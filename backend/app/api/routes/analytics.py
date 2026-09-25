"""Read-only Stage 7A dataset endpoint."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.builder import validate_range
from app.domain.analytics.types import AnalyticsDataset
from app.schemas.analytics import AnalyticsDatasetRead
from app.services.analytics import get_dataset

router = APIRouter(tags=["analytics"])


@router.get("/analytics/dataset", response_model=AnalyticsDatasetRead,
            summary="Набор данных для аналитики")
def read_dataset(session: DbSession, clock: ClockDep,
                 start: date = Query(...), end: date = Query(...)) -> AnalyticsDataset:
    try:
        validate_range(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_dataset(session, start, end, today=clock.today())
