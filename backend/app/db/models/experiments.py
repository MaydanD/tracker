"""Personal experiments: a bounded intervention window the user defines.

An experiment is **not** a habit. It is a temporary change or observation with a
start and an end; Tracker only compares the user's existing habit and Daily State
data before, during and after it. Nothing here proves causation.

Status is deliberately *not* a stored column. It is one deterministic function of
the dates and the cancellation timestamp (see ``app.domain.experiments``), so the
lifecycle can never drift out of sync with the calendar.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class Experiment(Base):
    """One user-defined experiment window."""

    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_nonempty"),
        CheckConstraint("start_date <= end_date", name="date_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    # User-authored text: what they expect to see, and what they change.
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    protocol: Mapped[str] = mapped_column(Text, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Set only by the explicit cancel action; the effective end becomes this date.
    # Stored as a calendar date (from the injected Clock), because every window
    # rule is calendar-based and must be deterministic, never wall-clock.
    cancelled_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"<Experiment id={self.id!r} {self.title!r} {self.start_date}..{self.end_date}>"
