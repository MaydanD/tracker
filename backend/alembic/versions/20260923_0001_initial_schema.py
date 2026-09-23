"""Initial schema: infrastructure tables only.

Stage 1 deliberately creates no product entities. ``app_metadata`` gives the
migration pipeline a real table and lets the application prove database access.

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_metadata")),
    )

    # A single marker row: proves migrations ran against a writable database.
    op.execute(
        sa.text(
            "INSERT INTO app_metadata (key, value, created_at, updated_at) VALUES "
            "('schema_initialized_at', "
            "strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
