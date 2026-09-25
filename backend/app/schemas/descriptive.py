"""OpenAPI and JSON contract for Stage 7B; no ORM response objects."""

from pydantic import RootModel

from app.domain.analytics.descriptive_types import DescriptiveAnalytics


class DescriptiveAnalyticsRead(RootModel[DescriptiveAnalytics]):
    pass
