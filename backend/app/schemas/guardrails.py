"""Typed JSON/OpenAPI contract for read-only statistical guardrails."""

from pydantic import RootModel

from app.domain.analytics.guardrail_types import GuardrailAnalytics


class GuardrailAnalyticsRead(RootModel[GuardrailAnalytics]):
    pass
