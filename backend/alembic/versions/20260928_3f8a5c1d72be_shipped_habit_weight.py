"""Shipped habits carry the ordinary score weight, exactly as a fresh install.

Revision ID: 3f8a5c1d72be
Revises: 9e2c7b4a610f

Importance became an independent column in the previous revision, but the
canonical set had already been written while `weight` was still standing in for
it, so the twenty-four shipped rows were stored as weight 2 («Важная»). The same
user starting fresh now gets weight 1 («Обычная»), and weight 2 was never an
opinion about those habits — it was the abandoned mapping.

No stored evaluation moves: the score weighs habits against each other, and all
twenty-four shipped habits carry the same weight either way. This only makes an
upgraded database hold the same data as a fresh one.

Only the rows reconciliation owns are touched (a habit with a stable `key`), and
only while the configuration is still the shipped one — weight 2 with
`importance = 'normal'` — so a habit the user has edited is never rewritten.
"""

from alembic import op

revision = "3f8a5c1d72be"
down_revision = "9e2c7b4a610f"
branch_labels = None
depends_on = None


def upgrade():
    # 1 is the ordinary weight a habit created in the app gets; 2 is what the
    # canonical rows were written with while weight doubled as importance.
    op.execute(
        "UPDATE habit_versions SET weight = 1 "
        "WHERE weight = 2 AND importance = 'normal' "
        "AND habit_id IN (SELECT id FROM habits WHERE key IS NOT NULL)"
    )


def downgrade():
    # Restores the intermediate state rather than guessing: the opposite of the
    # update above, for the same rows under the same condition.
    op.execute(
        "UPDATE habit_versions SET weight = 2 "
        "WHERE weight = 1 AND importance = 'normal' "
        "AND habit_id IN (SELECT id FROM habits WHERE key IS NOT NULL)"
    )
