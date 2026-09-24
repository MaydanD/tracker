"""Simple, SQLite-aware automatic backup.

Tracker keeps years of data in a single SQLite file, so the very first thing it
does with real usage is take a safety copy. This module does exactly that and
nothing more: no scheduler, no cloud, no restore UI, no integrity reporting.

**Why not ``shutil.copy``.** The database runs in WAL mode, which means recent
commits live in ``tracker.db-wal`` until a checkpoint. Copying only ``tracker.db``
during (or shortly after) a write therefore yields an *inconsistent* database, and
copying the ``-wal``/``-shm`` side files alongside it is racy by construction.
Instead this module uses SQLite's own online backup API
(:meth:`sqlite3.Connection.backup`), which reads the database through a real
connection: it takes a consistent snapshot, includes committed WAL content, and
is safe to run while the application holds the file open.

When it runs
------------
* once per application start, before the schema state is inspected, so the
  snapshot captures the state as it was found;
* at most one automatic backup per calendar day, enforced by looking for today's
  file name in the backup directory;
* never for in-memory databases (there is nothing on disk to protect) and never
  in the ``test`` environment, so a test run cannot litter real backup files.

Failures are logged loudly and reported through :class:`BackupOutcome`; a failed
backup never prevents the application from starting.

Two details exist purely so a broken backup can never masquerade as a good one:

* the target file is created with ``O_EXCL`` before SQLite opens it, so a name
  collision (two starts in the same second) fails instead of letting two writers
  interleave into one file;
* if the copy raises, the half-written file is removed, because a truncated file
  with a valid-looking name would be indistinguishable from a completed backup
  *and* would make :func:`backups_for_day` suppress today's retry.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.time import Clock
from app.db.database import Database

logger = get_logger(__name__)

BACKUP_PREFIX = "tracker-"
BACKUP_SUFFIX = ".db"

#: How many automatic backups to keep. One file per day means this is a couple of
#: weeks of history — enough to recover from a mistake noticed late, and bounded
#: so the folder cannot grow forever. Anything not matching the automatic naming
#: pattern is never touched.
BACKUP_RETENTION = 14

_AUTOMATIC_BACKUP_PATTERN = re.compile(
    rf"^{re.escape(BACKUP_PREFIX)}(\d{{4}}-\d{{2}}-\d{{2}})-(\d{{6}}){re.escape(BACKUP_SUFFIX)}$"
)


class BackupStatus(StrEnum):
    """Result of an attempted automatic backup."""

    CREATED = "created"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BackupOutcome:
    """What happened, reported rather than raised."""

    status: BackupStatus
    path: Path | None = None
    reason: str | None = None


def sqlite_database_file(database_url: str) -> Path | None:
    """The SQLite file behind ``database_url``, or ``None`` if there is none.

    Handles the two cases that must not produce a file: a non-SQLite database and
    an in-memory one (``sqlite://``, ``sqlite:///:memory:``).
    """
    try:
        url = make_url(database_url)
    except Exception:  # pragma: no cover - defensive: unparsable URL
        logger.warning("Could not parse the database URL for backup", exc_info=True)
        return None

    if not url.get_backend_name().startswith("sqlite"):
        return None

    database = url.database
    if not database or ":memory:" in database:
        return None
    return Path(database)


def backup_filename(moment: datetime) -> str:
    """Timestamped backup file name, e.g. ``tracker-2026-09-24-083045.db``."""
    return f"{BACKUP_PREFIX}{moment.strftime('%Y-%m-%d-%H%M%S')}{BACKUP_SUFFIX}"


def automatic_backups(backups_dir: Path) -> list[Path]:
    """Existing automatic backups, oldest first.

    Only files this module created are considered; anything else in the folder is
    left alone (and never deleted by retention).
    """
    if not backups_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in backups_dir.iterdir()
            if path.is_file() and _AUTOMATIC_BACKUP_PATTERN.match(path.name)
        ),
        key=lambda path: path.name,
    )


def backups_for_day(backups_dir: Path, day: date) -> list[Path]:
    """Automatic backups already taken on a calendar day."""
    prefix = f"{BACKUP_PREFIX}{day.isoformat()}-"
    return [
        path
        for path in automatic_backups(backups_dir)
        if path.name.startswith(prefix)
    ]


def copy_sqlite_database(source_path: Path, target_path: Path) -> None:
    """Write a consistent copy of a SQLite database using the online backup API.

    The copy is a complete, openable SQLite database. Because the snapshot is
    taken through a SQLite connection rather than at the filesystem level, WAL
    mode cannot make it inconsistent.

    The target must not exist. It is created exclusively first, then filled:
    SQLite treats a zero-length file as an empty database, so this both claims the
    name atomically and guarantees that an existing backup is never overwritten.
    A failure leaves no file behind.

    Raises :class:`FileExistsError` when the name is taken, and
    :class:`sqlite3.Error`/:class:`OSError` when the copy itself fails.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic claim of the name. `sqlite3.connect` alone would happily open an
    # existing backup file and write a second copy over it.
    os.close(os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))

    try:
        source = sqlite3.connect(str(source_path))
        try:
            target = sqlite3.connect(str(target_path))
            try:
                # Reads through a real connection: consistent snapshot, committed
                # WAL content included, no need to touch the -wal/-shm files.
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except BaseException:
        # Never leave a partial file: it would look like a finished backup and
        # would stop today's backup from being attempted again.
        target_path.unlink(missing_ok=True)
        raise


def _apply_retention(backups_dir: Path) -> None:
    """Delete the oldest automatic backups beyond :data:`BACKUP_RETENTION`."""
    backups = automatic_backups(backups_dir)
    for stale in backups[: max(len(backups) - BACKUP_RETENTION, 0)]:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover - defensive: locked or removed file
            logger.warning("Could not remove the old backup %s", stale, exc_info=True)


def run_startup_backup(
    database: Database,
    settings: Settings,
    *,
    clock: Clock,
) -> BackupOutcome:
    """Take today's automatic backup if it is due.

    Never raises: a broken backup must not stop the application from starting, but
    it must be visible in the log.
    """
    if settings.is_test:
        return BackupOutcome(
            status=BackupStatus.SKIPPED,
            reason="backups are disabled in the test environment",
        )

    source_path = sqlite_database_file(database.database_url)
    if source_path is None:
        return BackupOutcome(
            status=BackupStatus.SKIPPED,
            reason="the database is not a file-backed SQLite database",
        )

    backups_dir = settings.resolved_backups_dir
    today = clock.today()

    if backups_for_day(backups_dir, today):
        return BackupOutcome(
            status=BackupStatus.SKIPPED,
            reason=f"a backup for {today.isoformat()} already exists",
        )

    if not source_path.exists():
        return BackupOutcome(
            status=BackupStatus.SKIPPED,
            reason=f"the database file {source_path} does not exist yet",
        )

    target_path = backups_dir / backup_filename(clock.now())

    # Done before the collision-tolerant copy below: a backups *directory* that
    # cannot be created is a real failure, not something to report as "skipped".
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.error(
            "Automatic database backup failed; could not create %s",
            backups_dir,
            exc_info=True,
        )
        return BackupOutcome(
            status=BackupStatus.FAILED,
            path=target_path,
            reason="the backup directory could not be created",
        )

    try:
        copy_sqlite_database(source_path, target_path)
    except FileExistsError:
        # Another start claimed this exact name (same day, same second). The other
        # one is writing the same snapshot, so there is nothing left to do.
        logger.info("Backup file %s already exists; keeping it", target_path)
        return BackupOutcome(
            status=BackupStatus.SKIPPED,
            path=target_path,
            reason="a backup file with this name already exists",
        )
    except (OSError, sqlite3.Error):
        logger.error(
            "Automatic database backup failed; no backup was written for %s",
            today.isoformat(),
            exc_info=True,
        )
        return BackupOutcome(
            status=BackupStatus.FAILED,
            path=target_path,
            reason="the backup could not be written",
        )

    logger.info("Automatic database backup written to %s", target_path)
    _apply_retention(backups_dir)
    return BackupOutcome(status=BackupStatus.CREATED, path=target_path)
