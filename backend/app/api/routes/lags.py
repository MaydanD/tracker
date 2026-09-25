"""One X/Y pair across explicitly selected, bounded calendar lags."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.lag_types import POLICY, LagAnalytics
from app.domain.analytics.lags import select_lags
from app.schemas.lags import LagAnalyticsRead
from app.services.lags import get_lags


class LagRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def localized_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(422, "Укажите корректные даты, переменные x/y и целые сдвиги от -7 до +7.") from exc

        return localized_handler


router = APIRouter(tags=["analytics"], route_class=LagRoute)


@router.get("/analytics/lags", response_model=LagAnalyticsRead,
            summary="Связи переменных со сдвигом во времени (период относится к Y)")
def read_lags(session: DbSession, clock: ClockDep,
              start: date = Query(...), end: date = Query(...),
              x: str = Query(..., min_length=1, max_length=160),
              y: str = Query(..., min_length=1, max_length=160),
              lag: int | None = Query(None, ge=-POLICY.max_absolute_lag, le=POLICY.max_absolute_lag),
              lags: list[int] | None = Query(None, min_length=1, max_length=POLICY.max_lag_values),
              lag_start: int | None = Query(None, ge=-POLICY.max_absolute_lag, le=POLICY.max_absolute_lag),
              lag_end: int | None = Query(None, ge=-POLICY.max_absolute_lag, le=POLICY.max_absolute_lag),
              ) -> LagAnalytics:
    try:
        selected = select_lags(lag=lag, lags=tuple(lags) if lags is not None else None,
                               lag_start=lag_start, lag_end=lag_end)
        return get_lags(session, start, end, x, y, selected, today=clock.today())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
