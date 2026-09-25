"""Stage 7E contract: how well a *given* association is supported by the history.

Confidence is an evidence-maturity label, never a probability. It says how much
of the user's own history reproduces the coefficient, not how likely the
association is to be true, causal, significant or predictive. The semantics are
documented in docs/analytics-confidence.md.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lag_types import LagResult
from app.domain.analytics.relationship_types import (
    Direction, Method, Policy as RelationshipPolicy, Strength,
)
from app.domain.analytics.types import Grain, Variable


ConfidenceLevel = Literal["preliminary", "stable", "well_supported"]
ConfidenceStatus = Literal["evaluated", "not_evaluable"]
NotEvaluableReason = Literal["grain_mismatch", "unsupported_types", "incompatible_units",
                             "insufficient_data", "constant_series", "invalid_values",
                             "numerical_error", "unsupported"]
SegmentName = Literal["only", "early", "middle", "recent"]
# How one history segment relates to the full-period direction: "near_zero" is
# the deliberately weaker middle case between confirmation and refutation.
RelationToFull = Literal["same", "near_zero", "opposite", "insufficient"]
MethodAgreement = Literal["single_method", "agree", "partial", "disagree", "unavailable"]

CaveatCode = Literal[
    "small_sample", "limited_history", "low_coverage", "systematic_missingness_possible",
    "segment_inconsistency", "direction_reversal", "magnitude_instability", "partial_period",
    "method_disagreement", "constant_series", "incompatible_units",
    "unsupported_variable_types", "ordinal_distance_limitation", "autocorrelation_possible",
    "association_not_causation",
]

# Canonical emission order: caveat order must never depend on dict/set iteration.
CAVEAT_ORDER: tuple[CaveatCode, ...] = (
    "small_sample", "limited_history", "low_coverage", "systematic_missingness_possible",
    "segment_inconsistency", "direction_reversal", "magnitude_instability", "partial_period",
    "method_disagreement", "constant_series", "incompatible_units",
    "unsupported_variable_types", "ordinal_distance_limitation", "autocorrelation_possible",
    "association_not_causation",
)


@dataclass(frozen=True)
class Policy:
    """Centralized product policy. Not statistical truth; not a p-value threshold.

    Direction uses the existing Stage 7C ``negligible_below`` band, so no second
    near-zero threshold exists in Stage 7E.
    """

    version: str = "1"
    # Chronological history segments (contiguous, non-overlapping, calendar-equal).
    segment_count: int = 3
    # preliminary: the relationship is computable at all.
    preliminary_minimum_n: int = 5
    # stable: enough paired observations, coverage and replicated direction.
    stable_minimum_n: int = 20
    stable_minimum_pair_coverage: float = 0.60
    stable_minimum_analyzable_segments: int = 2
    stable_maximum_deviation_from_full: float = 0.35
    # well_supported: stricter sample, coverage, full replication, steady magnitude.
    well_supported_minimum_n: int = 40
    well_supported_minimum_pair_coverage: float = 0.75
    well_supported_minimum_analyzable_segments: int = 3
    # Segments allowed to be "near_zero" instead of matching the full direction.
    well_supported_maximum_non_matching_segments: int = 1
    well_supported_maximum_deviation_from_full: float = 0.20
    # Data-quality warning: pair coverage differing this much across segments.
    segment_coverage_imbalance_threshold: float = 0.25


POLICY = Policy()


@dataclass(frozen=True)
class Caveat:
    """Deterministic code with the Russian label/message a future UI may show."""

    code: CaveatCode
    label: str
    message: str


@dataclass(frozen=True)
class SampleEvidence:
    n: int
    requested_count: int
    eligible_count: int
    excluded_count: int
    missing_count: int
    unavailable_count: int
    pair_coverage: float | None
    minimum_n_met: bool
    stable_n_met: bool
    well_supported_n_met: bool


@dataclass(frozen=True)
class CoverageEvidence:
    pair_coverage: float | None
    eligible_count: int
    stable_coverage_met: bool
    well_supported_coverage_met: bool
    segment_pair_coverage: tuple[float | None, ...]
    minimum_segment_coverage: float | None
    maximum_segment_coverage: float | None
    coverage_imbalance: float | None
    low_coverage: bool
    segment_instability: bool


@dataclass(frozen=True)
class StabilityEvidence:
    segment_count: int
    analyzable_segment_count: int
    insufficient_segment_count: int
    same_direction_count: int
    near_zero_count: int
    opposite_direction_count: int
    coefficients: tuple[float, ...]
    median_coefficient: float | None
    median_absolute_coefficient: float | None
    coefficient_range: float | None
    maximum_deviation_from_full: float | None
    direction_consistent: bool
    meaningful_reversal: bool
    magnitude_stable: bool
    magnitude_well_supported: bool


@dataclass(frozen=True)
class MethodEvidence:
    primary_method: Method | None
    methods: tuple[Method, ...]
    coefficients: tuple[float | None, ...]
    directions: tuple[Direction | None, ...]
    agreement: MethodAgreement


@dataclass(frozen=True)
class ConfidenceEvidence:
    sample: SampleEvidence
    coverage: CoverageEvidence
    stability: StabilityEvidence
    methods: MethodEvidence


@dataclass(frozen=True)
class ConfidenceSegment:
    """One chronological slice of the requested Y target period."""

    index: int
    name: SegmentName
    period: Period
    relationship: LagResult
    relation_to_full: RelationToFull
    direction: Direction | None
    strength: Strength | None


@dataclass(frozen=True)
class GuardrailSummary:
    """Compact Stage 7D guardrail verdict carried by the Stage 7E response.

    Guardrails and confidence stay separate fields: an association can be
    historically stable and still be inadmissible evidence for a discovery
    family, or vice versa.
    """

    policy_version: str
    status: Literal["pass", "pass_with_warnings", "blocked", "not_evaluable"]
    family_size: int
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence_capped: bool = False


@dataclass(frozen=True)
class ConfidenceAnalytics:
    contract_version: str
    dataset_contract_version: str
    confidence_policy_version: str
    today: date
    x: Variable
    y: Variable
    grain: Grain | None
    lag: int
    lag_unit: Literal["day", "week"] | None
    target_period: Period
    source_range: Period
    habit_entry_source_range: Period
    status: ConfidenceStatus
    reason: NotEvaluableReason | None
    confidence: ConfidenceLevel | None
    policy: Policy
    relationship_policy: RelationshipPolicy
    relationship: LagResult
    evidence: ConfidenceEvidence
    segments: tuple[ConfidenceSegment, ...]
    caveats: tuple[Caveat, ...]
    guardrail: GuardrailSummary | None = None
