"""Daily habit entry ORM model.

One row records one habit's state on one calendar date. The row is deliberately
*thin on configuration*: it stores the user's observation only, and the rules
that applied that day (unit, decimal support, weight, schedule) are resolved from
``habit_versions`` — the single source of truth for dated habit configuration.

Why no configuration snapshot and no ``habit_version_id`` on the entry:

* a snapshot would duplicate ``habit_versions`` and could drift from it;
* a foreign key would freeze the version a row was written against, which breaks
  the Stage 2 same-day-collapse rule: an edit made today updates today's version,
  and today's entry must be read through the resulting configuration rather than
  through a frozen copy;
* resolving ``habit_id + entry_date`` through the existing effective-dated lookup
  already answers "what were the rules that day?" for any date, past or future.

``quantity_value_micro`` is an exact integer number of millionths rather than a
``NUMERIC``/``REAL`` column: SQLite's numeric affinity is binary floating point and
would turn a stored 6.4 into 6.4000000000000004 (see :mod:`app.domain.daily`).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.habits import Habit
from app.domain.daily import NOTE_MAX_LENGTH, SKIP_REASON_MAX_LENGTH, Quantity


class DailyHabitEntry(Base):
    """What the user recorded for one habit on one calendar date.

    ``habit_id + entry_date`` is unique, so re-saving a day edits the existing row
    instead of appending a duplicate. The absence of a row is a first-class state
    ("no entry"); nothing derives a miss from it.
    """

    __tablename__ = "daily_habit_entries"
    __table_args__ = (
        UniqueConstraint("habit_id", "entry_date", name="habit_entry_date"),
        CheckConstraint(
            "status IN ('done', 'missed', 'skipped')",
            name="status_values",
        ),
        # The skip reason and the status must agree, so a reason can never be lost
        # or invented by a partial write. `trim` rejects whitespace-only reasons,
        # which is what the domain layer's normalisation also refuses.
        CheckConstraint(
            "(status = 'skipped' AND skip_reason IS NOT NULL "
            "AND length(trim(skip_reason)) > 0) OR "
            "(status <> 'skipped' AND skip_reason IS NULL)",
            name="skip_reason_matches_status",
        ),
        CheckConstraint(
            "quantity_value_micro IS NULL OR quantity_value_micro >= 0",
            name="quantity_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT is the point: a habit cannot be deleted out from under its recorded
    # history. Habits are archived, and this constraint makes a future delete
    # feature fail loudly instead of silently erasing years of entries.
    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="RESTRICT"), nullable=False
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Exact millionths of the historical quantity unit; never a float.
    quantity_value_micro: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(
        String(SKIP_REASON_MAX_LENGTH), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(NOTE_MAX_LENGTH), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    habit: Mapped[Habit] = relationship()

    # -- domain conversion --------------------------------------------------

    @property
    def quantity(self) -> Quantity | None:
        """The stored quantity as an exact value, or ``None`` when unrecorded."""
        if self.quantity_value_micro is None:
            return None
        return Quantity(scaled=self.quantity_value_micro)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return (
            f"<DailyHabitEntry habit={self.habit_id} date={self.entry_date} "
            f"status={self.status}>"
        )
