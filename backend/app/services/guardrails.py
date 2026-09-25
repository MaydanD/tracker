"""One dataset build for a whole guardrail family; no per-hypothesis SQL."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.guardrail_types import FamilyMode, GuardrailAnalytics
from app.domain.analytics.guardrails import Hypothesis, analyze
from app.domain.analytics.lags import normalize_lags, request_variables, required_source_range
from app.services import analytics


def family_source_range(start: date, end: date, hypotheses: tuple[Hypothesis, ...]) -> Period:
    """Union of every hypothesis' required X window (already segment-aware).

    Metadata comes from the canonical Stage 7A registry, so an invalid request
    fails before any source is loaded. A grain-mismatched hypothesis only ever
    needs the requested target period.
    """
    if not hypotheses:
        raise ValueError("Нужна хотя бы одна гипотеза.")
    ranges = []
    for x_key, y_key, lag in hypotheses:
        variables = request_variables(start, end, (x_key, y_key))
        lag = normalize_lags((lag,))[0]
        ranges.append(required_source_range(Period(start, end), (lag,), variables[0].grain)
                      if variables[0].grain == variables[1].grain else Period(start, end))
    return Period(min(item.start for item in ranges), max(item.end for item in ranges))


def get_guardrails(session: Session, start: date, end: date, hypotheses: tuple[Hypothesis, ...],
                   *, mode: FamilyMode, today: date) -> GuardrailAnalytics:
    source = family_source_range(start, end, hypotheses)
    dataset = analytics.get_dataset(session, source.start, source.end, today=today)
    return analyze(dataset, start, end, hypotheses, mode=mode)
