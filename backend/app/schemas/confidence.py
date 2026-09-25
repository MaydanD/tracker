"""Typed JSON/OpenAPI contract for read-only confidence evaluation."""

from pydantic import RootModel

from app.domain.analytics.confidence_types import ConfidenceAnalytics


class ConfidenceAnalyticsRead(RootModel[ConfidenceAnalytics]):
    pass
