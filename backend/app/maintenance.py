"""Explicit offline first-use reset; never called by startup or an HTTP route.

Stop Tracker before running ``python -m app.maintenance --reset-tracking``.
Operational metadata and files (including Telegram credentials) stay intact.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from uuid import uuid4

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import today_local
from app.db.backup import copy_sqlite_database, sqlite_database_file
from app.db.database import Database, create_database
from app.db.migrations import schema_status
from app.db.models import (AppMetadata, Area, DailyHabitEntry, DailyState,
                           Experiment, Habit, HabitVersion, InsightSnapshot)
from app.services.canonical import PARKED_ENTRIES_KEY, reconcile_canonical

# Child rows first. No FK disabling and no deletion of the database/schema.
TRACKING_MODELS = (InsightSnapshot, Experiment, DailyState, DailyHabitEntry,
                   HabitVersion, Habit, Area)
TRACKING_METADATA = ("canonical_habits_initialized", PARKED_ENTRIES_KEY)


def reset_tracking(database: Database, settings: Settings, *, today: date) -> dict:
    """Back up, clear tracking data and reconcile in one outer transaction.

    Ordinary services commit their own work. Savepoints keep those commits
    inside this reset, so a failed seed also restores the deleted history.
    """
    source = sqlite_database_file(database.database_url)
    if source is None or not source.is_file() or schema_status(database) != "ok":
        raise ValueError("First-use reset requires an existing, migrated SQLite database.")
    expected = {model.__tablename__ for model in TRACKING_MODELS} | {"app_metadata", "alembic_version"}
    unknown = set(inspect(database.engine).get_table_names()) - expected
    if unknown:
        raise ValueError(f"Inspect additional tables before resetting: {sorted(unknown)}")
    safety = settings.resolved_backups_dir / f"tracker-before-first-use-{today}-{uuid4().hex}.db"
    with database.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            copy_sqlite_database(source, safety)
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                before = _counts(session)
                for model in TRACKING_MODELS:
                    session.execute(delete(model))
                session.execute(delete(AppMetadata).where(AppMetadata.key.in_(TRACKING_METADATA)))
                session.commit()
                reconcile_canonical(session, today=today)
                after = _counts(session)
                expected_counts = {
                    "areas": 4, "habits": 24, "habit_versions": 24,
                    "daily_habit_entries": 0, "daily_states": 0,
                    "experiments": 0, "insight_snapshots": 0,
                }
                if after != expected_counts:
                    raise ValueError(f"Unexpected counts after reset: {after}")
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Foreign key check failed after reset.")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {"backup": str(safety), "before": before, "after": after}


def _counts(session: Session) -> dict[str, int]:
    return {model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in TRACKING_MODELS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset-tracking", action="store_true", required=True,
                        help="Delete all tracking history and recreate the canonical set.")
    parser.parse_args()
    settings = Settings()
    database = create_database(settings)
    try:
        print(json.dumps(reset_tracking(database, settings, today=today_local()), indent=2))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
