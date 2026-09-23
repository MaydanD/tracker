"""Infrastructure-only tables.

Stage 1 deliberately does not model Habits, Areas, DailyEntries, Insights or any
other product entity — that starts in Stage 2. ``app_metadata`` exists so the
migration pipeline has something real to create and so tests can prove that the
database is genuinely reachable and migrated.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class AppMetadata(Base):
    """Simple key/value store for internal, non-user-facing bookkeeping.

    Timestamps are UTC; SQLite stores them without an offset by design (see
    ``app.core.time``).
    """

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
