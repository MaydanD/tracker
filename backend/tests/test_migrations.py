"""Alembic migration tests: fresh database, no model drift, reversible."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text

from app.core.config import Settings
from app.db.database import create_db_engine
from tests.helpers import alembic_config, run_migrations, table_names


def _recorded_revision(database_url: str) -> str:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()


def test_upgrade_head_creates_the_schema(settings: Settings) -> None:
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)

    tables = table_names(settings.resolved_database_url)

    assert "app_metadata" in tables
    assert "alembic_version" in tables
    assert settings.resolved_database_path.exists()


def test_upgrade_records_the_revision(settings: Settings) -> None:
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)

    assert _recorded_revision(settings.resolved_database_url) == "0001"


def test_migrations_are_idempotent(settings: Settings) -> None:
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)
    run_migrations(settings.resolved_database_url)  # second run is a no-op

    assert "app_metadata" in table_names(settings.resolved_database_url)


def test_models_match_the_migrations(settings: Settings) -> None:
    """`alembic check` fails if models and migrations have drifted apart."""
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)

    command.check(alembic_config(settings.resolved_database_url))


def test_downgrade_and_upgrade_are_reversible(settings: Settings) -> None:
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)

    command.downgrade(alembic_config(settings.resolved_database_url), "base")
    assert "app_metadata" not in table_names(settings.resolved_database_url)

    run_migrations(settings.resolved_database_url)
    assert "app_metadata" in table_names(settings.resolved_database_url)


def test_offline_mode_can_emit_sql(settings: Settings, capsys) -> None:
    """`alembic upgrade --sql` works without touching a database."""
    command.upgrade(alembic_config(settings.resolved_database_url), "head", sql=True)

    emitted = capsys.readouterr().out
    assert "CREATE TABLE app_metadata" in emitted
