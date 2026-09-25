"""Stage 8 insights: an aggregated feed, one detail view, history and refresh.

The feed is aggregated on purpose: opening the page is one request, not one
request per card. Only opening a specific insight asks for a second one, and it
already carries its charts and its history.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.confidence_types import ConfidenceLevel
from app.domain.analytics.guardrail_types import GuardrailVerdict
from app.domain.analytics.insight_types import (
    DISCOVERY_POLICY, InsightAnalytics, InsightCatalogue, InsightDetail, InsightRefreshResult,
    InsightSnapshotRead,
)
from app.domain.errors import InsightRequestError
from app.schemas.insights import (
    InsightAnalyticsRead, InsightCatalogueRead, InsightDetailRead, InsightHistoryRead,
    InsightRefreshRead, InsightRefreshRequest,
)
from app.services.insights import InsightRequest, get_catalogue, get_detail, get_history, get_insights, refresh


CONFIDENCE_LEVELS: tuple[ConfidenceLevel, ...] = ("preliminary", "stable", "well_supported")
VERDICTS: tuple[GuardrailVerdict, ...] = ("pass", "pass_with_warnings", "blocked", "not_evaluable")

LAG_MAX = 7


class InsightRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def localized_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(
                    422, "Укажите корректные даты, период от 7 до 730 дней и понятные "
                         "параметры аналитики.") from exc

        return localized_handler


router = APIRouter(tags=["analytics"], route_class=InsightRoute)


def _checked(values: tuple[str, ...] | None, allowed: tuple[str, ...], name: str):
    if values is None:
        return None
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise InsightRequestError(f"Недопустимые значения {name}: {', '.join(unknown)}.")
    return values


def _request(*, start: date, end: date, mode: str, x: str | None, y: str | None, lag: int,
             lags: list[int] | None, max_variables: int | None, include_hidden: bool = False,
             confidence: list[str] | None = None, verdicts: list[str] | None = None,
             variables: list[str] | None = None) -> InsightRequest:
    return InsightRequest(
        start=start, end=end, mode="explorer" if mode == "explorer" else "discovery",
        x=x, y=y, lag=lag,
        lags=tuple(lags) if lags else None, max_variables=max_variables,
        include_hidden=include_hidden,
        confidence=_checked(tuple(confidence) if confidence else None, CONFIDENCE_LEVELS,
                            "уровня подтверждённости"),
        verdicts=_checked(tuple(verdicts) if verdicts else None, VERDICTS, "результата проверок"),
        variables=tuple(variables) if variables else None)


@router.get("/analytics/insights/variables", response_model=InsightCatalogueRead,
            summary="Показатели аналитики с человекочитаемыми названиями")
def read_insight_catalogue(session: DbSession) -> InsightCatalogue:
    return get_catalogue(session)


@router.post("/analytics/insights/refresh", response_model=InsightRefreshRead,
             summary="Пересчитать аналитику и сохранить снимок истории за сегодня")
def refresh_insights(session: DbSession, clock: ClockDep,
                     payload: InsightRefreshRequest) -> InsightRefreshResult:
    request = InsightRequest(start=payload.start, end=payload.end,
                             lags=tuple(payload.lags) if payload.lags else None,
                             max_variables=payload.max_variables)
    return refresh(session, request, today=clock.today())


@router.get("/analytics/insights/refresh", include_in_schema=False)
def refresh_is_not_an_id() -> None:
    """``refresh`` is an operation, not a fingerprint; GET must say so, not 404."""

    raise HTTPException(status_code=405, detail="Обновление аналитики выполняется методом POST.",
                        headers={"Allow": "POST"})


MODE_MAX_LAGS = 15


@router.get("/analytics/insights", response_model=InsightAnalyticsRead,
            summary="Наблюдения по вашим данным: формулировки, доказательства и ограничения")
def read_insights(session: DbSession, clock: ClockDep,
                  start: date = Query(...), end: date = Query(...),
                  x: str | None = Query(None, min_length=1, max_length=160),
                  y: str | None = Query(None, min_length=1, max_length=160),
                  lag: int = Query(0, ge=-LAG_MAX, le=LAG_MAX),
                  lags: list[int] | None = Query(None, min_length=1, max_length=MODE_MAX_LAGS),
                  max_variables: int | None = Query(None, ge=2,
                                                    le=DISCOVERY_POLICY.maximum_variable_budget),
                  include_hidden: bool = Query(False),
                  confidence: list[str] | None = Query(None, max_length=3),
                  verdicts: list[str] | None = Query(None, max_length=4),
                  variables: list[str] | None = Query(None, min_length=1, max_length=64)
                  ) -> InsightAnalytics:
    # A pair means one pre-selected hypothesis; no pair means the discovery sweep.
    request = _request(start=start, end=end,
                       mode="explorer" if x is not None and y is not None else "discovery",
                       x=x, y=y, lag=lag, lags=lags, max_variables=max_variables,
                       include_hidden=include_hidden, confidence=confidence,
                       verdicts=verdicts, variables=variables)
    return get_insights(session, request, today=clock.today())


@router.get("/analytics/insights/{fingerprint}/history", response_model=InsightHistoryRead,
            summary="Как менялось доказательство одной связи при прошлых оценках")
def read_insight_history(session: DbSession, fingerprint: str) -> tuple[InsightSnapshotRead, ...]:
    return get_history(session, fingerprint)


@router.get("/analytics/insights/{fingerprint}", response_model=InsightDetailRead,
            summary="Одно наблюдение: доказательная база, графики и история")
def read_insight_detail(session: DbSession, clock: ClockDep, fingerprint: str,
                        start: date = Query(...), end: date = Query(...),
                        x: str = Query(..., min_length=1, max_length=160),
                        y: str = Query(..., min_length=1, max_length=160),
                        lag: int = Query(0, ge=-LAG_MAX, le=LAG_MAX),
                        mode: str = Query("discovery", pattern="^(discovery|explorer)$"),
                        lags: list[int] | None = Query(None, min_length=1, max_length=MODE_MAX_LAGS),
                        max_variables: int | None = Query(
                            None, ge=2, le=DISCOVERY_POLICY.maximum_variable_budget)
                        ) -> InsightDetail:
    # ``mode`` must match the feed the card came from, so the verdict and the
    # correction denominator stay identical when a card is opened.
    request = InsightRequest(start=start, end=end, mode="explorer" if mode == "explorer"
                             else "discovery", x=x, y=y, lag=lag,
                             lags=tuple(lags) if lags else None, max_variables=max_variables)
    return get_detail(session, fingerprint, request, today=clock.today())
