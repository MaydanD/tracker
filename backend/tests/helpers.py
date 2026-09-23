"""Shared test helpers (importable from test modules)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db.database import create_db_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


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
