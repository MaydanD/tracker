"""FastAPI application factory.

``create_app`` is the single place where the application is assembled. The
module-level ``app`` exists so ``uvicorn app.main:app`` works unchanged, and so
a future pywebview shell can start the same ASGI app on a background thread.

Nothing touches the filesystem at import time: the data directory is created
during startup (lifespan) and the engine is lazy, so importing this module never
creates a database or a directory as a side effect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.config import Settings, get_settings, unknown_environment_variables
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.database import Database, create_database
from app.db.migrations import applied_revision, expected_revision, schema_status

logger = get_logger(__name__)


def log_schema_state(database: Database) -> None:
    """Report at startup whether the database is behind on migrations.

    Startup deliberately does not fail: ``/api/health`` must stay reachable so the
    UI can explain what is wrong, and ``/api/ready`` reports the pending migration
    as not ready.
    """
    try:
        status = schema_status(database)
    except SQLAlchemyError:
        logger.warning("Could not determine the database schema state", exc_info=True)
        return

    if status == "ok":
        logger.info("Database schema is up to date (%s)", expected_revision())
    elif status == "pending":
        logger.error(
            "Database schema is out of date (at %r, expected %r). "
            "Run 'alembic upgrade head' in backend/.",
            applied_revision(database),
            expected_revision(),
        )
    else:
        logger.info("Database schema state not checked (migration files unavailable)")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully configured FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    unrecognised = unknown_environment_variables()
    if unrecognised:
        logger.warning(
            "Ignoring unrecognised environment variables (typo?): %s",
            ", ".join(unrecognised),
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        logger.info(
            "%s backend starting (environment=%s, version=%s)",
            settings.app_name,
            settings.app_env,
            settings.app_version,
        )
        logger.info("Database: %s", settings.resolved_database_path)
        log_schema_state(app.state.database)
        try:
            yield
        finally:
            app.state.database.dispose()
            logger.info("%s backend stopped", settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local, single-user habit and daily-state tracker.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Bound on app.state before startup so dependencies resolve even when the
    # lifespan is not run (for example a route exercised directly in a test).
    app.state.settings = settings
    app.state.database = create_database(settings)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
