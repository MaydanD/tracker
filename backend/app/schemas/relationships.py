"""Typed JSON/OpenAPI contract for read-only relationship analysis."""

from pydantic import RootModel

from app.domain.analytics.relationship_types import RelationshipAnalytics


class RelationshipAnalyticsRead(RootModel[RelationshipAnalytics]):
    pass
