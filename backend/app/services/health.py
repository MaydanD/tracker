"""System/health services.

Kept separate from the HTTP layer so the checks are directly testable and can be
reused later (for example by a desktop startup splash screen).
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.database import Database
from app.db.migrations import SchemaStatus, schema_status


def check_database(database: Database) -> None:
    """Verify the database is genuinely usable.

    Runs a real query through the same session lifecycle the API uses, so a
    missing file, a bad path, or a locked/corrupt database all surface here.
    Raises :class:`sqlalchemy.exc.SQLAlchemyError` on failure.
    """
    with database.session() as session:
        session.execute(text("SELECT 1"))


def check_schema(database: Database) -> SchemaStatus:
    """Report whether the database schema matches the code.

    A migrated-but-reachable database still cannot serve product endpoints when
    the schema is behind, so readiness reports that separately from
    connectivity. Raises :class:`sqlalchemy.exc.SQLAlchemyError` if the check
    itself cannot be performed.
    """
    return schema_status(database)
