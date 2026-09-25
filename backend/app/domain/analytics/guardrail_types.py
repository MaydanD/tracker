"""Statistical guardrail contract: may this result be used as evidence at all?

Guardrails and confidence answer different questions. Guardrails ask whether a
computed association is admissible evidence (enough observations, balanced
groups, a non-negligible effect, survives multiple-comparison control, is not a
weekday artifact, is not temporally unstable, has usable coverage). Confidence
(Stage 7E) then asks how well an admissible association is supported by the whole
history. The two verdicts are reported separately and are never merged.

Nothing here proves causation, generates recommendations, ranks behaviour,
forecasts anything or produces user-facing insights.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.analytics.confidence_types import (
    CoverageEvidence, SampleEvidence, StabilityEvidence,
)
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lag_types import LagResult
from app.domain.analytics.relationship_types import (
    Contingency, Method, Policy as RelationshipPolicy,
)
from app.domain.analytics.types import Grain, Variable


GuardrailVerdict = Literal["pass", "pass_with_warnings", "blocked", "not_evaluable"]
CheckStatus = Literal["passed", "failed", "not_applicable", "not_evaluable"]
CheckName = Literal["sample_size", "coverage", "group_balance", "effect_size",
                    "weekday_control", "temporal_stability", "multiple_comparisons"]
FamilyMode = Literal["single", "lag_scan", "matrix"]
WeekdayOutcome = Literal["retained", "attenuated", "explained_by_weekday", "reversed",
                         "not_applicable", "not_supported", "insufficient_strata",
                         "not_evaluable"]

BlockingReason = Literal["insufficient_sample", "insufficient_coverage",
                         "below_effect_threshold", "insufficient_group_balance",
                         "sparse_contingency_cell", "false_discovery_risk",
                         "weekday_explained", "weekday_reversal",
                         "temporal_direction_inconsistency", "temporal_reversal"]
WarningCode = Literal["small_sample", "moderate_coverage", "weekday_attenuation",
                      "weekday_control_unavailable", "insufficient_temporal_evidence",
                      "magnitude_instability", "partial_period"]

BLOCKING_ORDER: tuple[BlockingReason, ...] = (
    "insufficient_sample", "insufficient_coverage", "below_effect_threshold",
    "insufficient_group_balance", "sparse_contingency_cell", "false_discovery_risk",
    "weekday_explained", "weekday_reversal", "temporal_direction_inconsistency",
    "temporal_reversal",
)
WARNING_ORDER: tuple[WarningCode, ...] = (
    "small_sample", "moderate_coverage", "weekday_attenuation", "weekday_control_unavailable",
    "insufficient_temporal_evidence", "magnitude_instability", "partial_period",
)


@dataclass(frozen=True)
class Policy:
    """Centralized guardrail policy. Product rules, not statistical truth.

    Deliberately consistent with the Stage 7E confidence policy: coverage passes
    at 0.60 there and blocks below 0.40 here, with 0.40-0.60 only a warning, so
    the two layers can never contradict each other.
    """

    version: str = "1"
    # Sample size: below minimum blocks, below warning warns, otherwise passes.
    minimum_n: int = 10
    warning_below_n: int = 20
    # Pair coverage (never calendar days).
    minimum_pair_coverage: float = 0.40
    warning_below_pair_coverage: float = 0.60
    # Minimum practically meaningful absolute coefficient.
    minimum_absolute_effect: float = 0.15
    # Binary comparisons.
    minimum_group_observations: int = 5
    minimum_minority_share: float = 0.15
    minimum_contingency_cell: int = 5
    # Weekday control.
    weekday_minimum_strata: int = 2
    weekday_minimum_stratum_observations: int = 3
    weekday_maximum_relative_attenuation: float = 0.50
    # Multiple comparisons.
    fdr_threshold: float = 0.10
    # Temporal blocking reuses the Stage 7E stability metrics.
    temporal_minimum_analyzable_segments: int = 2


POLICY = Policy()


@dataclass(frozen=True)
class Reason:
    """Deterministic code with the Russian label/message a future UI may show."""

    code: str
    label: str
    message: str


BLOCKING_REASONS: dict[str, tuple[str, str]] = {
    "insufficient_sample": ("Мало наблюдений",
                            "Пар наблюдений меньше минимума для использования связи как "
                            "доказательства."),
    "insufficient_coverage": ("Недостаточное покрытие",
                              "Доля пар наблюдений слишком низкая, чтобы считать результат "
                              "надёжным."),
    "below_effect_threshold": ("Эффект ниже порога",
                               "Величина связи ниже минимального практически значимого "
                               "эффекта."),
    "insufficient_group_balance": ("Несбалансированные группы",
                                   "В одной из бинарных групп слишком мало наблюдений или "
                                   "её доля слишком мала."),
    "sparse_contingency_cell": ("Разреженная таблица",
                               "В таблице сопряжённости есть ячейки с малым числом "
                               "наблюдений."),
    "false_discovery_risk": ("Риск ложного открытия",
                            "Связь не проходит контроль доли ложных открытий (FDR) в "
                            "проверяемом семействе гипотез."),
    "weekday_explained": ("Полностью объясняется днём недели",
                         "После контроля дня недели вариация связи исчезает: это "
                         "недельный паттерн, а не связь."),
    "weekday_reversal": ("Смена знака после контроля дня недели",
                        "После контроля дня недели направление связи меняется на "
                        "противоположное."),
    "temporal_direction_inconsistency": ("Нестабильное направление",
                                        "Большинство временных отрезков истории не "
                                        "поддерживают направление связи."),
    "temporal_reversal": ("Разворот во времени",
                         "На одном из отрезков истории связь уверенно противоположна "
                         "связи за весь период."),
}

WARNINGS: dict[str, tuple[str, str]] = {
    "small_sample": ("Небольшая выборка",
                     "Наблюдений достаточно для проверки, но меньше комфортного уровня."),
    "moderate_coverage": ("Умеренное покрытие",
                         "Покрытие приемлемо, но часть подходящих дат не имеет обеих "
                         "переменных."),
    "weekday_attenuation": ("Ослабление после контроля дня недели",
                            "После контроля дня недели величина связи заметно снижается."),
    "weekday_control_unavailable": ("Контроль дня недели недоступен",
                                    "Для этой комбинации типов или периода контроль дня "
                                    "недели не применяется; результат не проверен на "
                                    "недельную природу."),
    "insufficient_temporal_evidence": ("Мало временных данных",
                                       "Недостаточно анализируемых отрезков истории для "
                                       "подтверждения устойчивости."),
    "magnitude_instability": ("Нестабильная величина",
                              "Величина связи заметно различается между отрезками истории."),
    "partial_period": ("Неполный период",
                       "Часть недель периода неполные и исключена из расчёта."),
}


@dataclass(frozen=True)
class GuardrailCheck:
    name: CheckName
    status: CheckStatus
    blocking: bool
    detail: str
    observed: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class GroupEvidence:
    boolean_side: Literal["x", "y"]
    true_count: int
    false_count: int
    minority_count: int
    minority_share: float | None
    true_mean: float | None
    false_mean: float | None
    true_median: float | None
    false_median: float | None
    absolute_mean_difference: float | None
    cohens_d: float | None
    contingency: Contingency | None
    minimum_cell_count: int | None


@dataclass(frozen=True)
class EffectEvidence:
    method: Method | None
    coefficient: float | None
    absolute_coefficient: float | None
    minimum_absolute_effect: float
    meets_minimum: bool
    group: GroupEvidence | None


@dataclass(frozen=True)
class WeekdayControlEvidence:
    status: CheckStatus
    outcome: WeekdayOutcome
    weekday_basis: Literal["y_target_date"]
    strata_count: int
    usable_strata_count: int
    observations: int
    raw_coefficient: float | None
    adjusted_coefficient: float | None
    absolute_difference: float | None
    relative_attenuation: float | None
    direction_change: bool


@dataclass(frozen=True)
class MultipleComparisonEvidence:
    family_mode: FamilyMode
    family_size: int
    tested_size: int
    family_rank: int | None
    method: Literal["benjamini_hochberg"] | None
    threshold: float
    status: CheckStatus
    raw_p_value: float | None
    adjusted_q_value: float | None
    passed: bool | None


@dataclass(frozen=True)
class GuardrailHypothesis:
    index: int
    x: Variable
    y: Variable
    grain: Grain | None
    lag: int
    lag_unit: Literal["day", "week"] | None
    target_period: Period
    verdict: GuardrailVerdict
    relationship: LagResult
    sample: SampleEvidence
    coverage: CoverageEvidence
    stability: StabilityEvidence
    effect: EffectEvidence
    weekday: WeekdayControlEvidence
    multiple_comparisons: MultipleComparisonEvidence
    checks: tuple[GuardrailCheck, ...]
    blocking_reasons: tuple[Reason, ...]
    warnings: tuple[Reason, ...]


@dataclass(frozen=True)
class FamilySummary:
    mode: FamilyMode
    requested_size: int
    evaluable_size: int
    tested_size: int
    fdr_method: Literal["benjamini_hochberg"]
    fdr_threshold: float
    # Multiplicity control only matters inside a family of tested hypotheses.
    multiple_comparisons_checked: bool
    verdicts: dict[GuardrailVerdict, int]


@dataclass(frozen=True)
class GuardrailAnalytics:
    contract_version: str
    dataset_contract_version: str
    guardrail_policy_version: str
    today: date
    target_period: Period
    source_range: Period
    habit_entry_source_range: Period
    lags: tuple[int, ...]
    policy: Policy
    relationship_policy: RelationshipPolicy
    family: FamilySummary
    hypotheses: tuple[GuardrailHypothesis, ...]
