"""Independent versioned importance; preserve every historical weight and entry.

Revision ID: 9e2c7b4a610f
Revises: 5824a510506e
"""
from alembic import op
import sqlalchemy as sa

revision = "9e2c7b4a610f"
down_revision = "5824a510506e"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite accepts a checked ADD COLUMN in place; no table rebuild or row loss.
    op.add_column("habit_versions", sa.Column(
        "importance", sa.String(16),
        sa.CheckConstraint("importance IN ('low', 'normal', 'high')",
                           name=op.f("ck_habit_versions_importance_values")),
        nullable=False, server_default="normal",
    ))


def downgrade():
    op.drop_column("habit_versions", "importance")
