"""Allow a deliberate skip without a reason, preserving all existing entries."""

from alembic import context, op
from alembic.script import ScriptDirectory
import sqlalchemy as sa

revision = "a7c491de620b"
down_revision = "3f8a5c1d72be"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_daily_habit_entries_skip_reason_matches_status"


def upgrade():
    # Offline SQL has no connection to reflect. Reuse the frozen schema of the
    # revision that introduced value scales, never today's mutable ORM model.
    original = None
    if context.is_offline_mode():
        previous = ScriptDirectory.from_config(context.config).get_revision("5824a510506e").module
        original = sa.Table(
            "daily_habit_entries", sa.MetaData(),
            *previous._entry_columns(with_values=True),
            *previous._entry_constraints(with_values=True),
        )
        sa.Index("ix_daily_habit_entries_entry_date", original.c.entry_date)
    with op.batch_alter_table("daily_habit_entries", copy_from=original) as batch:
        batch.drop_constraint(op.f(CONSTRAINT), type_="check")
        batch.create_check_constraint(
            op.f(CONSTRAINT),
            "skip_reason IS NULL OR "
            "(status = 'skipped' AND length(trim(skip_reason)) > 0)",
        )


def downgrade():
    # Refuse to discard entries or invent reasons to fit the older contract.
    if op.get_bind().scalar(sa.text(
        "SELECT count(*) FROM daily_habit_entries "
        "WHERE status = 'skipped' AND skip_reason IS NULL"
    )):
        raise RuntimeError("Cannot downgrade while skips without reasons exist.")
    with op.batch_alter_table("daily_habit_entries") as batch:
        batch.drop_constraint(op.f(CONSTRAINT), type_="check")
        batch.create_check_constraint(
            op.f(CONSTRAINT),
            "(status = 'skipped' AND skip_reason IS NOT NULL "
            "AND length(trim(skip_reason)) > 0) OR "
            "(status <> 'skipped' AND skip_reason IS NULL)",
        )
