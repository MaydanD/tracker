"""System/health services.

Kept separate from the HTTP layer so the checks are directly testable and can be
reused later (for example by a desktop startup splash screen).
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.database import Database


def check_database(database: Database) -> None:
    """Verify the database is genuinely usable.

    Runs a real query through the same session lifecycle the API uses, so a
    missing file, a bad path, or a locked/corrupt database all surface here.
    Raises :class:`sqlalchemy.exc.SQLAlchemyError` on failure.
    """
    with database.session() as session:
        session.execute(text("SELECT 1"))
