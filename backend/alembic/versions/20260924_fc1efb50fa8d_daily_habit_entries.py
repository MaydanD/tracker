"""Daily habit entries.

Stage 3 adds manual day-by-day tracking:

* ``daily_habit_entries`` — one row per habit per calendar date, holding the
  user\'s observation (``done`` / ``missed`` / ``skipped``), an optional exact
  quantity, an optional skip reason and an optional note.

Design notes that matter for the schema:

* ``UNIQUE (habit_id, entry_date)`` is the invariant behind "saving a day edits
  the existing record". Without it, a re-save could append a second row and the
  same day would be counted twice.
* ``quantity_value_micro`` is an integer number of millionths. SQLite has no
  decimal type and its numeric affinity goes through a binary float, so a
  ``REAL`` quantity would make ``6.4`` unrepresentable; the exact value is kept
  as an integer and converted with :class:`decimal.Decimal` in the domain layer.
  Six places is a deliberate bound: it exceeds any hand-recorded unit by orders
  of magnitude, and the largest scaled value (1 000 000 × 10^6 = 10^12) stays
  well inside a signed 64-bit column.
* The foreign key is ``ON DELETE RESTRICT``: recorded history must not disappear
  because a habit row was removed. Habits are archived, never deleted.
* ``skip_reason`` and ``status`` are kept consistent by a ``CHECK``, and the
  quantity has a non-negative ``CHECK``; the cross-table rule "a binary habit has
  no quantity" is enforced by the domain layer, because SQLite cannot express a
  check across two tables.

Configuration is deliberately *not* snapshotted onto an entry, and no
``habit_version_id`` is stored: "which unit and decimal rule applied that day?" is
already answered by ``habit_versions`` through the effective-dated lookup, and a
snapshot would fight the Stage 2 same-day-collapse rule.

Revision ID: fc1efb50fa8d
Revises: 8c12a1c62d83
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fc1efb50fa8d"
down_revision: str | None = "8c12a1c62d83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_habit_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        # Exact millionths of the historical quantity unit (see the module doc).
        sa.Column("quantity_value_micro", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("skip_reason", sa.String(length=200), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
    )

    # Day views read every entry of one date; the unique constraint already covers
    # lookups by habit, so only the date needs its own index.
    op.create_index(
        op.f("ix_daily_habit_entries_entry_date"),
        "daily_habit_entries",
        ["entry_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_daily_habit_entries_entry_date"), table_name="daily_habit_entries"
    )
    op.drop_table("daily_habit_entries")
