"""Database connectivity and session lifecycle tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.database import Database, create_database
from app.db.models import AppMetadata
from app.services.health import check_database


def test_database_file_is_created_inside_the_data_directory(
    migrated_settings: Settings,
) -> None:
    database_path = migrated_settings.resolved_database_path

    assert database_path.exists()
    assert database_path.parent == migrated_settings.resolved_data_dir
    assert database_path.name == "tracker.db"


def test_database_container_uses_resolved_settings(
    migrated_settings: Settings,
) -> None:
    database = create_database(migrated_settings)
    try:
        assert database.database_url == migrated_settings.resolved_database_url
        assert str(database.engine.url) == migrated_settings.resolved_database_url
    finally:
        database.dispose()


def test_session_can_execute_a_query(session: Session) -> None:
    assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_sqlite_pragmas_are_applied(session: Session) -> None:
    foreign_keys = session.execute(text("PRAGMA foreign_keys")).scalar_one()
    journal_mode = session.execute(text("PRAGMA journal_mode")).scalar_one()
    busy_timeout = session.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"
    assert busy_timeout == 5000


def test_migration_marker_row_is_present(session: Session) -> None:
    marker = session.get(AppMetadata, "schema_initialized_at")

    assert marker is not None
    assert marker.value.endswith("Z")
    assert marker.created_at is not None


def test_sessions_do_not_commit_implicitly(database: Database) -> None:
    """Writes only persist after an explicit ``commit()``."""
    with database.session() as db_session:
        db_session.add(AppMetadata(key="uncommitted_row", value="1"))

    with database.session() as db_session:
        assert db_session.get(AppMetadata, "uncommitted_row") is None

    with database.session() as db_session:
        db_session.add(AppMetadata(key="committed_row", value="1"))
        db_session.commit()

    with database.session() as db_session:
        assert db_session.get(AppMetadata, "committed_row") is not None


def test_session_rolls_back_after_an_error(database: Database) -> None:
    with pytest.raises(RuntimeError):
        with database.session() as db_session:
            db_session.add(AppMetadata(key="failed_row", value="1"))
            raise RuntimeError("boom")

    with database.session() as db_session:
        assert db_session.get(AppMetadata, "failed_row") is None


def test_database_dispose_is_safe_to_call_twice(database: Database) -> None:
    database.dispose()
    database.dispose()


def test_check_database_succeeds_against_a_migrated_database(
    database: Database,
) -> None:
    assert check_database(database) is None


def test_check_database_raises_when_the_file_cannot_be_opened(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "tracker.db"
    broken = Database(f"sqlite+pysqlite:///{missing.as_posix()}")

    try:
        with pytest.raises(SQLAlchemyError):
            check_database(broken)
    finally:
        broken.dispose()
