"""Aggregate router for the whole API surface.

Stage 1 exposes only the system endpoints. Stage 2+ adds one router per
resource area (areas, habits, entries, ...) and includes it here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
