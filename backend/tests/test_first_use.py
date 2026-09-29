"""First-use reset is atomic, backed up and preserves operational settings."""

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app import maintenance
from app.db.models import AppMetadata, Area, Habit, HabitVersion
from app.services import areas, backup, canonical, habits
from tests.test_canonical_habits import plain_config
from tests.test_logical_backup import pack


FINAL_DIRECTIONS = {
    "body.exercise": "positive", "body.workout": "positive",
    "body.walk": "positive", "body.bicycle": "positive",
    "body.mood": "neutral", "body.energy": "neutral",
    "body.sleep_quality": "positive", "body.symptoms": "neutral",
    "body.sex": "neutral", "body.masturbation": "neutral",
    "development.reading": "positive", "development.study": "positive",
    "development.projects": "positive", "development.work": "neutral",
    "development.tasks": "positive", "leisure.friends": "positive",
    "leisure.games": "negative", "leisure.movies": "neutral",
    "leisure.computer": "neutral", "nutrition.normal_food": "positive",
    "nutrition.junk_food": "negative", "nutrition.overeating": "negative",
    "nutrition.coffee": "neutral", "nutrition.alcohol": "negative",
}


def assert_final_configuration(session, today):
    assert [(a.key, a.name) for a in session.scalars(select(Area).order_by(Area.sort_order))] == [
        ("body", "Тело"), ("development", "Развитие"), ("leisure", "Досуг"), ("nutrition", "Питание"),
    ]
    rows = list(session.scalars(select(Habit).order_by(Habit.sort_order)))
    assert len(rows) == 24
    assert {h.key: h.current_version.direction for h in rows} == FINAL_DIRECTIONS
    assert all(not h.is_archived for h in rows)
    versions = list(session.scalars(select(HabitVersion)))
    assert len(versions) == 24
    definitions = {h.key: h for h in canonical.CANONICAL_HABITS}
    for habit in rows:
        version = habit.current_version
        assert version.version_number == 1
        assert version.effective_from == today
        assert version.value_type == definitions[habit.key].value_type.value
        assert tuple(version.value_labels) == definitions[habit.key].labels
        assert version.weight == 1 and version.importance == "normal"
        assert version.tracking_mode == "binary"
        assert version.quantity_unit is None and not version.quantity_allows_decimal
        assert version.schedule_type == "daily"


def test_final_clean_reconcile_and_second_run(database, frozen_clock):
    with database.session() as session:
        canonical.reconcile_canonical(session, today=frozen_clock.today())
        assert_final_configuration(session, frozen_clock.today())
        before = backup.snapshot(session)
        assert not canonical.reconcile_canonical(session, today=frozen_clock.today()).changed
        assert backup.snapshot(session) == before
        assert_final_configuration(session, frozen_clock.today())


@pytest.fixture
def old_tracking(database, migrated_settings, frozen_clock):
    payload = json.loads((Path(__file__).parent / "fixtures/backup-v2.json").read_text(encoding="utf-8"))
    _, data = backup.validate_archive(pack(payload), migrated_settings)
    backup.restore(database, data, migrated_settings, frozen_clock.now())
    with database.session() as session:
        area = areas.create_area(session, name="Тестовая сфера")
        habit = habits.create_habit(session, plain_config(area.id, name="21312"),
                                    effective_date=frozen_clock.today() - timedelta(days=10))
        habits.archive_habit(session, habit.id)
        areas.archive_area(session, area.id)
        session.add_all([
            AppMetadata(key="backup_settings_v1", value='{"chat_id":"sentinel","auto_enabled":false}'),
            AppMetadata(key="future_operational_setting", value="keep"),
            AppMetadata(key="canonical_habits_initialized", value="2026-09-01"),
            AppMetadata(key=canonical.PARKED_ENTRIES_KEY, value=json.dumps([
                {"key": "body.walk", "entry_date": str(frozen_clock.today()), "value": 2},
            ])),
        ])
        session.commit()
    token = migrated_settings.resolved_data_dir / "telegram-token.secret"
    token.write_bytes(b"secret-sentinel")
    return token


def database_snapshot(database):
    with database.engine.connect() as connection:
        return {table.name: connection.execute(select(table).order_by(*table.primary_key.columns)).all()
                for table in AppMetadata.metadata.sorted_tables}


def test_reset_clears_all_history_and_keeps_settings(database, migrated_settings, frozen_clock, old_tracking):
    before = database_snapshot(database)
    result = maintenance.reset_tracking(database, migrated_settings, today=frozen_clock.today())
    assert all(result["before"][key] > 0 for key in result["before"])
    assert result["after"] == {"areas": 4, "habits": 24, "habit_versions": 24,
                               "daily_habit_entries": 0, "daily_states": 0,
                               "experiments": 0, "insight_snapshots": 0}
    with sqlite3.connect(result["backup"]) as saved:
        assert saved.execute('SELECT count(*) FROM daily_habit_entries').fetchone()[0] == result["before"]["daily_habit_entries"]
        assert saved.execute('PRAGMA integrity_check').fetchone()[0] == "ok"
    assert old_tracking.read_bytes() == b"secret-sentinel"
    with database.session() as session:
        assert_final_configuration(session, frozen_clock.today())
        assert session.get(AppMetadata, canonical.PARKED_ENTRIES_KEY) is None
        assert session.get(AppMetadata, "canonical_habits_initialized").value == str(frozen_clock.today())
        assert session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        snapshot = backup.snapshot(session)
        assert not canonical.reconcile_canonical(session, today=frozen_clock.today()).changed
        assert backup.snapshot(session) == snapshot
    after = database_snapshot(database)
    assert [row for row in before["app_metadata"] if row.key not in maintenance.TRACKING_METADATA] == [
        row for row in after["app_metadata"] if row.key not in maintenance.TRACKING_METADATA]


def test_failed_reconcile_rolls_back_deletions_and_service_commits(database, migrated_settings, frozen_clock, old_tracking, monkeypatch):
    before = database_snapshot(database)
    def fail_after_creation(session, *, today):
        canonical.reconcile_canonical(session, today=today)
        raise RuntimeError("seed failed")
    monkeypatch.setattr(maintenance, "reconcile_canonical", fail_after_creation)
    with pytest.raises(RuntimeError, match="seed failed"):
        maintenance.reset_tracking(database, migrated_settings, today=frozen_clock.today())
    assert database_snapshot(database) == before
    assert old_tracking.read_bytes() == b"secret-sentinel"


def test_failed_backup_does_not_delete_tracking(database, migrated_settings, frozen_clock, old_tracking, monkeypatch):
    before = database_snapshot(database)
    def fail_backup(*args):
        raise OSError("backup failed")
    monkeypatch.setattr(maintenance, "copy_sqlite_database", fail_backup)
    with pytest.raises(OSError, match="backup failed"):
        maintenance.reset_tracking(database, migrated_settings, today=frozen_clock.today())
    assert database_snapshot(database) == before
