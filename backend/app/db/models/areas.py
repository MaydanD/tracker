"""Area ORM model.

``key`` and ``sort_order`` are the two columns a shipped (canonical) area uses:
a stable machine identifier so reconciliation recognises its own rows, and the
position the user should see it in. Both are plain configuration — an area
created by hand simply has no key and sorts after the shipped ones.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
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
    __table_args__ = (
        # Uniqueness is a unique *index*, not a table constraint: SQLite can
        # create an index on a populated table in place, while adding a UNIQUE
        # constraint rebuilds the table — and rebuilding ``areas`` would detach
        # every habit version that references it. Many NULLs are allowed, which
        # is exactly right: a hand-made area has no key.
        Index("uq_areas_key", "key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable machine identifier of an area Tracker created itself; NULL for a
    # user's own area.
    key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # 0 means "no position of its own": ordered by name after the shipped areas.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
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
