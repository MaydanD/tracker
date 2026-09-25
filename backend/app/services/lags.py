"""One expanded 7A dataset build for the entire read-only lag scan."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lag_types import LagAnalytics
from app.domain.analytics.lags import analyze, normalize_lags, request_variables, required_source_range
from app.services import analytics


def get_lags(session: Session, start: date, end: date, x: str, y: str,
             lags: tuple[int, ...] = (0,), *, today: date) -> LagAnalytics:
    variables = request_variables(start, end, (x, y))
    lags = normalize_lags(lags)
    period = Period(start, end)
    source = (required_source_range(period, lags, variables[0].grain)
              if variables[0].grain == variables[1].grain else period)
    dataset = analytics.get_dataset(session, source.start, source.end, today=today)
    return analyze(dataset, start, end, (x, y), lags)
