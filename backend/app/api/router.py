"""Aggregate router for the whole API surface.

Stage 1 exposed the system endpoints; Stage 2 adds areas and habits.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import areas, habits, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(areas.router)
api_router.include_router(habits.router)
