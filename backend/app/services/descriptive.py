"""One canonical dataset load for all descriptive operations and both periods."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.analytics.descriptive import analyze, request_periods
from app.domain.analytics.descriptive_types import DescriptiveAnalytics
from app.services import analytics


def get_descriptive(session: Session, start: date, end: date, variables: tuple[str, ...],
                    *, today: date) -> DescriptiveAnalytics:
    _, previous = request_periods(start, end, variables)
    dataset = analytics.get_dataset(session, previous.start, end, today=today)
    return analyze(dataset, start, end, variables)
