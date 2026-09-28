"""Stage 4 data survives upgrade and downgrade; CHECK SQL matches the ORM."""

from alembic import command
from sqlalchemy import CheckConstraint, inspect, text

from app.db.database import create_db_engine
from app.db.models import DailyState
from tests.helpers import STAGE_3_REVISION, alembic_config, run_migrations, table_names
from tests.test_migrations import TestUpgradeFromStageTwo as MigrationSeed


def test_stage_four_data_survives_roundtrip(settings):
    settings.ensure_directories()
    url = settings.resolved_database_url
    run_migrations(url, STAGE_3_REVISION)  # Stage 4 introduced no schema changes.
    MigrationSeed()._insert_stage_two_data(url)
    engine = create_db_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO daily_habit_entries (habit_id, entry_date, status, note, created_at, updated_at) VALUES (1, '2026-09-24', 'done', 'unchanged', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        # Columns that already existed, named explicitly: later revisions add
        # columns, so a bare SELECT * would compare different shapes rather than
        # the point of the test — that no stored value changed.
        columns = {
            "areas": "id, name, color, is_archived, archived_at, created_at, updated_at",
            "habits": "id, is_archived, archived_at, created_at, updated_at",
            "habit_versions": (
                "id, habit_id, version_number, effective_from, created_at, name, "
                "description, area_id, weight, tracking_mode, quantity_unit, "
                "quantity_allows_decimal, schedule_type, schedule_weekdays, "
                "schedule_times_per_week"
            ),
            "daily_habit_entries": (
                "id, habit_id, entry_date, quantity_value_micro, status, "
                "skip_reason, note, created_at, updated_at"
            ),
            "app_metadata": "*",
        }

        def snapshot():
            with engine.connect() as connection:
                return {
                    table: connection.execute(text(f"SELECT {expr} FROM {table}")).all()
                    for table, expr in columns.items()
                }

        before = snapshot()
        run_migrations(url)
        assert snapshot() == before
        command.check(alembic_config(url))
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO daily_states (state_date, mood, created_at, updated_at) VALUES ('2026-09-24', 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        command.downgrade(alembic_config(url), STAGE_3_REVISION)
        assert "daily_states" not in table_names(url)
        assert snapshot() == before
        run_migrations(url)
        command.check(alembic_config(url))
        assert snapshot() == before
    finally:
        engine.dispose()


def test_fresh_migration_constraints_match_orm(database):
    with database.engine.connect() as connection:
        actual = {item["name"]: item["sqltext"] for item in inspect(connection).get_check_constraints("daily_states")}
        expected = {item.name: str(item.sqltext) for item in DailyState.__table__.constraints if isinstance(item, CheckConstraint)}
        assert actual == expected
        assert inspect(connection).get_foreign_keys("daily_states") == []
        assert inspect(connection).get_unique_constraints("daily_states")[0]["column_names"] == ["state_date"]
