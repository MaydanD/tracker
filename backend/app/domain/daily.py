"""Daily habit entry rules.

One entry records what the user did for one habit on one *calendar date*. The
rules that make that safe live here as pure functions, so they can be tested
without a database:

* **"no entry" is a state.** A missing record means "the user has not said
  anything yet" — it is *never* automatically interpreted as ``missed``. Only an
  explicit ``missed`` entry means the habit was not done. Nothing in Tracker
  derives a miss from silence.
* **Statuses.** ``done`` and ``missed`` describe a day that has already happened
  (today or earlier); ``skipped`` is a deliberate/planned skip and is the only
  status allowed on a future date.
* **Skip reason is separate from the note.** ``skip_reason`` explains *why* a
  habit was intentionally skipped and exists only for ``skipped``; ``note`` is a
  free-form remark attached to any entry. They are distinct fields and are never
  merged.
* **Quantity is measured against the habit configuration in force on that date.**
  Validation therefore receives a :class:`~app.domain.habits.HabitConfig` rather
  than a bare tracking mode: the unit and the decimal rule of the day decide what
  is acceptable (see :mod:`app.db.queries` and ``habit_versions``).

Quantity storage is exact. SQLite has no decimal type and its ``NUMERIC``
affinity goes through a binary float, which is what makes "6.4" print as
6.4000000000000004. Tracker therefore stores a quantity as an integer number of
millionths (:data:`QUANTITY_SCALE`) and only converts to
:class:`decimal.Decimal` for arithmetic and display. The API exposes it as a JSON
number because JSON has no decimal type; the stored value is never a float and
never a string.

The choices this makes are deliberate product bounds, not accidents of the
implementation:

* **Six decimal places.** Micro-precision is far beyond what any plausibly
  hand-recorded unit needs (a gram of a body weight in kg, a metre of a distance
  in km, a millisecond of a duration in seconds), so the representation stops
  being the thing that limits a future unit. Excess precision is *rejected*, never
  rounded: quietly dropping a digit the user typed would corrupt a record.
* **Non-negative and at most :data:`MAX_QUANTITY`.** Counts and measurements are
  non-negative here, and the cap keeps the scaled integer comfortably inside a
  64-bit column (1 000 000 × 10^6 = 10^12) instead of silently overflowing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from math import isfinite

from app.domain.errors import (
    FutureEntryError,
    InvalidEntryStatusError,
    InvalidNoteError,
    InvalidQuantityValueError,
    InvalidSkipReasonError,
    QuantityDecimalNotAllowedError,
    QuantityNotAllowedError,
    SkipReasonNotAllowedError,
    SkipReasonRequiredError,
)
from app.domain.habits import HabitConfig
from app.domain.tracking import TrackingMode


class EntryStatus(StrEnum):
    """What the user recorded for a habit on a date.

    Deliberately small: Stage 3 stores observations, and a "partial" state is
    expressed by marking the habit done and recording a quantity.
    """

    DONE = "done"
    MISSED = "missed"
    SKIPPED = "skipped"


#: The only statuses allowed on a date that has not happened yet. A planned skip
#: is the single future entry Tracker accepts.
FUTURE_ALLOWED_STATUSES: tuple[EntryStatus, ...] = (EntryStatus.SKIPPED,)

SKIP_REASON_MAX_LENGTH = 200
NOTE_MAX_LENGTH = 500

#: Exact storage scale: a quantity is kept as an integer number of millionths.
#: Six places covers every real unit with room to spare, and keeps the scaled
#: value a plain 64-bit integer (see the module docstring for the bound).
QUANTITY_DECIMAL_PLACES = 6
QUANTITY_SCALE = 10**QUANTITY_DECIMAL_PLACES
#: Upper bound on a single quantity. Large enough for any real unit (pages,
#: minutes, km, reps, steps) and small enough that the scaled integer stays a
#: plain 64-bit value instead of silently overflowing the column.
MAX_QUANTITY = Decimal("1000000")

#: The largest integer this module will ever produce for a quantity. Stated here
#: so a regression test can pin it against the 64-bit range of the DB column.
MAX_SCALED_QUANTITY = int(MAX_QUANTITY * QUANTITY_SCALE)


# ---------------------------------------------------------------------------
# Quantity
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Decimal:
    """Convert an incoming quantity to :class:`~decimal.Decimal` without floats.

    Floats are converted through their shortest string form, so a JSON ``6.4``
    becomes ``Decimal("6.4")`` and not the binary approximation behind it.
    """
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, bool):
        raise InvalidQuantityValueError("A quantity must be a number.")
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, float):
        if not isfinite(value):
            raise InvalidQuantityValueError("A quantity must be a finite number.")
        decimal_value = Decimal(str(value))
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value.strip())
        except (InvalidOperation, ValueError) as exc:
            raise InvalidQuantityValueError("A quantity must be a number.") from exc
    else:
        raise InvalidQuantityValueError("A quantity must be a number.")

    if not decimal_value.is_finite():
        raise InvalidQuantityValueError("A quantity must be a finite number.")
    return decimal_value


@dataclass(frozen=True, slots=True)
class Quantity:
    """An exact quantity, stored as an integer number of millionths."""

    scaled: int

    @classmethod
    def parse(cls, value: object) -> Quantity:
        """Validate and convert an incoming value.

        Rejects negative numbers, absurdly large numbers, and anything with more
        precision than :data:`QUANTITY_DECIMAL_PLACES`. Values are never silently
        rounded: losing a digit the user typed would corrupt a record.
        """
        decimal_value = _to_decimal(value)

        if decimal_value < 0:
            raise InvalidQuantityValueError(
                "A quantity cannot be negative.",
                details={"quantity_value": str(decimal_value)},
            )
        if decimal_value > MAX_QUANTITY:
            raise InvalidQuantityValueError(
                "That quantity is too large.",
                details={"quantity_value": str(decimal_value), "max": str(MAX_QUANTITY)},
            )

        scaled = decimal_value * QUANTITY_SCALE
        if scaled != scaled.to_integral_value():
            raise InvalidQuantityValueError(
                f"A quantity can have at most {QUANTITY_DECIMAL_PLACES} decimal places.",
                details={"quantity_value": str(decimal_value)},
            )
        return cls(scaled=int(scaled))

    @property
    def value(self) -> Decimal:
        """The quantity as an exact decimal (``Decimal("6.4")``, never ``6.4000``)."""
        return Decimal(self.scaled) / QUANTITY_SCALE

    @property
    def is_whole(self) -> bool:
        """True when the value has no fractional part."""
        return self.scaled % QUANTITY_SCALE == 0


def validate_quantity(
    configuration: HabitConfig, quantity_value: object | None
) -> Quantity | None:
    """Validate a quantity against the habit configuration in force on the date.

    Quantity only exists for ``binary_quantity`` habits: a binary habit with a
    quantity is a contradiction, not extra information, and is rejected. The
    decimal rule comes from the same historical configuration, so editing an old
    day is judged by the rule that applied back then.
    """
    if quantity_value is None:
        return None

    if configuration.tracking_mode is not TrackingMode.BINARY_QUANTITY:
        raise QuantityNotAllowedError(
            "This habit does not track a quantity.",
            details={"tracking_mode": configuration.tracking_mode.value},
        )

    quantity = Quantity.parse(quantity_value)
    if not configuration.quantity_allows_decimal and not quantity.is_whole:
        raise QuantityDecimalNotAllowedError(
            "This habit is configured for whole numbers only.",
            details={
                "quantity_value": str(quantity.value),
                "quantity_unit": configuration.quantity_unit,
            },
        )
    return quantity


# ---------------------------------------------------------------------------
# Status, skip reason, note
# ---------------------------------------------------------------------------


def coerce_status(status: object) -> EntryStatus:
    """Validate a status, raising a stable domain error instead of a ``ValueError``."""
    try:
        return EntryStatus(status)  # type: ignore[arg-type]
    except ValueError as exc:
        raise InvalidEntryStatusError(
            "Unknown daily entry status.", details={"status": str(status)}
        ) from exc


def ensure_status_allowed_on(
    *, status: EntryStatus, entry_date: date, today: date
) -> None:
    """Reject ``done``/``missed`` on a future date.

    This is a product rule, not a UI preference: a habit cannot be reported as
    performed or failed before the day exists. Only a planned skip may be
    recorded ahead of time.
    """
    if entry_date > today and status not in FUTURE_ALLOWED_STATUSES:
        raise FutureEntryError(
            "Only a planned skip can be recorded for a future date.",
            details={
                "entry_date": entry_date.isoformat(),
                "today": today.isoformat(),
                "status": status.value,
            },
        )


def normalise_skip_reason(status: EntryStatus, skip_reason: str | None) -> str | None:
    """Trim a skip reason and keep it strictly tied to ``skipped``.

    A skipped entry must say why. For ``done``/``missed`` the field is cleared
    rather than stored, so a reason can never be silently reinterpreted later.
    """
    cleaned = " ".join((skip_reason or "").split())

    if status is EntryStatus.SKIPPED:
        if not cleaned:
            raise SkipReasonRequiredError("Enter why the habit was skipped.")
        if len(cleaned) > SKIP_REASON_MAX_LENGTH:
            raise InvalidSkipReasonError(
                f"A skip reason can be at most {SKIP_REASON_MAX_LENGTH} characters."
            )
        return cleaned

    if cleaned:
        raise SkipReasonNotAllowedError(
            "A skip reason only applies to a deliberately skipped entry.",
            details={"status": status.value},
        )
    return None


def normalise_note(note: str | None) -> str | None:
    """Trim a note; blank input means "no note"."""
    if note is None:
        return None
    cleaned = note.strip()
    if not cleaned:
        return None
    if len(cleaned) > NOTE_MAX_LENGTH:
        raise InvalidNoteError(f"A note can be at most {NOTE_MAX_LENGTH} characters.")
    return cleaned


# ---------------------------------------------------------------------------
# The full rule set
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntryValues:
    """A fully validated daily entry, ready to be persisted."""

    status: EntryStatus
    quantity: Quantity | None
    skip_reason: str | None
    note: str | None


def validate_entry(
    *,
    configuration: HabitConfig,
    status: EntryStatus | str,
    entry_date: date,
    today: date,
    quantity_value: object | None = None,
    skip_reason: str | None = None,
    note: str | None = None,
) -> EntryValues:
    """Apply every daily-entry rule and return the values to store.

    ``configuration`` is the habit configuration effective on ``entry_date``, so
    a historical edit is validated against the settings that applied back then.
    """
    resolved_status = coerce_status(status)

    ensure_status_allowed_on(status=resolved_status, entry_date=entry_date, today=today)

    return EntryValues(
        status=resolved_status,
        quantity=validate_quantity(configuration, quantity_value),
        skip_reason=normalise_skip_reason(resolved_status, skip_reason),
        note=normalise_note(note),
    )
