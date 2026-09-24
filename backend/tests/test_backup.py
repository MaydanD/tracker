"""Automatic SQLite backup.

The point of these tests is that the copy is a *real, consistent* database — not
that a file with a nice name appeared. They therefore open the produced file with
SQLite itself and read data out of it, including a row written while the database
was in WAL mode.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.time import today_local
from app.db.backup import (
    BACKUP_PREFIX,
    BACKUP_RETENTION,
    BACKUP_SUFFIX,
    BackupStatus,
    automatic_backups,
    backup_filename,
    backups_for_day,
    copy_sqlite_database,
    run_startup_backup,
    sqlite_database_file,
)
from app.db.database import Database, create_database
from app.db.models import AppMetadata
from app.main import create_app
from tests.helpers import STAGE_2_REVISION, FrozenClock, run_migrations

TODAY = today_local()


@pytest.fixture()
def dev_settings(tmp_path: Path) -> Settings:
    """Development settings, where the automatic backup is active."""
    return Settings(
        _env_file=None,
        app_env="development",
        data_dir=tmp_path / "data",
        log_level="WARNING",
    )


@pytest.fixture()
def dev_database(dev_settings: Settings) -> Iterator[Database]:
    """A migrated database on disk, opened by the application's own container."""
    dev_settings.ensure_directories()
    run_migrations(dev_settings.resolved_database_url)
    database = create_database(dev_settings)
    try:
        yield database
    finally:
        database.dispose()


def write_marker(database: Database, key: str, value: str) -> None:
    with database.session() as session:
        session.add(AppMetadata(key=key, value=value))
        session.commit()


def read_value(backup_path: Path | None, key: str) -> str | None:
    """Read a value straight out of the backup file with the sqlite3 module."""
    assert backup_path is not None
    connection = sqlite3.connect(str(backup_path))
    try:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else row[0]
    finally:
        connection.close()


def table_names(backup_path: Path) -> set[str]:
    connection = sqlite3.connect(str(backup_path))
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


class TestAutomaticBackup:
    def test_a_backup_is_created_on_startup(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert outcome.status is BackupStatus.CREATED
        assert outcome.path is not None
        assert outcome.path.exists()
        assert outcome.path.parent == dev_settings.resolved_backups_dir

    def test_the_backup_is_stored_away_from_the_database(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert outcome.path is not None
        assert outcome.path.parent != dev_settings.resolved_database_path.parent
        assert dev_settings.resolved_backups_dir.is_dir()

    def test_the_name_carries_the_date_and_time(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert outcome.path is not None
        assert outcome.path.name.startswith(f"{BACKUP_PREFIX}{TODAY.isoformat()}-")
        assert outcome.path.name.endswith(BACKUP_SUFFIX)
        assert backup_filename(FrozenClock(TODAY).now()) == outcome.path.name


class TestBackupValidity:
    def test_the_backup_is_a_valid_sqlite_database(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        write_marker(dev_database, "backup_marker", "hello")

        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        connection = sqlite3.connect(str(outcome.path))
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()

        assert read_value(outcome.path, "backup_marker") == "hello"

    def test_the_backup_contains_the_whole_schema(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert outcome.path is not None
        assert {
            "app_metadata",
            "areas",
            "habits",
            "habit_versions",
            "daily_habit_entries",
        } <= table_names(outcome.path)

    def test_the_backup_includes_data_that_only_the_wal_file_holds(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        """The whole reason this module does not use ``shutil.copy``.

        A connection is held open while a row is written, so the row is genuinely
        only in ``tracker.db-wal`` and not yet in ``tracker.db``. A blind file copy
        would ship a database without it; the SQLite backup API takes a consistent
        snapshot instead.
        """
        database_path = dev_settings.resolved_database_path
        writer = sqlite3.connect(str(database_path))
        try:
            mode = writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            assert mode.lower() == "wal"
            writer.execute(
                "INSERT INTO app_metadata (key, value, created_at, updated_at) "
                "VALUES ('wal_only_row', '7', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
            writer.commit()

            assert Path(f"{database_path}-wal").exists()

            blind_copy = dev_settings.resolved_data_dir / "blind-copy.db"
            shutil.copy(database_path, blind_copy)
            assert read_value(blind_copy, "wal_only_row") is None, (
                "the test needs the row to still be WAL-only for this to prove "
                "anything"
            )

            outcome = run_startup_backup(
                dev_database, dev_settings, clock=FrozenClock(TODAY)
            )
        finally:
            writer.close()

        assert outcome.status is BackupStatus.CREATED
        assert read_value(outcome.path, "wal_only_row") == "7"


class TestOncePerDay:
    def test_a_second_run_on_the_same_day_does_not_add_another_backup(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        clock = FrozenClock(TODAY)

        first = run_startup_backup(dev_database, dev_settings, clock=clock)
        second = run_startup_backup(dev_database, dev_settings, clock=clock)

        assert first.status is BackupStatus.CREATED
        assert second.status is BackupStatus.SKIPPED
        assert len(backups_for_day(dev_settings.resolved_backups_dir, TODAY)) == 1

    def test_a_later_day_gets_its_own_backup(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        run_startup_backup(dev_database, dev_settings, clock=FrozenClock(TODAY))
        tomorrow = run_startup_backup(
            dev_database,
            dev_settings,
            clock=FrozenClock(TODAY + timedelta(days=1)),
        )

        assert tomorrow.status is BackupStatus.CREATED
        assert len(automatic_backups(dev_settings.resolved_backups_dir)) == 2

    def test_the_backup_path_can_be_discovered_for_a_day(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        run_startup_backup(dev_database, dev_settings, clock=FrozenClock(TODAY))

        found = backups_for_day(dev_settings.resolved_backups_dir, TODAY)

        assert len(found) == 1
        assert found[0].exists()


class TestNothingToBackUp:
    def test_the_test_environment_does_not_write_backups(
        self, migrated_settings: Settings
    ) -> None:
        """A test run must not create real backup files for a real database."""
        database = create_database(migrated_settings)
        try:
            outcome = run_startup_backup(
                database, migrated_settings, clock=FrozenClock(TODAY)
            )
        finally:
            database.dispose()

        assert outcome.status is BackupStatus.SKIPPED
        assert automatic_backups(migrated_settings.resolved_backups_dir) == []
        assert not migrated_settings.resolved_backups_dir.exists()

    def test_an_in_memory_database_is_not_backed_up(
        self, dev_settings: Settings
    ) -> None:
        database = Database("sqlite+pysqlite:///:memory:")
        try:
            outcome = run_startup_backup(
                database, dev_settings, clock=FrozenClock(TODAY)
            )
        finally:
            database.dispose()

        assert outcome.status is BackupStatus.SKIPPED
        assert sqlite_database_file(database.database_url) is None
        assert automatic_backups(dev_settings.resolved_backups_dir) == []

    def test_a_database_that_does_not_exist_yet_is_not_backed_up(
        self, tmp_path: Path
    ) -> None:
        settings = Settings(
            _env_file=None,
            app_env="development",
            data_dir=tmp_path / "fresh",
            log_level="WARNING",
        )
        settings.ensure_directories()
        database = create_database(settings)
        try:
            outcome = run_startup_backup(
                database, settings, clock=FrozenClock(TODAY)
            )
        finally:
            database.dispose()

        assert outcome.status is BackupStatus.SKIPPED
        assert outcome.reason is not None
        assert automatic_backups(settings.resolved_backups_dir) == []

    def test_a_non_sqlite_url_has_no_file_to_back_up(self) -> None:
        assert sqlite_database_file("postgresql://localhost/tracker") is None

    def test_sqlite_file_uris_are_resolved(self, tmp_path: Path) -> None:
        path = tmp_path / "tracker.db"

        resolved = sqlite_database_file(f"sqlite+pysqlite:///{path.as_posix()}")

        assert resolved == path


class TestFailuresAreVisible:
    def test_a_failed_backup_is_reported_and_logged(
        self,
        dev_database: Database,
        dev_settings: Settings,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # A *file* where the backups directory should be makes the write fail the
        # way a read-only or full disk would.
        dev_settings.resolved_backups_dir.parent.mkdir(parents=True, exist_ok=True)
        dev_settings.resolved_backups_dir.write_text("not a directory")

        with caplog.at_level(logging.ERROR, logger="app.db.backup"):
            outcome = run_startup_backup(
                dev_database, dev_settings, clock=FrozenClock(TODAY)
            )

        assert outcome.status is BackupStatus.FAILED
        assert any(record.levelno >= logging.ERROR for record in caplog.records)

    def test_a_failed_backup_does_not_stop_startup(
        self, dev_settings: Settings
    ) -> None:
        dev_settings.ensure_directories()
        run_migrations(dev_settings.resolved_database_url)
        dev_settings.resolved_backups_dir.parent.mkdir(parents=True, exist_ok=True)
        dev_settings.resolved_backups_dir.write_text("not a directory")

        with TestClient(create_app(dev_settings, clock=FrozenClock(TODAY))) as client:
            assert client.get("/api/health").status_code == 200


class TestInterruptedBackup:
    """A failure must leave nothing that could be mistaken for a backup.

    A truncated file with a valid-looking name is worse than no file at all: it
    would look like today's snapshot and would stop the next start from trying
    again.
    """

    def test_a_copy_that_fails_removes_the_file_it_created(
        self, tmp_path: Path
    ) -> None:
        # A directory cannot be opened as a database, so the copy fails *after* the
        # target name has been claimed — exactly the window that used to leave a
        # partial file behind.
        source = tmp_path / "not-a-database"
        source.mkdir()
        target = tmp_path / "backups" / backup_filename(FrozenClock(TODAY).now())

        with pytest.raises(sqlite3.Error):
            copy_sqlite_database(source, target)

        assert not target.exists()
        assert automatic_backups(target.parent) == []

    def test_a_failed_backup_does_not_suppress_the_days_retry(
        self,
        tmp_path: Path,
        dev_database: Database,
        dev_settings: Settings,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        write_marker(dev_database, "source_intact", "1")

        broken = tmp_path / "not-a-database"
        broken.mkdir()
        broken_database = Database(
            f"sqlite+pysqlite:///{broken.as_posix()}"
        )
        try:
            with caplog.at_level(logging.ERROR, logger="app.db.backup"):
                failed = run_startup_backup(
                    broken_database, dev_settings, clock=FrozenClock(TODAY)
                )
        finally:
            broken_database.dispose()

        assert failed.status is BackupStatus.FAILED
        assert failed.path is not None and not failed.path.exists()
        assert backups_for_day(dev_settings.resolved_backups_dir, TODAY) == []
        assert any(record.levelno >= logging.ERROR for record in caplog.records)
        # The failed attempt read the source; it must not have damaged it.
        assert read_value(dev_settings.resolved_database_path, "source_intact") == "1"

        retry = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert retry.status is BackupStatus.CREATED
        assert read_value(retry.path, "source_intact") == "1"


class TestExistingBackupIsNeverOverwritten:
    def test_the_copy_refuses_a_name_that_is_already_taken(
        self, tmp_path: Path, dev_database: Database
    ) -> None:
        target = tmp_path / "backups" / backup_filename(FrozenClock(TODAY).now())
        target.parent.mkdir(parents=True)
        target.write_bytes(b"an earlier backup")

        with pytest.raises(FileExistsError):
            copy_sqlite_database(
                sqlite_database_file(dev_database.database_url) or tmp_path, target
            )

        assert target.read_bytes() == b"an earlier backup"

    def test_a_colliding_startup_backup_is_skipped_and_leaves_the_file_alone(
        self,
        dev_database: Database,
        dev_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        backups_dir = dev_settings.resolved_backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        target = backups_dir / backup_filename(FrozenClock(TODAY).now())
        target.write_bytes(b"an earlier backup")
        # The race this guard exists for: the once-a-day check ran before the other
        # process had written its file.
        monkeypatch.setattr("app.db.backup.backups_for_day", lambda *_: [])

        outcome = run_startup_backup(
            dev_database, dev_settings, clock=FrozenClock(TODAY)
        )

        assert outcome.status is BackupStatus.SKIPPED
        assert outcome.path == target
        assert target.read_bytes() == b"an earlier backup"


class TestBackupBeforeMigration:
    def test_a_database_one_stage_behind_is_backed_up_before_it_migrates(
        self, tmp_path: Path
    ) -> None:
        """The snapshot must be of the database as it was *found*.

        A Stage 2 database is the case that matters: if the Stage 3 migration ever
        went wrong, this copy is the one to fall back to, so it has to be taken
        before the migration and it has to still hold the Stage 2 data.
        """
        settings = Settings(
            _env_file=None,
            app_env="development",
            data_dir=tmp_path / "data",
            log_level="WARNING",
        )
        settings.ensure_directories()
        run_migrations(settings.resolved_database_url, STAGE_2_REVISION)
        database = create_database(settings)
        try:
            write_marker(database, "stage_two_row", "kept")
        finally:
            database.dispose()

        with TestClient(create_app(settings, clock=FrozenClock(TODAY))) as client:
            # Behind on migrations, but reachable and honest about it.
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/ready").status_code == 503

        backups = backups_for_day(settings.resolved_backups_dir, TODAY)
        assert len(backups) == 1
        assert read_value(backups[0], "stage_two_row") == "kept"
        assert "daily_habit_entries" not in table_names(backups[0])

        run_migrations(settings.resolved_database_url)

        assert read_value(settings.resolved_database_path, "stage_two_row") == "kept"


class TestRetention:
    def test_old_automatic_backups_are_pruned(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        backups_dir = dev_settings.resolved_backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        older = [
            backups_dir / f"{BACKUP_PREFIX}2025-01-{day:02d}-120000{BACKUP_SUFFIX}"
            for day in range(1, BACKUP_RETENTION + 3)
        ]
        for path in older:
            path.write_bytes(b"stale")

        run_startup_backup(dev_database, dev_settings, clock=FrozenClock(TODAY))

        # One new backup plus at most BACKUP_RETENTION kept ones.
        remaining = automatic_backups(backups_dir)
        assert len(remaining) <= BACKUP_RETENTION
        assert not older[0].exists()

    def test_unrelated_files_in_the_backup_folder_are_never_deleted(
        self, dev_database: Database, dev_settings: Settings
    ) -> None:
        backups_dir = dev_settings.resolved_backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        keep = backups_dir / "restore-notes.txt"
        keep.write_text("mine")
        for day in range(1, BACKUP_RETENTION + 5):
            (
                backups_dir / f"{BACKUP_PREFIX}2025-01-{day:02d}-120000{BACKUP_SUFFIX}"
            ).write_bytes(b"stale")

        run_startup_backup(dev_database, dev_settings, clock=FrozenClock(TODAY))

        assert keep.exists()


class TestStartupIntegration:
    def test_starting_the_application_writes_todays_backup(
        self, dev_settings: Settings
    ) -> None:
        dev_settings.ensure_directories()
        run_migrations(dev_settings.resolved_database_url)
        database = create_database(dev_settings)
        write_marker(database, "before_start", "1")
        database.dispose()

        with TestClient(create_app(dev_settings, clock=FrozenClock(TODAY))) as client:
            assert client.get("/api/ready").status_code == 200

        backups = backups_for_day(dev_settings.resolved_backups_dir, TODAY)
        assert len(backups) == 1
        assert read_value(backups[0], "before_start") == "1"

    def test_starting_the_application_twice_in_a_day_writes_one_backup(
        self, dev_settings: Settings
    ) -> None:
        dev_settings.ensure_directories()
        run_migrations(dev_settings.resolved_database_url)

        for _ in range(2):
            with TestClient(
                create_app(dev_settings, clock=FrozenClock(TODAY))
            ) as client:
                assert client.get("/api/ready").status_code == 200

        assert len(backups_for_day(dev_settings.resolved_backups_dir, TODAY)) == 1


def test_frozen_clock_dates_are_used_for_the_day_bucket(tmp_path: Path) -> None:
    """A backup taken at a frozen date lands in that date's bucket."""
    path = tmp_path / "backups"
    path.mkdir()
    (path / f"{BACKUP_PREFIX}2026-03-01-090000{BACKUP_SUFFIX}").write_bytes(b"x")

    assert len(backups_for_day(path, date(2026, 3, 1))) == 1
    assert backups_for_day(path, date(2026, 3, 2)) == []
