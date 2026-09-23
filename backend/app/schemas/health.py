"""Response schemas for the system endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: the process is up and serving requests."""

    status: Literal["ok"] = "ok"
    app: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness: the application can actually do its job (database reachable)."""

    status: Literal["ready", "unavailable"]
    checks: dict[str, str] = Field(
        default_factory=dict,
        description="Per-component result, e.g. {'database': 'ok'}.",
    )
