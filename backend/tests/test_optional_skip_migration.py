"""Optional reasons preserve existing data and database constraints."""

import pytest
from alembic import command
from sqlalchemy import CheckConstraint, inspect, text

from app.db.database import create_db_engine
from app.db.models import DailyHabitEntry
from tests.helpers import STAGE_3_REVISION, alembic_config, run_migrations
from tests.test_migrations import TestUpgradeFromStageTwo as MigrationSeed


def test_optional_skip_upgrade_preserves_data_and_supports_safe_downgrade(settings):
    settings.ensure_directories()
    url = settings.resolved_database_url
    run_migrations(url, STAGE_3_REVISION)
    MigrationSeed()._insert_stage_two_data(url)
    run_migrations(url, "3f8a5c1d72be")
    engine = create_db_engine(url)
    try:
        with engine.begin() as connection:
            for day, status, reason, value, quantity in [
                (24, 'done', None, 0, None),
                (25, 'skipped', 'поездка', None, None),
                (26, 'done', None, None, 12500000),
            ]:
                connection.execute(text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "skip_reason, value, quantity_value_micro, note, created_at, updated_at) "
                    "VALUES (1, :day, :status, :reason, :value, :quantity, 'keep', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ), dict(day=f'2026-09-{day}', status=status, reason=reason, value=value, quantity=quantity))

        def snapshot():
            with engine.connect() as connection:
                return {table: connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).all()
                        for table in ('areas', 'habits', 'habit_versions', 'daily_habit_entries')}

        before = snapshot()
        run_migrations(url)
        assert snapshot() == before
        command.check(alembic_config(url))
        with engine.connect() as connection:
            assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
            assert connection.execute(text('PRAGMA integrity_check')).scalar() == 'ok'
        command.downgrade(alembic_config(url), '3f8a5c1d72be')
        assert snapshot() == before
        run_migrations(url)
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO daily_habit_entries (habit_id, entry_date, status, created_at, updated_at) "
                "VALUES (1, '2026-09-27', 'skipped', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
        with pytest.raises(RuntimeError, match='without reasons'):
            command.downgrade(alembic_config(url), '3f8a5c1d72be')
        with engine.connect() as connection:
            assert connection.execute(text('SELECT count(*) FROM daily_habit_entries')).scalar() == 4
    finally:
        engine.dispose()


def test_optional_skip_check_matches_orm(database):
    with database.engine.connect() as connection:
        actual = {item['name']: item['sqltext'] for item in inspect(connection).get_check_constraints('daily_habit_entries')}
    expected = {item.name: str(item.sqltext) for item in DailyHabitEntry.__table__.constraints
                if isinstance(item, CheckConstraint)}
    assert actual == expected
