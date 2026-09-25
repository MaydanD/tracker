"""One X/Y hypothesis (same-period or one lag) and its evidence quality."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.confidence_types import ConfidenceAnalytics
from app.domain.analytics.lag_types import POLICY as LAG_POLICY
from app.schemas.confidence import ConfidenceAnalyticsRead
from app.services.confidence import get_confidence


class ConfidenceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def localized_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(422, "Укажите корректные даты, переменные x/y и сдвиг от -7 до +7.") from exc

        return localized_handler


router = APIRouter(tags=["analytics"], route_class=ConfidenceRoute)


@router.get("/analytics/confidence", response_model=ConfidenceAnalyticsRead,
            summary="Подтверждённость связи X/Y имеющейся историей (сдвиг -7..+7)")
def read_confidence(session: DbSession, clock: ClockDep,
                    start: date = Query(...), end: date = Query(...),
                    x: str = Query(..., min_length=1, max_length=160),
                    y: str = Query(..., min_length=1, max_length=160),
                    lag: int = Query(0, ge=-LAG_POLICY.max_absolute_lag,
                                     le=LAG_POLICY.max_absolute_lag),
                    ) -> ConfidenceAnalytics:
    try:
        return get_confidence(session, start, end, x, y, lag=lag, today=clock.today())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
