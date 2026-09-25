"""Bounded, read-only descriptive analytics API."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.descriptive_types import POLICY, DescriptiveAnalytics
from app.schemas.descriptive import DescriptiveAnalyticsRead
from app.services.descriptive import get_descriptive


class DescriptiveRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def localized_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(422, "Укажите корректные даты начала и конца и список переменных.") from exc

        return localized_handler


router = APIRouter(tags=["analytics"], route_class=DescriptiveRoute)


@router.get("/analytics/descriptive", response_model=DescriptiveAnalyticsRead,
            summary="Описательная аналитика и динамика за период")
def read_descriptive(session: DbSession, clock: ClockDep,
                     start: date = Query(...), end: date = Query(...),
                     variables: list[str] = Query(..., min_length=1, max_length=POLICY.max_variables)
                     ) -> DescriptiveAnalytics:
    try:
        return get_descriptive(session, start, end, tuple(variables), today=clock.today())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
