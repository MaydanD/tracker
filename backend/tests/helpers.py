"""Shared test helpers (importable from test modules)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db.database import create_db_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

STAGE_1_REVISION = "0001"
STAGE_2_REVISION = "8c12a1c62d83"
STAGE_3_REVISION = "fc1efb50fa8d"
STAGE_5_REVISION = "d5a1c09e2401"
STAGE_8_REVISION = "b2631e796164"


@dataclass(frozen=True)
class FrozenClock:
    """A clock stuck on one date, so calendar rules are testable.

    Satisfies ``app.core.time.Clock``; injected through ``create_app(..., clock=...)``
    instead of patching ``datetime`` anywhere in the application.
    """

    current: date

    def today(self) -> date:
        return self.current

    def now(self) -> datetime:
        # Midday keeps a frozen clock away from any midnight edge in file names.
        return datetime.combine(self.current, time(hour=12))

    def advance(self, days: int) -> FrozenClock:
        return FrozenClock(self.current + timedelta(days=days))


def alembic_config(database_url: str) -> Config:
    """Alembic config pointing at an explicit database."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_migrations(database_url: str, revision: str = "head") -> None:
    """Apply migrations to the given database."""
    command.upgrade(alembic_config(database_url), revision)


def table_names(database_url: str) -> list[str]:
    """Existing table names in the database at ``database_url``."""
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            return inspect(connection).get_table_names()
    finally:
        engine.dispose()


def habit_payload(**overrides: Any) -> dict[str, Any]:
    """A valid habit payload; override individual fields as needed.

    ``area_id`` is intentionally absent so tests state which area they use.
    """
    payload: dict[str, Any] = {
        "name": "Reading",
        "description": None,
        "weight": 1,
        "tracking_mode": "binary",
        "quantity_unit": None,
        "quantity_allows_decimal": False,
        "schedule": {"type": "daily"},
    }
    payload.update(overrides)
    return payload
