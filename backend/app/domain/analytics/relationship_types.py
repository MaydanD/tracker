"""Detached Stage 7C contract. Counts refer to aligned same-period pairs."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.analytics.descriptive_types import Coverage, Period
from app.domain.analytics.types import Grain, Variable


Method = Literal["pearson", "spearman", "point_biserial", "phi"]
Status = Literal["ok", "insufficient_data", "constant_series", "invalid_values",
                 "numerical_error", "incompatible_units", "unsupported"]
Reason = Literal["too_few_pairs", "zero_variance", "nonfinite_or_invalid_values",
                 "unstable_calculation", "mixed_quantity_units", "grain_mismatch",
                 "unsupported_types"]
Direction = Literal["positive", "negative", "near_zero"]
Strength = Literal["negligible", "weak", "moderate", "strong"]
Exclusion = Literal["future", "incomplete_period", "not_eligible", "missing",
                    "invalid_value", "low_source_coverage"]


@dataclass(frozen=True)
class Policy:
    max_period_days: int = 1830
    max_variables: int = 24
    calculation_minimum: int = 5
    strength_minimum: int = 10
    negligible_below: float = 0.1
    weak_below: float = 0.3
    moderate_below: float = 0.5


POLICY = Policy()


@dataclass(frozen=True)
class Metric:
    method: Method
    status: Status
    coefficient: float | None
    reason: Reason | None = None


@dataclass(frozen=True)
class BooleanCounts:
    true_count: int
    false_count: int


@dataclass(frozen=True)
class Contingency:
    true_true: int
    true_false: int
    false_true: int
    false_false: int


@dataclass(frozen=True)
class PairCoverage:
    requested_count: int
    eligible_count: int
    valid_pair_count: int
    missing_count: int
    unavailable_count: int
    excluded_count: int
    pair_coverage: float | None
    losses: dict[Exclusion, int]
    x: Coverage
    y: Coverage
    source_x: Coverage | None
    source_y: Coverage | None
    paired_source_x: Coverage | None
    paired_source_y: Coverage | None
    includes_today: bool


@dataclass(frozen=True)
class Relationship:
    x: Variable
    y: Variable
    grain: Grain | None
    method: Method | None
    coefficient: float | None
    direction: Direction | None
    strength: Strength | None
    n: int
    coverage: PairCoverage | None
    status: Status
    reason: Reason | None
    metrics: tuple[Metric, ...]
    boolean_x: BooleanCounts | None
    boolean_y: BooleanCounts | None
    contingency: Contingency | None
    units_x: tuple[str, ...]
    units_y: tuple[str, ...]
    limitations: tuple[Literal["ordinal_spacing_assumed"], ...]


@dataclass(frozen=True)
class RelationshipAnalytics:
    contract_version: str
    dataset_contract_version: str
    today: date
    period: Period
    mode: Literal["pair", "matrix"]
    policy: Policy
    minimum_weekly_source_coverage: float
    relationships: tuple[Relationship, ...]
