"""System endpoints: liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.api.dependencies import DatabaseDep, SettingsDep
from app.core.logging import get_logger
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import check_database, check_schema

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def read_health(settings: SettingsDep) -> HealthResponse:
    """Return 200 as long as the process is alive and serving requests."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "model": ReadinessResponse,
            "description": "The database is unreachable or its schema is out of date.",
        }
    },
    summary="Readiness probe",
)
def read_readiness(database: DatabaseDep) -> JSONResponse:
    """Check that the application can actually do its job.

    Two things are verified: the database answers a real query, and its schema
    matches the revision this code expects. A readiness probe reports *state*, so
    the failure path answers 503 with the same body shape as the success path
    (``checks``) instead of raising an error — the frontend can then explain what
    is wrong without interpreting an error envelope.

    A database that is behind on migrations is a genuine not-ready state: product
    endpoints would fail with "no such table", so reporting it here turns an
    opaque 500 into an actionable message.
    """
    try:
        check_database(database)
        schema = check_schema(database)
    except SQLAlchemyError:
        logger.warning("Readiness check failed: database unavailable", exc_info=True)
        payload = ReadinessResponse(status="unavailable", checks={"database": "error"})
        return JSONResponse(status_code=503, content=payload.model_dump())

    if schema == "pending":
        logger.error(
            "Readiness check failed: database schema is out of date. "
            "Run 'alembic upgrade head' in backend/."
        )
        payload = ReadinessResponse(
            status="unavailable", checks={"database": "ok", "migrations": "pending"}
        )
        return JSONResponse(status_code=503, content=payload.model_dump())

    payload = ReadinessResponse(
        status="ready", checks={"database": "ok", "migrations": schema}
    )
    return JSONResponse(status_code=200, content=payload.model_dump())
