"""How a habit is recorded: completion, quantity, and daily value scales.

A habit is answered in one of two ways:

* **completion** — ``done``, ``missed`` or a deliberate ``skipped``. This is the
  original model, and a habit with ``binary``/``binary_quantity`` tracking keeps
  it exactly as before.
* **value** — a small fixed scale the user answers every day: ``нет``/``да`` for
  taking the stairs, ``0``/``мало``/``нормально``/``много`` for walking. The
  answer is stored as a number so it can be correlated, averaged and trended.

Three parts of a value scale belong to the habit's *configuration*, never to the
client:

* :class:`ValueType` — how many values the scale has: ``binary`` (0/1) or
  ``ordinal_4`` (0..3);
* ``value_labels`` — the Russian text of every position, stored per version,
  because the same ``ordinal_4`` scale means completely different things from
  one habit to the next (Настроение is ``ужас/плохо/норм/хорошо``, Симптомы is
  ``нет/слабые/заметные/сильные``). Labels live in the version so an old day
  keeps the words it was recorded with;
* :class:`Direction` — whether a higher value is better, worse, or neither.
  Analytics must never have to guess this from a habit's name, and it is
  deliberately **not** the same thing as importance (the habit's
  :attr:`~app.domain.habits.HabitConfig.weight`): direction says which end of
  the scale is good, importance says how much the habit matters to the user.

``None`` is never zero. A recorded ``0`` is a real answer — "нет", "no coffee" —
while a missing entry means the day was not recorded at all.

Units are free text on purpose (pages, minutes, km, reps, glasses, chapters,
anything the user needs). There is deliberately no unit conversion system and no
fixed unit enum, because converting km to metres or minutes to hours would
invent meaning the user never expressed.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.errors import (
    InvalidDirectionError,
    InvalidHabitValueError,
    InvalidQuantityUnitError,
    InvalidValueLabelsError,
    InvalidValueTypeError,
)

QUANTITY_UNIT_MAX_LENGTH = 32

#: A label is short display text ("нормально", "3+ кофе"), not a sentence.
VALUE_LABEL_MAX_LENGTH = 40


class TrackingMode(StrEnum):
    """How a habit is recorded.

    Completion modes answer *whether* the habit happened; a habit whose
    configuration carries a :class:`ValueType` instead answers *how much*, and
    stores that answer in ``daily_habit_entries.value``.
    """

    BINARY = "binary"
    BINARY_QUANTITY = "binary_quantity"


#: Tracking modes that measure a quantity. Only meaningful with a unit.
QUANTITY_MODES: tuple[TrackingMode, ...] = (TrackingMode.BINARY_QUANTITY,)


class ValueType(StrEnum):
    """How many discrete values a habit's answer has."""

    BINARY = "binary"
    ORDINAL_4 = "ordinal_4"


class Direction(StrEnum):
    """Whether a higher value is better, worse, or carries no built-in judgement.

    ``positive`` — more is better (Прогулка, Чтение, Энергия);
    ``negative`` — more is worse (Симптомы, Игры, Алкоголь);
    ``neutral``  — no evaluative meaning at all (Секс, Работа, Кофе).
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


#: Number of labels and the maximum value of each scale. ``binary`` is ``0/1``.
SCALE_LENGTH: dict[ValueType, int] = {
    ValueType.BINARY: 2,
    ValueType.ORDINAL_4: 4,
}

#: The widest scale Tracker stores; pins the column's check constraint.
MAX_VALUE = 3

#: Labels used when a binary habit does not configure its own. ``ordinal_4``
#: labels are never defaulted silently — four unknown words would be worse than
#: an honest error — so only the two-value scale has a fallback.
DEFAULT_BINARY_LABELS: tuple[str, ...] = ("нет", "да")


def normalise_quantity_unit(unit: str | None, *, required: bool) -> str | None:
    """Trim and validate a quantity unit.

    Returns ``None`` when quantity tracking is disabled (any submitted unit is
    discarded, so a binary habit can never keep stale configuration).
    """
    if not required:
        return None

    cleaned = " ".join((unit or "").split())
    if not cleaned:
        raise InvalidQuantityUnitError(
            "Enter a unit (for example pages, minutes, km or reps)."
        )
    if len(cleaned) > QUANTITY_UNIT_MAX_LENGTH:
        raise InvalidQuantityUnitError(
            f"A unit can be at most {QUANTITY_UNIT_MAX_LENGTH} characters."
        )
    return cleaned


def resolve_allows_decimal(*, tracking_mode: TrackingMode, allows_decimal: bool) -> bool:
    """Decimal support only has meaning when a quantity is recorded."""
    if tracking_mode is TrackingMode.BINARY:
        return False
    return bool(allows_decimal)


# ---------------------------------------------------------------------------
# Value scales
# ---------------------------------------------------------------------------


def coerce_value_type(value: object) -> ValueType:
    """Validate a value type, raising a stable domain error."""
    try:
        return ValueType(value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise InvalidValueTypeError(
            details={"value_type": str(value)}
        ) from exc


def coerce_direction(value: object) -> Direction:
    """Validate a direction, raising a stable domain error."""
    try:
        return Direction(value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise InvalidDirectionError(
            details={"direction": str(value)}
        ) from exc


def max_value(value_type: ValueType | str) -> int:
    """The largest value a scale accepts (1 for binary, 3 for ordinal_4)."""
    return SCALE_LENGTH[coerce_value_type(value_type)] - 1


def normalise_value_labels(
    value_type: ValueType | str, labels: tuple[str, ...] | list[str] | None
) -> tuple[str, ...]:
    """Validate the label of every position of a scale.

    A scale with a missing or blank label would leave the UI unable to render an
    option, so labels are required — one per position — and a ``binary`` scale
    with no labels of its own falls back to ``нет``/``да``.
    """
    resolved = coerce_value_type(value_type)
    expected = SCALE_LENGTH[resolved]

    if labels is None:
        if resolved is ValueType.BINARY:
            return DEFAULT_BINARY_LABELS
        raise InvalidValueLabelsError(
            f"A {resolved.value} habit needs exactly {expected} labels.",
            details={"expected": expected},
        )

    cleaned = tuple(" ".join(str(label).split()) for label in labels)
    if len(cleaned) != expected:
        raise InvalidValueLabelsError(
            f"A {resolved.value} habit needs exactly {expected} labels.",
            details={"labels": list(cleaned), "expected": expected},
        )
    if any(not label for label in cleaned):
        raise InvalidValueLabelsError("A value label cannot be blank.")
    # Two positions with the same word would be indistinguishable on the
    # check-in screen, so the scale itself would lose a level.
    if len(set(cleaned)) != len(cleaned):
        raise InvalidValueLabelsError(
            "Every value label must be different.",
            details={"labels": list(cleaned)},
        )
    too_long = [label for label in cleaned if len(label) > VALUE_LABEL_MAX_LENGTH]
    if too_long:
        raise InvalidValueLabelsError(
            f"A value label can be at most {VALUE_LABEL_MAX_LENGTH} characters.",
            details={"labels": too_long},
        )
    return cleaned


def validate_value(value_type: ValueType | str, value: object) -> int:
    """Validate a recorded answer against its scale.

    Booleans are rejected even though ``True == 1`` in Python: an answer must be
    an integer on the scale, not a truthiness accident. Non-integers and values
    outside ``0..max`` are rejected rather than clamped, so a typo can never be
    stored as a different answer.
    """
    resolved = coerce_value_type(value_type)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidHabitValueError(
            "A habit value must be a whole number.",
            details={"value": value, "value_type": resolved.value},
        )
    upper = max_value(resolved)
    if not 0 <= value <= upper:
        raise InvalidHabitValueError(
            f"A {resolved.value} value must be between 0 and {upper}.",
            details={"value": value, "min": 0, "max": upper},
        )
    return value


def normalised_value(
    value: int, value_type: ValueType | str, direction: Direction | str
) -> float | None:
    """A direction-aware ``0..1`` reading of one answer, or ``None`` if neutral.

    * ``positive`` — the value as-is (``0 → 0.0`` … ``max → 1.0``);
    * ``negative`` — inverted (``0 → 1.0`` … ``max → 0.0``);
    * ``neutral`` — ``None``.

    Neutral is deliberately ``None`` rather than a middle value: a neutral habit
    (Секс, Работа, Кофе) has no better or worse end, so it must never move an
    evaluative score — not by being high, and not by being low. Analytics can
    still correlate it.

    The caller still needs :func:`validate_value` for range checks; this helper
    assumes an already-valid value and only decides the direction.
    """
    upper = max_value(coerce_value_type(value_type))
    if upper == 0:  # pragma: no cover - no scale is that small today
        return None
    fraction = value / upper
    resolved_direction = coerce_direction(direction)
    if resolved_direction is Direction.POSITIVE:
        return fraction
    if resolved_direction is Direction.NEGATIVE:
        return 1.0 - fraction
    return None
