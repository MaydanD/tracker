"""One expanded 7A dataset build for the full period and every history segment."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.analytics.confidence import analyze, split_period
from app.domain.analytics.confidence_types import ConfidenceAnalytics
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lags import normalize_lags, request_variables, required_source_range
from app.domain.analytics.types import Grain
from app.services import analytics


def required_source_range_for_scan(period: Period, segments: tuple[Period, ...],
                                   lag: int, grain: Grain) -> Period:
    """Union of the full period's and every segment's shifted X windows.

    A single lag shifts the whole period uniformly, so segment X windows are a
    subset of the full one; the union is computed explicitly anyway so a future
    multi-lag scan cannot silently drop X before a segment starts.
    """
    ranges = (required_source_range(period, (lag,), grain),) + tuple(
        required_source_range(segment, (lag,), grain) for segment in segments)
    return Period(min(item.start for item in ranges), max(item.end for item in ranges))


def get_confidence(session: Session, start: date, end: date, x: str, y: str,
                   *, lag: int = 0, today: date) -> ConfidenceAnalytics:
    variables = request_variables(start, end, (x, y))
    lag = normalize_lags((lag,))[0]
    period = Period(start, end)
    grain = variables[0].grain if variables[0].grain == variables[1].grain else None
    if grain is None:
        source = period
    else:
        source = required_source_range_for_scan(period, split_period(period, grain), lag, grain)
    dataset = analytics.get_dataset(session, source.start, source.end, today=today)
    return analyze(dataset, start, end, (x, y), lag)
