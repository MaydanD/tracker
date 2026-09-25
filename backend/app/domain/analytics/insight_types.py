"""Stage 8 contract: how admissible evidence becomes a user-facing insight.

An insight is a *representation* of evidence that already exists. This module
defines the vocabulary for that representation; the engine in
:mod:`app.domain.analytics.insights` builds it from the Stage 7A dataset, the
Stage 7D guardrails and the Stage 7E confidence engine, without computing a new
statistic.

Nothing here proves causation, recommends behaviour, ranks factors of importance
or forecasts anything. The response is deterministic and free of any language
model: every user-facing string is produced by a typed template.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.domain.analytics.confidence_types import (
    ConfidenceLevel, CoverageEvidence, MethodEvidence, NotEvaluableReason, SampleEvidence,
    StabilityEvidence,
)
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.guardrail_types import (
    EffectEvidence, GuardrailCheck, GuardrailVerdict, Reason, WeekdayControlEvidence,
)
from app.domain.analytics.relationship_types import (
    Direction, Method, Status as RelationshipStatus, Strength,
)
from app.domain.analytics.types import Grain, Variable


InsightKind = Literal["association"]
InsightStatus = Literal["preliminary", "stable", "well_supported", "warning", "hidden",
                        "not_evaluable"]
InsightFeedMode = Literal["discovery", "explorer"]
# Temporal orientation of the hypothesis. ``same_period`` is a symmetric
# same-date pair, ``x_earlier`` a positive lag and ``x_later`` a negative one.
InsightOrientation = Literal["same_period", "x_earlier", "x_later"]
InsightAvailability = Literal["ok", "preliminary_only", "no_guardrails_passed",
                              "insufficient_data", "no_data"]
CaveatSeverity = Literal["info", "warning", "blocking"]
VariableGroup = Literal["score", "state", "habit", "calendar", "other"]
ChartKey = Literal["series", "relationship", "groups", "lag_profile", "segments", "history"]


@dataclass(frozen=True)
class Policy:
    """Presentation-layer policy: status mapping, deduplication and provenance."""

    version: str = "1"
    template_version: str = "1"
    # History snapshots returned by one detail or history request.
    maximum_history_returned: int = 200
    # Partial periods still get preliminary wording but always carry this caveat.
    negative_lag_caveat: str = "negative_lag_reversed_order"


@dataclass(frozen=True)
class DiscoveryPolicy:
    """Centralized, documented candidate-discovery policy (product rules).

    The default sweep is deliberately bounded: a handful of Daily State
    variables (in a fixed priority order), the daily score and the completion of
    the most important active habits. Everything else is reachable through the
    explorer, so a discovery run can never turn into an unbounded combination
    matrix.
    """

    version: str = "1"
    default_window_days: int = 90
    minimum_window_days: int = 7
    maximum_window_days: int = 730
    # Variable budgets. ``default_variable_budget`` is what a plain request gets;
    # ``maximum_variable_budget`` is what an explicit request may ask for.
    default_variable_budget: int = 6
    maximum_variable_budget: int = 8
    score_budget: int = 1
    state_budget: int = 3
    habit_budget: int = 2
    # Fixed priority order; the first ``state_budget`` present in the dataset win.
    state_priority: tuple[str, ...] = (
        "state.energy", "state.mood", "state.sleep_minutes", "state.wellbeing",
        "state.alcohol", "state.gaming", "state.computer_overuse",
        "state.gaming_minutes", "state.computer_minutes",
    )
    score_variable: str = "daily.score"
    # Feature name inside the canonical ``habit.<id>.<grain>.<feature>`` key.
    habit_feature: str = "completion"
    # Both temporal directions are tested, so the family is
    # ``pairs * (1 + 2 * len(non_zero_lags))`` hypotheses.
    default_lags: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)
    maximum_hypotheses: int = 480
    # Discovery runs on daily grain only; weekly hypotheses live in the explorer.
    discovery_grain: Grain = Grain.DAILY


POLICY = Policy()
DISCOVERY_POLICY = DiscoveryPolicy()

# Deterministic presentation order. This is a *display* order, not a statement
# about importance, and it is reported with every response.
SORT_ORDER: tuple[str, ...] = (
    "guardrail_usability", "confidence_maturity", "recency", "sample_size",
    "absolute_effect", "fingerprint",
)

# How the page explains itself when the current period yields nothing to show.
AVAILABILITY_MESSAGES: dict[InsightAvailability, str] = {
    "ok": "Найдены наблюдения, которые прошли статистические проверки.",
    "preliminary_only": "Появились первые сигналы — данных пока недостаточно для "
                        "устойчивых выводов.",
    "no_guardrails_passed": "Связи рассчитаны, но пока не прошли статистические проверки.",
    "insufficient_data": "Пока недостаточно совместных наблюдений для устойчивых выводов.",
    "no_data": "За выбранный период данных для аналитики нет.",
}


@dataclass(frozen=True)
class InsightText:
    """Deterministic Russian wording for one candidate.

    ``statement`` is the association sentence, ``timing`` the short lag chip and
    ``full`` the sentence a card shows (``statement`` with a confidence prefix).
    No field ever contains a causal or advisory word; see
    ``tests/test_insights.py::test_no_causal_or_recommendation_wording``.
    """

    statement: str
    timing: str
    prefix: str
    full: str
    template_version: str


@dataclass(frozen=True)
class InsightCaveat:
    """One limitation, translated from a backend code (never invented in the UI)."""

    code: str
    label: str
    message: str
    detail: str
    severity: CaveatSeverity


@dataclass(frozen=True)
class InsightRelationship:
    """Compact view of the Stage 7C/7D relationship the insight represents."""

    method: Method | None
    coefficient: float | None
    absolute_coefficient: float | None
    direction: Direction | None
    strength: Strength | None
    n: int
    status: RelationshipStatus
    reason: str | None
    limitations: tuple[str, ...]
    method_agreement: str


@dataclass(frozen=True)
class InsightGuardrail:
    """Stage 7D admissibility verdict, carried verbatim."""

    verdict: GuardrailVerdict
    policy_version: str
    family_mode: str
    family_size: int
    tested_size: int
    family_rank: int | None
    threshold: float
    raw_p_value: float | None
    adjusted_q_value: float | None
    blocking_reasons: tuple[Reason, ...]
    warnings: tuple[Reason, ...]
    confidence_capped: bool


@dataclass(frozen=True)
class InsightConfidence:
    """Stage 7E evidence maturity, carried verbatim and never merged with guardrails."""

    status: Literal["evaluated", "not_evaluable"]
    level: ConfidenceLevel | None
    policy_version: str
    reason: NotEvaluableReason | None


@dataclass(frozen=True)
class InsightSegment:
    """One chronological slice of the target period (Stage 7E segmentation)."""

    index: int
    name: str
    period: Period
    coefficient: float | None
    direction: Direction | None
    strength: Strength | None
    relation_to_full: str


@dataclass(frozen=True)
class InsightEvidence:
    """Everything the detail view may show, all of it from Stage 7C/7D/7E."""

    sample: SampleEvidence
    coverage: CoverageEvidence
    stability: StabilityEvidence
    methods: MethodEvidence
    effect: EffectEvidence
    weekday: WeekdayControlEvidence
    checks: tuple[GuardrailCheck, ...]
    segments: tuple[InsightSegment, ...]


@dataclass(frozen=True)
class InsightAlternative:
    """One lag of the same pair, kept so the whole lag profile stays visible.

    Only one lag becomes the representative card; the rest are never discarded —
    the detail view draws them all.
    """

    fingerprint: str
    timing: str
    lag: int
    is_representative: bool
    orientation: InsightOrientation
    guardrail: GuardrailVerdict
    status: InsightStatus
    confidence: ConfidenceLevel | None
    coefficient: float | None
    absolute_coefficient: float | None
    direction: Direction | None
    n: int
    pair_coverage: float | None
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class InsightCandidate:
    """A typed candidate insight: a pointer to existing evidence plus its wording."""

    fingerprint: str
    kind: InsightKind
    status: InsightStatus
    orientation: InsightOrientation
    x: Variable
    y: Variable
    grain: Grain | None
    lag: int
    lag_unit: Literal["day", "week"] | None
    target_period: Period
    text: InsightText
    relationship: InsightRelationship
    guardrail: InsightGuardrail
    confidence: InsightConfidence
    evidence: InsightEvidence
    caveats: tuple[InsightCaveat, ...]
    alternatives: tuple[InsightAlternative, ...]
    in_default_feed: bool
    # First evaluation date this hypothesis was ever snapshotted, when known.
    first_seen: date | None = None


@dataclass(frozen=True)
class InsightCounts:
    """Counts of the family (hypotheses) and of the feed (display units).

    The unit is part of the field name, because the two are genuinely different:
    one relationship family collapses several lag hypotheses into one card.
    """

    hypotheses: int
    evaluated_hypotheses: int
    admissible_hypotheses: int
    blocked_hypotheses: int
    unevaluable_hypotheses: int
    groups: int
    shown: int
    in_default_feed: int
    by_status: dict[str, int]
    by_blocking_reason: dict[str, int]


@dataclass(frozen=True)
class InsightSummary:
    availability: InsightAvailability
    message: str
    counts: InsightCounts


@dataclass(frozen=True)
class InsightAnalytics:
    """Aggregated insight feed for one requested period."""

    contract_version: str
    dataset_contract_version: str
    insight_policy_version: str
    guardrail_policy_version: str
    confidence_policy_version: str
    template_version: str
    today: date
    mode: InsightFeedMode
    window: Period
    source_range: Period
    lags: tuple[int, ...]
    include_hidden: bool
    discovery_policy: DiscoveryPolicy
    sort_order: tuple[str, ...]
    summary: InsightSummary
    insights: tuple[InsightCandidate, ...]


@dataclass(frozen=True)
class InsightChartPoint:
    """A chart point. ``missing`` marks a gap that must never be drawn as zero."""

    date: date
    value: float | None
    missing: bool
    incomplete: bool


@dataclass(frozen=True)
class InsightRollingPoint:
    date: date
    window: int
    mean: float | None
    status: str


@dataclass(frozen=True)
class InsightSeries:
    variable: Variable
    points: tuple[InsightChartPoint, ...]
    rolling: tuple[InsightRollingPoint, ...]


@dataclass(frozen=True)
class InsightPairPoint:
    """One aligned observation of a numeric/ordinal pair (scatter data only)."""

    x_date: date
    y_date: date
    x: float
    y: float


@dataclass(frozen=True)
class InsightVariable:
    """One selectable variable, with a human-readable Russian label.

    ``key`` is the stable identity used by every analytics layer; ``label`` is
    presentation metadata resolved from the *current* habit configuration, so a
    rename never changes identity but is always reflected in the UI.
    """

    key: str
    label: str
    type: str
    grain: Grain
    group: VariableGroup
    habit_id: int | None
    area_id: int | None
    area_name: str | None
    is_archived: bool
    # Whether an association can be computed for this variable at all.
    supported: bool
    # Whether the default discovery sweep considers this variable.
    in_default_sweep: bool


@dataclass(frozen=True)
class InsightArea:
    id: int
    name: str
    color: str
    is_archived: bool


@dataclass(frozen=True)
class InsightCatalogue:
    contract_version: str
    discovery_policy: DiscoveryPolicy
    areas: tuple[InsightArea, ...]
    variables: tuple[InsightVariable, ...]


@dataclass(frozen=True)
class InsightChartSummary:
    """Accessible text summary of one chart, in Russian, built by the backend."""

    key: ChartKey
    title: str
    summary: str


@dataclass(frozen=True)
class InsightChart:
    x: InsightSeries
    y: InsightSeries
    pairs: tuple[InsightPairPoint, ...]
    lag_profile: tuple[InsightAlternative, ...]
    segments: tuple[InsightSegment, ...]
    summaries: tuple[InsightChartSummary, ...]


@dataclass(frozen=True)
class InsightSnapshotRead:
    """One persisted history entry for a hypothesis fingerprint."""

    id: int
    fingerprint: str
    evaluated_on: date
    period: Period
    x_key: str
    y_key: str
    x_label: str
    y_label: str
    x_archived: bool | None
    y_archived: bool | None
    grain: str
    lag: int
    lag_unit: str | None
    orientation: str
    method: str | None
    coefficient: float | None
    n: int
    pair_coverage: float | None
    confidence: str | None
    guardrail_verdict: str
    status: str
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    statement: str
    insight_policy_version: str
    guardrail_policy_version: str
    confidence_policy_version: str
    template_version: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class InsightDetail:
    contract_version: str
    today: date
    mode: InsightFeedMode
    window: Period
    snapshot_policy: str
    candidate: InsightCandidate
    chart: InsightChart
    history: tuple[InsightSnapshotRead, ...]


@dataclass(frozen=True)
class InsightSnapshotSummary:
    evaluated_on: date
    created: int
    updated: int
    unchanged: int
    total: int


@dataclass(frozen=True)
class InsightRefreshResult:
    analytics: InsightAnalytics
    snapshots: InsightSnapshotSummary
