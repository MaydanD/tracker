"""habit value scales, importance order and stable keys

Extends the ordinary habit model so a habit can be answered with a value instead
of a completion, which is what the daily check-in now records:

* ``habits.key`` — a stable machine identifier (``body.walk``) of a habit Tracker
  created itself, used only so reconciliation recognises its own rows; ``NULL``
  for a habit the user created by hand;
* ``habits.sort_order`` / ``areas.sort_order`` — the position the user sees,
  ``0`` meaning "no position of its own" (ordered by name, as before);
* ``habit_versions.value_type`` / ``value_labels`` / ``direction`` — the scale a
  day is answered on, the words of that scale, and which end of it is good;
* ``daily_habit_entries.value`` — the recorded answer, where ``0`` is a real
  answer and only a missing row means "not recorded".

Weight retains its historical semantics. Independent importance is added by
the following revision, including databases already at this intermediate head.

All of it is configuration *of a version*, so a historical day keeps the scale,
the labels, the direction and the importance that were in force then. No habit,
version, entry or daily-state row is modified: the new columns are nullable (or
defaulted to ``0``), and every existing row is copied into the rebuilt tables
untouched.

The habits themselves are created by ``app.services.canonical`` at startup, not
here, so a fresh database and an existing one converge on the same 24 habits
idempotently.

Rebuilding ``habit_versions`` and ``daily_habit_entries``
--------------------------------------------------------

SQLite can add a column but not a ``CHECK`` constraint, so a table that gains a
constraint has to be rebuilt: renamed aside, recreated and refilled. That is
spelled out here rather than left to Alembic's batch mode, because batch mode
reflects the live table — which would make ``alembic upgrade head --sql``
impossible, and that is the supported way to read this project's DDL without a
database.

The rebuild is safe with foreign keys enabled (how the application opens the
database) because both tables are leaves: habits, areas, entries and versions
point *at* other tables, and nothing points at these two. The same reasoning is
why ``areas`` and ``habits`` are only altered in place: rebuilding either of
those would detach the versions and entries that reference them, and a unique
*index* can be created on a populated table where a UNIQUE constraint cannot.

Revision ID: 5824a510506e
Revises: c3f1a7b24d90
Create Date: 2026-09-28
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "5824a510506e"
down_revision: str | None = "c3f1a7b24d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables of the uncommitted value-scale prototype that stored scales in
#: parallel ``indicator_*`` tables. They are replaced by the habit columns added
#: below; a database that never saw them (every fresh one) skips this entirely.
LEGACY_TABLES = (
    "indicator_versions",
    "daily_indicator_entries",
    "indicators",
    "indicator_areas",
)

#: Where recorded answers of that prototype are parked for the service to adopt.
#: The canonical habits do not exist yet at migration time, so the answers wait
#: here until the first reconciliation writes them into the right habit.
PARKING_KEY = "legacy_indicator_entries"

HABIT_VERSIONS = "habit_versions"
DAILY_ENTRIES = "daily_habit_entries"


def upgrade() -> None:
    _add_key_and_order()
    _rebuild_habit_versions(with_values=True)
    _rebuild_daily_entries(with_values=True)
    _retire_legacy_tables()


def downgrade() -> None:
    if PARKING_KEY in _parked_keys():
        op.get_bind().execute(
            sa.text("DELETE FROM app_metadata WHERE key = :key"), {"key": PARKING_KEY}
        )

    _rebuild_daily_entries(with_values=False)
    _rebuild_habit_versions(with_values=False)

    op.drop_index("uq_habits_key", table_name="habits")
    op.drop_column("habits", "sort_order")
    op.drop_column("habits", "key")

    op.drop_index("uq_areas_key", table_name="areas")
    op.drop_column("areas", "sort_order")
    op.drop_column("areas", "key")


# ---------------------------------------------------------------------------
# In-place changes
# ---------------------------------------------------------------------------


def _add_key_and_order() -> None:
    """A stable machine key and a display position for areas and habits.

    Both changes are in place on SQLite: a nullable column, a column with a
    default, and an index. ``sort_order`` keeps its ``0`` default — on a
    populated table the existing rows are exactly the ones with no position of
    their own.
    """
    for table in ("areas", "habits"):
        op.add_column(table, sa.Column("key", sa.String(length=64), nullable=True))
        op.add_column(
            table,
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index(f"uq_{table}_key", table, ["key"], unique=True)


# ---------------------------------------------------------------------------
# The two rebuilt tables
# ---------------------------------------------------------------------------
# The pre-revision shapes below mirror the revisions that created the tables
# (8c12a1c62d83 for habit_versions, fc1efb50fa8d for daily_habit_entries). They
# describe history and must not be edited afterwards: a running migration sees
# the table exactly as those revisions left it.


def _habit_version_columns(*, with_values: bool) -> list[sa.Column[Any]]:
    """Every column of ``habit_versions``, with or without the value scale."""
    columns: list[sa.Column[Any]] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("tracking_mode", sa.String(length=24), nullable=False),
        sa.Column("quantity_unit", sa.String(length=32), nullable=True),
        sa.Column("quantity_allows_decimal", sa.Boolean(), nullable=False),
        sa.Column("schedule_type", sa.String(length=24), nullable=False),
        sa.Column("schedule_weekdays", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("schedule_times_per_week", sa.Integer(), nullable=True),
    ]
    if with_values:
        columns += [
            sa.Column("value_type", sa.String(length=16), nullable=True),
            sa.Column("value_labels", sa.JSON(none_as_null=True), nullable=True),
            sa.Column("direction", sa.String(length=16), nullable=True),
        ]
    return columns


def _habit_version_constraints(*, with_values: bool) -> list[Any]:
    """Every constraint of ``habit_versions``, with or without the value scale."""
    constraints: list[Any] = [
        sa.CheckConstraint(
            "weight IN (1, 2, 3)", name=op.f("ck_habit_versions_weight_range")
        ),
        sa.CheckConstraint(
            "tracking_mode IN ('binary', 'binary_quantity')",
            name=op.f("ck_habit_versions_tracking_mode_values"),
        ),
        sa.CheckConstraint(
            "(tracking_mode = 'binary' AND quantity_unit IS NULL) OR "
            "(tracking_mode = 'binary_quantity' AND quantity_unit IS NOT NULL)",
            name=op.f("ck_habit_versions_quantity_unit_matches_mode"),
        ),
        sa.CheckConstraint(
            "(schedule_type = 'daily' AND schedule_weekdays IS NULL "
            "AND schedule_times_per_week IS NULL) OR "
            "(schedule_type = 'weekdays' AND schedule_weekdays IS NOT NULL "
            "AND schedule_times_per_week IS NULL) OR "
            "(schedule_type = 'times_per_week' AND schedule_weekdays IS NULL "
            "AND schedule_times_per_week BETWEEN 1 AND 7)",
            name=op.f("ck_habit_versions_schedule_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["area_id"],
            ["areas.id"],
            name=op.f("fk_habit_versions_area_id_areas"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["habit_id"],
            ["habits.id"],
            name=op.f("fk_habit_versions_habit_id_habits"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habit_versions")),
        sa.UniqueConstraint("habit_id", "effective_from", name="habit_effective_date"),
    ]
    if with_values:
        # A habit either tracks completion (no scale at all) or is answered on a
        # value scale, in which case the scale, its labels and a direction are
        # all present: half-configured scales cannot be stored.
        constraints += [
            sa.CheckConstraint(
                "(value_type IS NULL AND value_labels IS NULL AND direction IS NULL) OR "
                "(value_type IN ('binary', 'ordinal_4') "
                "AND value_labels IS NOT NULL AND direction IS NOT NULL)",
                name=op.f("ck_habit_versions_value_scale_shape"),
            ),
            sa.CheckConstraint(
                "direction IS NULL OR direction IN ('positive', 'negative', 'neutral')",
                name=op.f("ck_habit_versions_direction_values"),
            ),
        ]
    return constraints


def _entry_columns(*, with_values: bool) -> list[sa.Column[Any]]:
    """Every column of ``daily_habit_entries``, with or without the answer."""
    columns: list[sa.Column[Any]] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        # Exact millionths of the historical quantity unit (see revision
        # fc1efb50fa8d).
        sa.Column("quantity_value_micro", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("skip_reason", sa.String(length=200), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]
    if with_values:
        columns.append(sa.Column("value", sa.Integer(), nullable=True))
    return columns


def _entry_constraints(*, with_values: bool) -> list[Any]:
    """Every constraint of ``daily_habit_entries``, with or without the answer."""
    constraints: list[Any] = [
        sa.CheckConstraint(
            "status IN ('done', 'missed', 'skipped')",
            name=op.f("ck_daily_habit_entries_status_values"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped' AND skip_reason IS NOT NULL "
            "AND length(trim(skip_reason)) > 0) OR "
            "(status <> 'skipped' AND skip_reason IS NULL)",
            name=op.f("ck_daily_habit_entries_skip_reason_matches_status"),
        ),
        sa.CheckConstraint(
            "quantity_value_micro IS NULL OR quantity_value_micro >= 0",
            name=op.f("ck_daily_habit_entries_quantity_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["habit_id"],
            ["habits.id"],
            name=op.f("fk_daily_habit_entries_habit_id_habits"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_habit_entries")),
        sa.UniqueConstraint("habit_id", "entry_date", name="habit_entry_date"),
    ]
    if with_values:
        # ``0`` is an answer (нет, no coffee), so only NULL means "not recorded",
        # and the answer must be a whole number on one of the two scales.
        constraints.append(
            sa.CheckConstraint(
                "value IS NULL OR (typeof(value) = 'integer' AND value BETWEEN 0 AND 3)",
                name=op.f("ck_daily_habit_entries_value_range"),
            )
        )
    return constraints


def _rebuild_habit_versions(*, with_values: bool) -> None:
    """Add or remove the value scale of a habit version, keeping every row."""
    _rebuild(
        HABIT_VERSIONS,
        columns=_habit_version_columns(with_values=with_values),
        constraints=_habit_version_constraints(with_values=with_values),
        copy=[column.name for column in _habit_version_columns(with_values=False)],
        indexes=[("ix_habit_versions_area_id", ["area_id"])],
    )


def _rebuild_daily_entries(*, with_values: bool) -> None:
    """Add or remove the recorded answer of a day, keeping every row."""
    _rebuild(
        DAILY_ENTRIES,
        columns=_entry_columns(with_values=with_values),
        constraints=_entry_constraints(with_values=with_values),
        copy=[column.name for column in _entry_columns(with_values=False)],
        indexes=[("ix_daily_habit_entries_entry_date", ["entry_date"])],
    )


def _rebuild(
    table: str,
    *,
    columns: list[sa.Column[Any]],
    constraints: list[Any],
    copy: list[str],
    indexes: list[tuple[str, list[str]]],
) -> None:
    """Recreate ``table`` with a different definition and refill it.

    Written out rather than delegated to Alembic's batch mode so that it also
    renders as SQL without a database (see the module docstring). The rows are
    copied verbatim; the only columns that differ are the ones being added or
    removed, and those are nullable.
    """
    for name, _ in indexes:
        op.drop_index(name, table_name=table)

    previous = f"{table}__previous"
    op.rename_table(table, previous)
    op.create_table(table, *columns, *constraints)

    names = ", ".join(f'"{name}"' for name in copy)
    op.execute(f'INSERT INTO "{table}" ({names}) SELECT {names} FROM "{previous}"')

    # Dropping the renamed table also drops the indexes it carried, which is why
    # they are named here instead of being copied along.
    op.drop_table(previous)
    for name, index_columns in indexes:
        op.create_index(name, table, index_columns, unique=False)


# ---------------------------------------------------------------------------
# The retired value-scale prototype
# ---------------------------------------------------------------------------


def _retire_legacy_tables() -> None:
    """Drop the prototype's tables, after parking the answers they hold."""
    if op.get_context().as_sql:
        # A SQL script cannot be inspected or read from: emit the safest
        # complete script instead of guessing whether the tables exist. The
        # parked answers (below) need a live database, so they are simply not
        # part of an offline run.
        for table in LEGACY_TABLES:
            op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
        return

    bind = op.get_bind()
    present = set(sa.inspect(bind).get_table_names())
    if "daily_indicator_entries" in present and "indicators" in present:
        _park_answers(bind)

    for table in LEGACY_TABLES:
        if table in present:
            op.drop_table(table)


def _park_answers(bind: sa.Connection) -> None:
    """Copy the prototype's recorded answers into ``app_metadata`` as JSON."""
    rows = (
        bind.execute(
            sa.text(
                "SELECT i.key AS habit_key, e.entry_date AS entry_date, "
                "e.value AS value, e.note AS note "
                "FROM daily_indicator_entries AS e "
                "JOIN indicators AS i ON i.id = e.indicator_id"
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return

    payload = json.dumps(
        [
            {
                "key": row["habit_key"],
                "entry_date": str(row["entry_date"]),
                "value": int(row["value"]),
                "note": row["note"],
            }
            for row in rows
        ],
        ensure_ascii=False,
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    bind.execute(
        sa.text(
            "INSERT INTO app_metadata (key, value, created_at, updated_at) "
            "VALUES (:key, :value, :now, :now)"
        ),
        {"key": PARKING_KEY, "value": payload, "now": now},
    )


def _parked_keys() -> set[str]:
    """Keys already present in ``app_metadata`` (used by the downgrade)."""
    return {
        row[0] for row in op.get_bind().execute(sa.text("SELECT key FROM app_metadata"))
    }
