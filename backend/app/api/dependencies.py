"""FastAPI dependency providers.

Everything is read from ``app.state`` so a test (or a future desktop shell) can
build an application with its own settings and database without touching a
module-level global.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import SYSTEM_CLOCK, Clock
from app.db.database import Database


def get_app_settings(request: Request) -> Settings:
    """Settings bound to the running application instance."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:  # pragma: no cover - defensive, factory always sets it
        raise RuntimeError("Application settings were not initialised.")
    return settings


def get_database(request: Request) -> Database:
    """Database container bound to the running application instance."""
    database = getattr(request.app.state, "database", None)
    if database is None:  # pragma: no cover - defensive, factory always sets it
        raise RuntimeError("Database was not initialised.")
    return database


def get_clock(request: Request) -> Clock:
    """The application clock, used for every "is this date in the future?" rule.

    Injected rather than read from ``datetime`` at the call site so tests can
    freeze "today" and so calendar logic is never scattered through services.
    """
    clock = getattr(request.app.state, "clock", None)
    return clock if clock is not None else SYSTEM_CLOCK


def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> Iterator[Session]:
    """Request-scoped SQLAlchemy session.

    The session is closed when the request finishes; writes are committed
    explicitly by the code performing them.
    """
    with database.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
DbSession = Annotated[Session, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]
