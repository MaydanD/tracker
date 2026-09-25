"""One hypothesis, one lag family or one relationship matrix, with guardrails."""

from datetime import date
from itertools import combinations

from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.dependencies import ClockDep, DbSession
from app.domain.analytics.guardrail_types import GuardrailAnalytics
from app.domain.analytics.lag_types import POLICY as LAG_POLICY
from app.domain.analytics.lags import select_lags
from app.domain.analytics.relationship_types import POLICY as RELATIONSHIP_POLICY
from app.domain.analytics.relationships import validate_request
from app.schemas.guardrails import GuardrailAnalyticsRead
from app.services.guardrails import get_guardrails


class GuardrailRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def localized_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(422, "Укажите корректные даты, переменные x/y или список variables "
                                         "и целые сдвиги от -7 до +7.") from exc

        return localized_handler


router = APIRouter(tags=["analytics"], route_class=GuardrailRoute)


@router.get("/analytics/guardrails", response_model=GuardrailAnalyticsRead,
            summary="Допустим ли результат как evidence: размер, баланс, эффект, FDR, weekday, "
                    "устойчивость")
def read_guardrails(session: DbSession, clock: ClockDep,
                    start: date = Query(...), end: date = Query(...),
                    x: str | None = Query(None, min_length=1, max_length=160),
                    y: str | None = Query(None, min_length=1, max_length=160),
                    lag: int | None = Query(None, ge=-LAG_POLICY.max_absolute_lag,
                                            le=LAG_POLICY.max_absolute_lag),
                    lags: list[int] | None = Query(None, min_length=1,
                                                   max_length=LAG_POLICY.max_lag_values),
                    lag_start: int | None = Query(None, ge=-LAG_POLICY.max_absolute_lag,
                                                  le=LAG_POLICY.max_absolute_lag),
                    lag_end: int | None = Query(None, ge=-LAG_POLICY.max_absolute_lag,
                                                le=LAG_POLICY.max_absolute_lag),
                    variables: list[str] | None = Query(None, min_length=2,
                                                        max_length=RELATIONSHIP_POLICY.max_variables)
                    ) -> GuardrailAnalytics:
    try:
        if variables is not None:
            if x is not None or y is not None or lag is not None or lags is not None \
                    or lag_start is not None or lag_end is not None:
                raise ValueError("Укажите либо x и y со сдвигами, либо список variables.")
            validate_request(start, end, tuple(variables), pair=False)
            keys = tuple(sorted(variables))
            hypotheses = tuple((first, second, 0) for first, second in combinations(keys, 2))
            mode = "matrix"
        else:
            if x is None or y is None:
                raise ValueError("Укажите обе переменные x и y или список variables.")
            selected = select_lags(lag=lag, lags=tuple(lags) if lags is not None else None,
                                   lag_start=lag_start, lag_end=lag_end)
            hypotheses = tuple((x, y, item) for item in selected)
            mode = "single" if len(hypotheses) == 1 else "lag_scan"
        return get_guardrails(session, start, end, hypotheses, mode=mode, today=clock.today())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
