"""Load one canonical dataset per request, then analyze all pairs in memory."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.analytics.relationships import analyze, validate_request
from app.domain.analytics.relationship_types import RelationshipAnalytics
from app.services import analytics


def get_relationships(session: Session, start: date, end: date, variables: tuple[str, ...],
                      *, today: date, pair: bool = False) -> RelationshipAnalytics:
    validate_request(start, end, variables, pair=pair)
    dataset = analytics.get_dataset(session, start, end, today=today)
    return analyze(dataset, start, end, variables, pair=pair)
