"""One independent observation per date; NULL never means false or zero."""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class DailyState(Base):
    __tablename__ = "daily_states"
    __table_args__ = (
        UniqueConstraint("state_date"),
        *(CheckConstraint(
            f"{field} IS NULL OR (typeof({field}) = 'integer' AND {field} BETWEEN 1 AND 5)",
            name=f"{field}_range",
        ) for field in ("mood", "energy", "wellbeing")),
        *(CheckConstraint(
            f"{field} IS NULL OR (typeof({field}) = 'integer' AND {field} BETWEEN 0 AND 1440)",
            name=f"{field}_range",
        ) for field in ("sleep_minutes", "gaming_minutes", "computer_minutes")),
        *(CheckConstraint(f"{field} IS NULL OR {field} IN (0, 1)", name=f"{field}_values")
          for field in ("alcohol", "gaming", "computer_overuse")),
        CheckConstraint("sleep_status IS NULL OR sleep_status IN ('underslept', 'normal', 'overslept')", name="sleep_status_values"),
        CheckConstraint("alcohol_detail IS NULL OR (alcohol IS 1 AND length(trim(alcohol_detail)) BETWEEN 1 AND 200)", name="alcohol_detail_consistency"),
        CheckConstraint("gaming_minutes IS NULL OR gaming IS 1 OR (gaming IS 0 AND gaming_minutes = 0)", name="gaming_minutes_consistency"),
        CheckConstraint("note IS NULL OR length(trim(note)) BETWEEN 1 AND 500", name="note_length"),
        CheckConstraint(
            "mood IS NOT NULL OR energy IS NOT NULL OR wellbeing IS NOT NULL OR "
            "sleep_status IS NOT NULL OR sleep_minutes IS NOT NULL OR alcohol IS NOT NULL OR "
            "gaming IS NOT NULL OR computer_overuse IS NOT NULL OR computer_minutes IS NOT NULL OR note IS NOT NULL",
            name="nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state_date: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[int | None] = mapped_column(Integer)
    energy: Mapped[int | None] = mapped_column(Integer)
    wellbeing: Mapped[int | None] = mapped_column(Integer)
    sleep_status: Mapped[str | None] = mapped_column(String(16))
    sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    alcohol: Mapped[bool | None] = mapped_column(Boolean)
    alcohol_detail: Mapped[str | None] = mapped_column(String(200))
    gaming: Mapped[bool | None] = mapped_column(Boolean)
    gaming_minutes: Mapped[int | None] = mapped_column(Integer)
    computer_overuse: Mapped[bool | None] = mapped_column(Boolean)
    computer_minutes: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
