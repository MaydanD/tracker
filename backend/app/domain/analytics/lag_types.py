"""Stage 7D contract. Positive lag means X earlier than Y; Y owns the period."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.relationship_types import Policy as RelationshipPolicy, Relationship


@dataclass(frozen=True)
class LagPolicy:
    max_absolute_lag: int = 7
    max_lag_values: int = 15


POLICY = LagPolicy()


@dataclass(frozen=True)
class LagResult(Relationship):
    lag: int
    lag_unit: Literal["day", "week"] | None
    target_period: Period
    x_period: Period | None
    potential_aligned_count: int


@dataclass(frozen=True)
class LagAnalytics:
    contract_version: str
    dataset_contract_version: str
    today: date
    target_period: Period
    source_range: Period
    habit_entry_source_range: Period
    target_side: Literal["y"]
    sign_convention: Literal["positive_x_earlier"]
    policy: LagPolicy
    relationship_policy: RelationshipPolicy
    minimum_weekly_source_coverage: float
    limitations: tuple[Literal["association_not_causation", "autocorrelation_unadjusted",
                               "systematic_missingness", "multiple_lags_exploratory"], ...]
    results: tuple[LagResult, ...]
