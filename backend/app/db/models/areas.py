"""Area ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class Area(Base):
    """A persistent life sphere such as Health, Development, Work or Household.

    Areas are archived rather than deleted: habits (and, from Stage 3, historical
    entries) continue to reference them. Name and colour changes are not
    versioned — habit versions keep referential integrity through ``area_id``,
    and the *name* of an area is display metadata rather than historical fact.
    """

    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
