"""Aggregate router for the whole API surface.

Stage 1 exposed the system endpoints; Stage 2 added areas and habits; Stage 3
adds daily tracking.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import areas, daily, habits, health, progress

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(areas.router)
api_router.include_router(habits.router)
api_router.include_router(daily.router)
api_router.include_router(progress.router)
