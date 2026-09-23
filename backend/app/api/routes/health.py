"""System endpoints: liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.api.dependencies import DatabaseDep, SettingsDep
from app.core.logging import get_logger
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import check_database

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
            "description": "The database is not reachable.",
        }
    },
    summary="Readiness probe",
)
def read_readiness(database: DatabaseDep) -> JSONResponse:
    """Check the database with a real query.

    A readiness probe reports *state*, so the failure path answers 503 with the
    same body shape as the success path (``checks.database``) instead of raising
    an error — the frontend can then show "database unavailable" without having
    to interpret an error envelope.
    """
    try:
        check_database(database)
    except SQLAlchemyError:
        logger.warning("Readiness check failed: database unavailable", exc_info=True)
        payload = ReadinessResponse(status="unavailable", checks={"database": "error"})
        return JSONResponse(status_code=503, content=payload.model_dump())

    payload = ReadinessResponse(status="ready", checks={"database": "ok"})
    return JSONResponse(status_code=200, content=payload.model_dump())
