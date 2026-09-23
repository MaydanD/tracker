"""Alembic migration tests: fresh database, Stage 1 upgrade, drift, reversibility."""

from __future__ import annotations

from alembic import command
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.db.database import Database, create_database, create_db_engine
from app.db.migrations import applied_revision, expected_revision, schema_status
from tests.helpers import (
    STAGE_1_REVISION,
    STAGE_2_REVISION,
    alembic_config,
    run_migrations,
    table_names,
)

STAGE_1_TABLES = {"app_metadata", "alembic_version"}
STAGE_2_TABLES = {"areas", "habits", "habit_versions"}


def _recorded_revision(database_url: str) -> str:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()


def _index_names(database_url: str, table: str) -> set[str]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            return {index["name"] for index in inspect(connection).get_indexes(table)}
    finally:
        engine.dispose()


def _check_constraints(database_url: str, table: str) -> set[str]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            return {
                constraint["name"]
                for constraint in inspect(connection).get_check_constraints(table)
            }
    finally:
        engine.dispose()


def _prepare(settings: Settings) -> str:
    settings.ensure_directories()
    return settings.resolved_database_url


class TestFreshDatabase:
    def test_upgrade_head_creates_every_table(self, settings: Settings) -> None:
        run_migrations(_prepare(settings))

        tables = set(table_names(settings.resolved_database_url))

        assert STAGE_1_TABLES <= tables
        assert STAGE_2_TABLES <= tables
        assert settings.resolved_database_path.exists()

    def test_upgrade_records_the_head_revision(self, settings: Settings) -> None:
        run_migrations(_prepare(settings))

        assert _recorded_revision(settings.resolved_database_url) == STAGE_2_REVISION

    def test_stage_two_schema_has_its_constraints_and_index(
        self, settings: Settings
    ) -> None:
        database_url = _prepare(settings)
        run_migrations(database_url)

        assert _index_names(database_url, "habit_versions") == {
            "ix_habit_versions_area_id"
        }
        assert _check_constraints(database_url, "habit_versions") == {
            "ck_habit_versions_weight_range",
            "ck_habit_versions_tracking_mode_values",
            "ck_habit_versions_quantity_unit_matches_mode",
            "ck_habit_versions_schedule_shape",
        }

    def test_migrations_are_idempotent(self, settings: Settings) -> None:
        database_url = _prepare(settings)
        run_migrations(database_url)
        run_migrations(database_url)

        assert STAGE_2_TABLES <= set(table_names(database_url))


class TestUpgradeFromStageOne:
    def test_stage_two_applies_on_top_of_a_stage_one_database(
        self, settings: Settings
    ) -> None:
        database_url = _prepare(settings)

        run_migrations(database_url, STAGE_1_REVISION)
        assert set(table_names(database_url)) == STAGE_1_TABLES
        assert _recorded_revision(database_url) == STAGE_1_REVISION

        run_migrations(database_url)
        assert STAGE_2_TABLES <= set(table_names(database_url))
        assert _recorded_revision(database_url) == STAGE_2_REVISION

    def test_stage_one_data_survives_the_upgrade(self, settings: Settings) -> None:
        """The Stage 1 marker row must still be there after migrating."""
        database_url = _prepare(settings)
        run_migrations(database_url, STAGE_1_REVISION)
        run_migrations(database_url)

        engine = create_db_engine(database_url)
        try:
            with engine.connect() as connection:
                marker = connection.execute(
                    text(
                        "SELECT value FROM app_metadata "
                        "WHERE key = 'schema_initialized_at'"
                    )
                ).scalar_one()
        finally:
            engine.dispose()

        assert marker


class TestModelDrift:
    def test_models_match_the_migrations(self, settings: Settings) -> None:
        """`alembic check` fails if models and migrations have drifted apart."""
        database_url = _prepare(settings)
        run_migrations(database_url)

        command.check(alembic_config(database_url))


class TestReversibility:
    def test_downgrade_to_stage_one_removes_stage_two_tables(
        self, settings: Settings
    ) -> None:
        database_url = _prepare(settings)
        run_migrations(database_url)

        command.downgrade(alembic_config(database_url), STAGE_1_REVISION)

        tables = set(table_names(database_url))
        assert not (STAGE_2_TABLES & tables)
        assert STAGE_1_TABLES <= tables

    def test_downgrade_to_base_then_upgrade_again(self, settings: Settings) -> None:
        database_url = _prepare(settings)
        run_migrations(database_url)

        command.downgrade(alembic_config(database_url), "base")
        assert "app_metadata" not in table_names(database_url)

        run_migrations(database_url)
        assert STAGE_2_TABLES <= set(table_names(database_url))


class TestSchemaStatus:
    """The schema check that turns "no such table" into an actionable message."""

    def test_pending_for_an_unmigrated_database(self, settings: Settings) -> None:
        settings.ensure_directories()
        unmigrated = create_database(settings)
        try:
            assert applied_revision(unmigrated) is None
            assert schema_status(unmigrated) == "pending"
        finally:
            unmigrated.dispose()

    def test_ok_once_migrated(self, database: Database) -> None:
        assert applied_revision(database) == STAGE_2_REVISION
        assert schema_status(database) == "ok"

    def test_expected_revision_is_the_stage_two_revision(self) -> None:
        """The code's expected head must match the newest migration on disk."""
        assert expected_revision() == STAGE_2_REVISION

    def test_pending_for_a_database_left_at_stage_one(self, settings: Settings) -> None:
        database_url = _prepare(settings)
        run_migrations(database_url, STAGE_1_REVISION)
        stage_one = create_database(settings)
        try:
            assert applied_revision(stage_one) == STAGE_1_REVISION
            assert schema_status(stage_one) == "pending"
        finally:
            stage_one.dispose()


class TestOfflineMode:
    def test_offline_mode_can_emit_sql(self, settings: Settings, capsys) -> None:
        """`alembic upgrade --sql` works without touching a database."""
        command.upgrade(alembic_config(settings.resolved_database_url), "head", sql=True)

        emitted = capsys.readouterr().out
        assert "CREATE TABLE app_metadata" in emitted
        assert "CREATE TABLE habit_versions" in emitted
        assert "ck_habit_versions_weight_range" in emitted
