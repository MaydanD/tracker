"""Typed JSON/OpenAPI contract for lag analysis."""

from pydantic import RootModel

from app.domain.analytics.lag_types import LagAnalytics


class LagAnalyticsRead(RootModel[LagAnalytics]):
    pass
