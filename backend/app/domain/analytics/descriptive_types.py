"""Stage 7B response contract: detached, typed, and JSON serializable."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.analytics.types import Availability, Scalar, Variable


Status = Literal["ok", "insufficient_data", "incomplete_period", "coverage_mismatch",
                 "incompatible_units", "numerical_overflow", "not_supported"]


@dataclass(frozen=True)
class Policy:
    max_period_days: int = 1830
    max_variables: int = 64
    daily_windows: tuple[int, ...] = (7, 28)
    weekly_windows: tuple[int, ...] = (4, 12)
    minimum_coverage: float = 0.5
    maximum_coverage_difference: float = 0.25
    daily_comparison_minimum: int = 3
    weekly_comparison_minimum: int = 2
    daily_trend_half_minimum: int = 3
    weekly_trend_half_minimum: int = 2
    variability_minimum: int = 2
    trend_relative_threshold: float = 0.05
    trend_sd_threshold: float = 0.5
    ordinal_trend_threshold: float = 0.5


POLICY = Policy()


@dataclass(frozen=True)
class Period:
    start: date
    end: date


@dataclass(frozen=True)
class Coverage:
    total_count: int
    eligible_count: int
    observed_count: int
    missing_count: int
    unavailable_count: int
    ratio: float | None
    counts_by_availability: dict[Availability, int]


@dataclass(frozen=True)
class Frequency:
    value: str | int
    count: int
    proportion: float | None


@dataclass(frozen=True)
class NumericStatistics:
    type: Literal["numeric", "ordinal"]
    status: Status
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    range: float | None
    standard_deviation: float | None
    variability_status: Status
    distribution: tuple[Frequency, ...] | None


@dataclass(frozen=True)
class BooleanStatistics:
    type: Literal["boolean"]
    true_count: int
    false_count: int
    true_rate: float | None


@dataclass(frozen=True)
class HabitCompletion:
    completed_count: int
    missed_count: int
    skipped_count: int
    unmarked_count: int
    applicable_count: int
    completion_rate_among_observed: float | None


@dataclass(frozen=True)
class CategoricalStatistics:
    type: Literal["categorical"]
    distribution: tuple[Frequency, ...]
    # All tied modes, in registry/display order; empty when nothing observed.
    modes: tuple[str, ...]
    habit_completion: HabitCompletion | None


@dataclass(frozen=True)
class WeekCoverage:
    week_start: date
    week_end: date
    requested_start: date
    requested_end: date
    requested_days: int
    elapsed_requested_days: int
    calendar_elapsed_days: int
    partial_requested_week: bool
    unfinished_week: bool
    active_habit_days: int
    applicable_habit_days: int | None
    scope: Literal["calendar_week", "requested_elapsed_dates"]


@dataclass(frozen=True)
class SeriesPoint:
    date: date
    value: Scalar | None
    availability: Availability
    incomplete: bool
    unit: str | None = None
    week: WeekCoverage | None = None
    source_coverage: Coverage | None = None


@dataclass(frozen=True)
class Summary:
    period: Period
    coverage: Coverage
    source_coverage: Coverage | None
    incomplete: bool
    units: tuple[str, ...]
    statistics: NumericStatistics | BooleanStatistics | CategoricalStatistics


@dataclass(frozen=True)
class RollingPoint:
    date: date
    window_start: date | None
    window_size: int
    window_unit: Literal["days", "weeks"]
    available_count: int
    observed_count: int
    required_count: int
    coverage: Coverage
    status: Status
    mean: float | None


@dataclass(frozen=True)
class Comparison:
    status: Status
    metric: Literal["mean", "true_rate", "distribution"]
    current: Summary
    previous: Summary
    absolute_delta: float | None
    relative_delta: float | None
    percentage_delta: float | None


@dataclass(frozen=True)
class Trend:
    status: Status
    direction: Literal["rising", "falling", "stable", "insufficient_data", "not_supported"]
    method: Literal["half_period_medians"]
    split_date: date | None
    first_observed_count: int
    second_observed_count: int
    first_median: float | None
    second_median: float | None
    absolute_delta: float | None
    threshold: float | None


@dataclass(frozen=True)
class VariableAnalysis:
    variable: Variable
    summary: Summary
    series: tuple[SeriesPoint, ...]
    rolling: tuple[RollingPoint, ...]
    comparison: Comparison
    trend: Trend


@dataclass(frozen=True)
class DescriptiveAnalytics:
    contract_version: str
    dataset_contract_version: str
    today: date
    current_period: Period
    previous_period: Period
    policy: Policy
    variables: tuple[VariableAnalysis, ...]
