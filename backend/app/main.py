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
import secrets
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.config import Settings, get_settings, unknown_environment_variables
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.time import SYSTEM_CLOCK, Clock
from app.db.backup import run_startup_backup
from app.db.database import Database, create_database
from app.db.migrations import applied_revision, expected_revision, schema_status
from app.services.backup_settings import try_automatic
from app.services.canonical import reconcile_canonical

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


def reconcile_canonical_habits(database: Database, *, clock: Clock) -> None:
    """Create the shipped habit set and retire what predates it.

    Idempotent and safe on both a fresh and an existing database: it creates the
    four spheres and the 24 habits through the ordinary area/habit services when
    they are missing, archives habit content that predates the shipped set (kept
    in full for history), and changes nothing else. A missing table (schema not
    migrated yet) is logged, not raised, so the app still starts and
    ``/api/ready`` can explain the real problem.
    """
    try:
        with database.session() as session:
            summary = reconcile_canonical(session, today=clock.today())
    except SQLAlchemyError:
        logger.warning("Could not reconcile the shipped habits", exc_info=True)
        return

    if summary.areas_created or summary.habits_created:
        logger.info(
            "Canonical habits reconciled (%s areas, %s habits created)",
            summary.areas_created,
            summary.habits_created,
        )
    if summary.legacy_habits_archived or summary.legacy_areas_archived:
        logger.info(
            "Retired pre-canonical habit content (%s habits, %s areas archived, "
            "history kept)",
            summary.legacy_habits_archived,
            summary.legacy_areas_archived,
        )
    if summary.parked_entries_adopted:
        logger.info(
            "Adopted %s recorded answers from the previous value-scale tables",
            summary.parked_entries_adopted,
        )


def create_app(settings: Settings | None = None, *, clock: Clock | None = None) -> FastAPI:
    """Build a fully configured FastAPI application.

    ``clock`` supplies "today" for every calendar rule. Tests pass a frozen clock
    instead of patching ``datetime``; production uses the machine's local date.
    """
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
        # Before anything opens the database: snapshot what was found on disk.
        # Backs itself out for in-memory databases, test environments and a
        # database that does not exist yet, and never raises.
        run_startup_backup(app.state.database, settings, clock=app.state.clock)
        log_schema_state(app.state.database)
        # The user must never create the shipped habits by hand: reconcile the
        # exact 24-habit set on every start, idempotently. Skipped under test,
        # where every database is a fixture that states its own habits.
        if settings.app_env != "test":
            reconcile_canonical_habits(app.state.database, clock=app.state.clock)
        auto_backup = asyncio.create_task(asyncio.to_thread(
            try_automatic, app.state.database, settings, app.state.clock))
        try:
            yield
        finally:
            await auto_backup
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
            expose_headers=["Content-Disposition"],
        )

    # Bound on app.state before startup so dependencies resolve even when the
    # lifespan is not run (for example a route exercised directly in a test).
    app.state.settings = settings
    app.state.clock = clock if clock is not None else SYSTEM_CLOCK
    app.state.database = create_database(settings)
    # Restarting the process requires a new preview, no persistent tokens.
    app.state.backup_signing_key = secrets.token_bytes(32)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
