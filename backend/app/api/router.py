"""Aggregate router for the whole API surface.

Stage 1 exposed the system endpoints; Stage 2 added areas and habits; Stage 3
adds daily tracking; Stage 4 adds progress/scoring; Stage 5 adds daily state;
Stage 6 adds dashboard and calendar aggregations.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import analytics, areas, daily, daily_state, dashboard, descriptive, habits, health, progress
from app.api.routes import confidence, lags, relationships

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(areas.router)
api_router.include_router(habits.router)
api_router.include_router(daily.router)
api_router.include_router(progress.router)
api_router.include_router(daily_state.router)
api_router.include_router(dashboard.router)
api_router.include_router(analytics.router)
api_router.include_router(descriptive.router)
api_router.include_router(relationships.router)
api_router.include_router(lags.router)
api_router.include_router(confidence.router)
