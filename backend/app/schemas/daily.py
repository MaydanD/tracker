"""Daily entry schemas.

Shape only: ranges, precision and cross-field rules (future dates, skip reasons,
quantities, values against the scale of the day) are decided by
``app.domain.daily`` and reported with stable error codes, so the rules exist in
exactly one place.

``value`` is the answer of a habit that is tracked on a value scale: a whole
number on that scale, where ``0`` is a real recorded answer and only a missing
entry means "not recorded".

``quantity_value`` is accepted as a decimal and returned as a JSON *number* —
JSON has no decimal type, and the exact value is preserved in the database as an
integer number of millionths (see :mod:`app.db.models.daily`).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from math import isfinite

from pydantic import BaseModel, Field, field_validator

from app.db.models import DailyHabitEntry, HabitVersion
from app.domain.daily import (
    NOTE_MAX_LENGTH,
    SKIP_REASON_MAX_LENGTH,
    EntryStatus,
)
from app.domain.habits import Importance
from app.domain.tracking import Direction, TrackingMode, ValueType
from app.schemas.areas import AreaSummary
from app.schemas.habits import ScheduleRead
from app.services.daily import DayItem


class DailyEntryWrite(BaseModel):
    """Payload for creating or replacing a habit's entry on one date.

    The whole entry is sent because saving is an idempotent replace: leaving
    ``note`` or ``quantity_value`` out clears them.
    """

    status: EntryStatus
    quantity_value: Decimal | None = None
    value: int | None = Field(
        default=None, strict=True,
        description=(
            "Answer of a value-tracked habit (0/1, or 0–3); 0 is a recorded "
            "answer, not an empty one."
        ),
    )
    skip_reason: str | None = Field(default=None, max_length=SKIP_REASON_MAX_LENGTH)
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("quantity_value", mode="before")
    @classmethod
    def _normalise_quantity(cls, value: object) -> object:
        """Convert a JSON number to an exact decimal before it can become a float.

        ``Decimal(6.4)`` would carry the binary noise behind the literal; going
        through its shortest string form gives exactly ``Decimal("6.4")``. Anything
        that is not a number is left for pydantic to report as a shape error.
        """
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            return value
        if isinstance(value, float):
            return Decimal(str(value)) if isfinite(value) else value
        if isinstance(value, int):
            return Decimal(value)
        return value


class DailyEntryRead(BaseModel):
    """A recorded day, with the unit taken from the configuration of that date."""

    id: int
    habit_id: int
    entry_date: date
    status: EntryStatus
    value: int | None = Field(
        default=None,
        description=(
            "Answer of a value-tracked habit; null for a completion habit or "
            "when nothing is recorded."
        ),
    )
    quantity_value: float | None = Field(
        default=None, description="Exact stored quantity; null when not recorded."
    )
    quantity_unit: str | None = Field(
        default=None,
        description=(
            "Unit of the habit configuration effective on entry_date. Derived, "
            "never stored on the entry."
        ),
    )
    skip_reason: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls, entry: DailyHabitEntry, version: HabitVersion
    ) -> DailyEntryRead:
        quantity = entry.quantity
        return cls(
            id=entry.id,
            habit_id=entry.habit_id,
            entry_date=entry.entry_date,
            status=EntryStatus(entry.status),
            value=entry.value,
            quantity_value=None if quantity is None else float(quantity.value),
            quantity_unit=version.quantity_unit,
            skip_reason=entry.skip_reason,
            note=entry.note,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class DayItemRead(BaseModel):
    """One habit on a chosen date, described by that date's configuration.

    ``entry`` is ``null`` for a day the user has not recorded yet. The API never
    fills it in with ``missed``.
    """

    habit_id: int
    name: str
    area: AreaSummary
    #: How much the habit matters: `low`, `normal` or `high`.
    importance: Importance
    #: Historical score coefficient, independent of importance.
    weight: int
    tracking_mode: TrackingMode
    quantity_unit: str | None
    quantity_allows_decimal: bool
    #: ``null`` for a completion habit; otherwise the scale it is answered on.
    value_type: ValueType | None
    #: One label per value of the scale, in the user's own words.
    value_labels: list[str] | None
    #: Which end of the scale is good; ``null`` for a completion habit.
    direction: Direction | None
    schedule: ScheduleRead
    is_archived: bool
    entry: DailyEntryRead | None

    @classmethod
    def from_item(cls, item: DayItem) -> DayItemRead:
        version = item.version
        entry = item.entry

        return cls(
            habit_id=item.habit.id,
            name=version.name,
            area=AreaSummary.from_model(version.area),
            importance=version.importance_enum,
            weight=version.weight,
            tracking_mode=TrackingMode(version.tracking_mode),
            quantity_unit=version.quantity_unit,
            quantity_allows_decimal=version.quantity_allows_decimal,
            value_type=version.value_type_enum,
            value_labels=None if version.value_labels is None else list(version.value_labels),
            direction=version.direction_enum,
            schedule=ScheduleRead.from_domain(version.schedule),
            is_archived=item.habit.is_archived,
            entry=(
                None if entry is None else DailyEntryRead.from_model(entry, version)
            ),
        )


class DayRead(BaseModel):
    """The state of one calendar date.

    ``today`` and ``is_future`` come from the server so the screen and the backend
    agree on which rules apply: a future date only accepts a planned skip.
    """

    entry_date: date
    today: date
    is_future: bool
    items: list[DayItemRead]
