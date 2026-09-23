"""Declarative base and shared metadata for every Tracker table."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit constraint names keep Alembic migrations stable and make SQLite
# batch migrations (the default for this project) able to recreate constraints
# predictably.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier!r}>"
