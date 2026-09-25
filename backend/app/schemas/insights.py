"""Typed JSON/OpenAPI contracts for the Stage 8 insight layer."""

from datetime import date

from pydantic import BaseModel, Field, RootModel

from app.domain.analytics.insight_types import (
    InsightAnalytics, InsightCatalogue, InsightDetail, InsightRefreshResult, InsightSnapshotRead,
)


class InsightAnalyticsRead(RootModel[InsightAnalytics]):
    pass


class InsightDetailRead(RootModel[InsightDetail]):
    pass


class InsightHistoryRead(RootModel[tuple[InsightSnapshotRead, ...]]):
    pass


class InsightCatalogueRead(RootModel[InsightCatalogue]):
    pass


class InsightRefreshRead(RootModel[InsightRefreshResult]):
    pass


class InsightRefreshRequest(BaseModel):
    """Explicit materialization: this is the only request that writes history."""

    start: date = Field(description="Начало анализируемого периода (включительно).")
    end: date = Field(description="Конец анализируемого периода (включительно).")
    lags: list[int] | None = Field(
        default=None, max_length=15,
        description="Проверяемые сдвиги; по умолчанию 0..+7 дней.")
    max_variables: int | None = Field(
        default=None, ge=2, le=8,
        description="Сколько переменных включить в проверку (по умолчанию — политика).")
