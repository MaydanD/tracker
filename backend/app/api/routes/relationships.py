"""Explicit pair or bounded matrix; no implicit all-variable request."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import ClockDep, DbSession
from app.api.routes.descriptive import DescriptiveRoute
from app.domain.analytics.relationship_types import POLICY, RelationshipAnalytics
from app.schemas.relationships import RelationshipAnalyticsRead
from app.services.relationships import get_relationships


router = APIRouter(tags=["analytics"], route_class=DescriptiveRoute)


@router.get("/analytics/relationships", response_model=RelationshipAnalyticsRead,
            summary="Связи переменных на совпадающих датах или неделях")
def read_relationships(session: DbSession, clock: ClockDep,
                       start: date = Query(...), end: date = Query(...),
                       x: str | None = Query(None, min_length=1, max_length=160),
                       y: str | None = Query(None, min_length=1, max_length=160),
                       variables: list[str] | None = Query(None, min_length=2, max_length=POLICY.max_variables)
                       ) -> RelationshipAnalytics:
    try:
        if variables is not None:
            if x is not None or y is not None:
                raise ValueError("Укажите либо x и y, либо список variables.")
            keys, pair = tuple(variables), False
        else:
            if x is None or y is None:
                raise ValueError("Укажите обе переменные x и y или список variables.")
            keys, pair = (x, y), True
        return get_relationships(session, start, end, keys, today=clock.today(), pair=pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
