"""Areas and versioned habit configuration.

Stage 2 introduces the first product tables:

* ``areas`` — a persistent life sphere (Health, Development, Work, Household),
  archived rather than deleted;
* ``habits`` — identity and lifecycle only;
* ``habit_versions`` — immutable, effective-dated configuration snapshots.

Configuration lives in ``habit_versions`` rather than on ``habits`` so that
historical records always resolve to the settings that were valid when they were
recorded. The ``habit_id``/``effective_from`` unique constraint enforces one
version per habit per calendar day: a same-day edit updates that day's version
instead of stacking duplicates, which is what makes "the latest version" and
"the version effective on date X" unambiguous.

No daily completion, state, score, insight or experiment tables are created in
Stage 2.

Revision ID: 8c12a1c62d83
Revises: 0001
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c12a1c62d83"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_areas")),
    )

    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habits")),
    )

    op.create_table(
        "habit_versions",
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
        # Structural rules are enforced by the database as well as by the domain
        # layer, so a bad configuration cannot be written by any path.
        sa.CheckConstraint("weight IN (1, 2, 3)", name=op.f("ck_habit_versions_weight_range")),
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
        sa.UniqueConstraint(
            "habit_id", "effective_from", name="habit_effective_date"
        ),
    )

    op.create_index(
        op.f("ix_habit_versions_area_id"),
        "habit_versions",
        ["area_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_habit_versions_area_id"), table_name="habit_versions")
    op.drop_table("habit_versions")
    op.drop_table("habits")
    op.drop_table("areas")
