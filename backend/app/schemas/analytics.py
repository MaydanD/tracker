"""Explicit JSON/OpenAPI schema wrapping the canonical dataclass contract.

RootModel keeps the HTTP shape identical to the internal dataset. Smart unions
retain bool/int/string types; Value rejects nonfinite numbers and ambiguous nulls.
"""

from pydantic import RootModel

from app.domain.analytics.types import AnalyticsDataset


class AnalyticsDatasetRead(RootModel[AnalyticsDataset]):
    pass
