"""Database engine and session lifecycle.

One :class:`Database` instance is created per application instance and stored on
``app.state`` — there is deliberately no module-level global session. Sessions
are short-lived, request-scoped, and never shared between threads.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings

SQLITE_PREFIX = "sqlite"


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build an engine configured for Tracker's access patterns.

    SQLite gets ``NullPool`` plus ``check_same_thread=False``: a fresh
    connection per checkout keeps concurrent FastAPI worker threads away from
    the same underlying connection while still allowing the pool wrapper to
    exist. The connection cost is irrelevant for a single-user local app.
    """
    if database_url.startswith(SQLITE_PREFIX):
        engine = create_engine(
            database_url,
            echo=echo,
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
        _attach_sqlite_pragmas(engine)
        return engine
    return create_engine(database_url, echo=echo)


def _attach_sqlite_pragmas(engine: Engine) -> None:
    """Apply per-connection SQLite pragmas.

    ``foreign_keys`` is off by default in SQLite and must be set on every
    connection. ``busy_timeout`` avoids spurious "database is locked" failures
    when another connection (a backup task later on) touches the file.
    ``journal_mode=WAL`` is persistent in the database file and improves
    concurrent read/write behaviour.
    """

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


class Database:
    """Owns the engine and session factory for one application instance."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.database_url = database_url
        self.engine = create_db_engine(database_url, echo=echo)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session, rolling back on failure.

        Commits are left to the caller (route/service) so a request cannot
        accidentally persist a half-finished unit of work.
        """
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Release pooled connections (called on application shutdown)."""
        self.engine.dispose()


def create_database(settings: Settings) -> Database:
    """Build the application's database container from settings."""
    return Database(
        settings.resolved_database_url,
        echo=settings.log_level == "DEBUG",
    )
