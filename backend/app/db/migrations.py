"""Migration-state inspection.

A local application is easy to break in one specific way: the code is updated
but the database is not. SQLite then answers queries with ``no such table``,
which surfaces as an opaque 500 error. Comparing the database's recorded Alembic
revision against the revision the code expects turns that into an actionable
message ("run ``alembic upgrade head``").

The head revision is read from the migration files themselves, so there is no
second list of revisions to keep in sync.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.database import Database

logger = get_logger(__name__)

SchemaStatus = Literal["ok", "pending", "unknown"]

# ``backend/alembic.ini`` — this file is ``backend/app/db/migrations.py``.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache(maxsize=1)
def expected_revision() -> str | None:
    """Revision the code expects, or ``None`` when it cannot be determined.

    A packaged desktop build may not ship the migration files; that is not an
    error, it only means readiness cannot check the schema.
    """
    if not ALEMBIC_INI.is_file():
        logger.debug("No alembic.ini at %s; skipping schema check", ALEMBIC_INI)
        return None

    # Imported lazily so the application can start without Alembic present.
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    try:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
        script = ScriptDirectory.from_config(config)
        return script.get_current_head()
    except Exception:  # pragma: no cover - defensive: unreadable migrations
        logger.warning("Could not read the Alembic script directory", exc_info=True)
        return None


def applied_revision(database: Database) -> str | None:
    """Revision recorded in the database.

    Returns ``None`` when the database has never been migrated. Raises
    :class:`sqlalchemy.exc.SQLAlchemyError` if the database cannot be queried.
    """
    with database.session() as session:
        migrated = session.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        ).first()
        if migrated is None:
            return None
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar()


def schema_status(database: Database) -> SchemaStatus:
    """Compare the database schema with the revision the code expects.

    ``unknown`` means the comparison could not be made (no migration files in the
    build), which is deliberately *not* treated as a failure.
    """
    expected = expected_revision()
    if expected is None:
        return "unknown"
    return "ok" if applied_revision(database) == expected else "pending"
