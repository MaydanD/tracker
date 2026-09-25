"""Stage 7D: statistical guardrails between the association/lag engines and Insights.

Pure and deterministic: every coefficient, pairing, coverage and temporal
segmentation is reused from Stages 7A-7E. This module only decides whether a
computed association is admissible evidence at all; it never recomputes a
coefficient, a lag alignment or a segment split.

Guardrails add: minimum sample size, pair coverage, binary group balance, a
minimum practically meaningful effect, within-weekday control, temporal blocking
(through the Stage 7E stability metrics) and Benjamini-Hochberg FDR for a whole
analysis family. Nothing here proves causation, ranks behaviour, predicts or
recommends anything.
"""

from datetime import date
from math import isfinite

from app.domain.analytics.confidence import evaluate_hypothesis
from app.domain.analytics.confidence_types import POLICY as CONFIDENCE_POLICY
from app.domain.analytics.correlation import pearson, spearman
from app.domain.analytics.descriptive_types import Period, SeriesPoint
from app.domain.analytics.guardrail_types import (
    BLOCKING_ORDER, BLOCKING_REASONS, POLICY, WARNING_ORDER, WARNINGS, CheckName, CheckStatus,
    EffectEvidence, FamilyMode, FamilySummary, GroupEvidence, GuardrailAnalytics,
    GuardrailCheck, GuardrailHypothesis, GuardrailVerdict, MultipleComparisonEvidence, Policy,
    Reason, WeekdayControlEvidence,
)
from app.domain.analytics.inference import benjamini_hochberg, cohens_d, median, method_p_value
from app.domain.analytics.lags import (
    align_lagged_pairs, normalize_lags, required_source_range, series_selector, shifted_period,
)
from app.domain.analytics.relationship_types import POLICY as RELATIONSHIP_POLICY, Contingency
from app.domain.analytics.relationships import PairedObservations, classify, filter_pairs
from app.domain.analytics.types import AnalyticsDataset, Grain, Variable, VariableType as T
from app.domain.progress import week_bounds


Hypothesis = tuple[str, str, int]

# Weekday outcomes map onto the shared reason tables; the rich outcome stays on
# the evidence itself.
WEEKDAY_BLOCKING = {"explained_by_weekday": "weekday_explained", "reversed": "weekday_reversal"}
# ``not_supported`` (a categorical pair) is reported as ``not_applicable`` and
# never warns; the remaining outcomes map onto the shared warning table.
WEEKDAY_WARNING = {"attenuated": "weekday_attenuation",
                   "insufficient_strata": "weekday_control_unavailable",
                   "not_evaluable": "weekday_control_unavailable"}


def paired_observations(dataset: AnalyticsDataset, start: date, end: date,
                        keys: tuple[str, str], lag: int) -> PairedObservations | None:
    """Valid paired points, using exactly the Stage 7C/7D primitives in order.

    Same order of operations as the Stage 7D engine (slice, series, lagged
    alignment, shared pairwise filtering), so counts and coverage always agree
    with the relationship the guardrail judges. Returns None for grain mismatch.
    """
    known = {variable.key: variable for variable in dataset.variables}
    x, y = known[keys[0]], known[keys[1]]
    if x.grain != y.grain:
        return None
    selected = series_selector(dataset)
    target = Period(start, end)
    required = required_source_range(target, (lag,), x.grain)
    target_points = selected(y, target)
    source = required if x.grain == Grain.DAILY else shifted_period(target, lag, x.grain)
    aligned = align_lagged_pairs(selected(x, source), target_points, lag, x.grain)
    return filter_pairs(x, y, aligned.x, aligned.y, today=dataset.today)


def _encode(point: SeriesPoint, variable: Variable) -> float:
    """Booleans enter comparisons as their 0/1 encoding, never as null."""
    return float(point.value is True) if variable.type == T.BOOLEAN else float(point.value)


def weekday_control(paired: PairedObservations | None, relationship, policy: Policy
                    ) -> WeekdayControlEvidence:
    """Within-weekday centering of the valid pairs, stratified by the Y target date.

    Weekday is taken from the **Y** date, because the requested analytical period
    (and therefore the lag hypothesis) is defined on Y. The adjusted coefficient is
    the *same statistic as the raw one* (Pearson, Spearman, point-biserial or Phi
    are all applied to the 0/1 encodings or to the ranks) computed on
    within-weekday centered values, so raw and adjusted magnitudes are directly
    comparable. Thin strata cannot inform a within-weekday contrast and are
    excluded from the adjusted estimate; no future information is used and the raw
    coefficient is never modified.
    """

    def result(status: CheckStatus, outcome: str, strata: int = 0, usable: int = 0,
               observations: int = 0, adjusted: float | None = None) -> WeekdayControlEvidence:
        raw = relationship.coefficient if relationship.status == "ok" else None
        difference = (abs(raw) - abs(adjusted)) if raw is not None and adjusted is not None else None
        attenuation = (difference / abs(raw)) if difference is not None and raw else None
        raw_direction = classify(raw, relationship.n)[0]
        adjusted_direction = classify(adjusted, observations)[0]
        change = (raw_direction in ("positive", "negative")
                  and adjusted_direction in ("positive", "negative")
                  and raw_direction != adjusted_direction)
        return WeekdayControlEvidence(
            status=status, outcome=outcome, weekday_basis="y_target_date", strata_count=strata,
            usable_strata_count=usable, observations=observations, raw_coefficient=raw,
            adjusted_coefficient=adjusted, absolute_difference=difference,
            relative_attenuation=attenuation, direction_change=change)

    if paired is None or relationship.grain is None or relationship.grain == Grain.WEEKLY:
        return result("not_applicable", "not_applicable")
    if T.CATEGORICAL in (relationship.x.type, relationship.y.type):
        return result("not_applicable", "not_supported")
    if relationship.coefficient is None or relationship.method is None:
        return result("not_evaluable", "not_evaluable")

    strata: dict[int, list[tuple[float, float]]] = {}
    for first, second in zip(paired.x, paired.y):
        strata.setdefault(second.date.weekday(), []).append(
            (_encode(first, relationship.x), _encode(second, relationship.y)))
    usable = {weekday: group for weekday, group in strata.items()
              if len(group) >= policy.weekday_minimum_stratum_observations}
    observations = sum(len(group) for group in usable.values())
    if len(usable) < policy.weekday_minimum_strata or observations < RELATIONSHIP_POLICY.calculation_minimum:
        return result("not_evaluable", "insufficient_strata", len(strata), len(usable),
                      observations)

    residuals_x: list[float] = []
    residuals_y: list[float] = []
    for group in usable.values():
        mean_x = sum(item[0] for item in group) / len(group)
        mean_y = sum(item[1] for item in group) / len(group)
        for value_x, value_y in group:
            residuals_x.append(value_x - mean_x)
            residuals_y.append(value_y - mean_y)
    # Same statistic as the raw coefficient, on centered observations: Pearson and
    # the 0/1 correlations (point-biserial, Phi) share the linear formula, while an
    # ordinal pair is ranked exactly as its raw Spearman coefficient was.
    fitted = (spearman if relationship.method == "spearman" else pearson)(
        residuals_x, residuals_y)
    if fitted.status == "constant_series":
        # Every value is explained by its own weekday: the raw association is a
        # week pattern rather than a within-weekday relationship.
        return result("failed", "explained_by_weekday", len(strata), len(usable), observations)
    if fitted.status != "ok" or fitted.coefficient is None:
        return result("not_evaluable", "not_evaluable", len(strata), len(usable), observations)
    evidence = result("passed", "retained", len(strata), len(usable), observations,
                      fitted.coefficient)
    if evidence.direction_change:
        return result("failed", "reversed", len(strata), len(usable), observations,
                      fitted.coefficient)
    if (evidence.relative_attenuation is not None
            and evidence.relative_attenuation > policy.weekday_maximum_relative_attenuation):
        return result("failed", "attenuated", len(strata), len(usable), observations,
                      fitted.coefficient)
    return evidence


def group_evidence(paired: PairedObservations | None, relationship) -> GroupEvidence | None:
    """Descriptive binary group evidence; null is never a group member."""
    types = (relationship.x.type, relationship.y.type)
    if paired is None or T.BOOLEAN not in types or T.CATEGORICAL in types:
        return None
    boolean_side = "x" if relationship.x.type == T.BOOLEAN else "y"
    flags = [point.value is True for point in (paired.x if boolean_side == "x" else paired.y)]
    others = paired.y if boolean_side == "x" else paired.x
    other_variable = relationship.y if boolean_side == "x" else relationship.x
    true_values = [_encode(point, other_variable) for flag, point in zip(flags, others) if flag]
    false_values = [_encode(point, other_variable) for flag, point in zip(flags, others) if not flag]
    contingency = None
    minimum_cell = None
    if relationship.x.type == relationship.y.type == T.BOOLEAN:
        counts = {(True, True): 0, (True, False): 0, (False, True): 0, (False, False): 0}
        for first, second in zip(paired.x, paired.y):
            counts[(first.value is True, second.value is True)] += 1
        contingency = Contingency(counts[(True, True)], counts[(True, False)],
                                  counts[(False, True)], counts[(False, False)])
        minimum_cell = min(counts.values())
    minority = min(len(true_values), len(false_values))
    total = max(len(true_values) + len(false_values), 1)
    difference = None
    if true_values and false_values:
        difference = sum(true_values) / len(true_values) - sum(false_values) / len(false_values)
    return GroupEvidence(
        boolean_side=boolean_side, true_count=len(true_values), false_count=len(false_values),
        minority_count=minority, minority_share=minority / total,
        true_mean=(sum(true_values) / len(true_values)) if true_values else None,
        false_mean=(sum(false_values) / len(false_values)) if false_values else None,
        true_median=median(true_values), false_median=median(false_values),
        absolute_mean_difference=abs(difference) if difference is not None else None,
        cohens_d=(cohens_d(true_values, false_values)
                  if other_variable.type == T.NUMERIC else None),
        contingency=contingency, minimum_cell_count=minimum_cell)


def effect_evidence(relationship, group: GroupEvidence | None, policy: Policy) -> EffectEvidence:
    coefficient = relationship.coefficient
    absolute = abs(coefficient) if coefficient is not None and isfinite(coefficient) else None
    return EffectEvidence(
        method=relationship.method, coefficient=coefficient, absolute_coefficient=absolute,
        minimum_absolute_effect=policy.minimum_absolute_effect,
        meets_minimum=absolute is not None and absolute >= policy.minimum_absolute_effect,
        group=group)


def _check(name: CheckName, status: CheckStatus, blocking: bool, detail: str,
           observed: float | None = None, threshold: float | None = None) -> GuardrailCheck:
    return GuardrailCheck(name, status, blocking, detail, observed, threshold)


def evaluate_checks(relationship, sample, coverage, stability, weekday, effect, policy: Policy,
                    *, evaluated: bool) -> tuple[GuardrailCheck, ...]:
    """The six per-hypothesis guardrail checks (multiplicity is added per family)."""
    if not evaluated:
        return tuple(_check(name, "not_evaluable", False, "relationship_not_computed")
                     for name in ("sample_size", "coverage", "group_balance", "effect_size",
                                  "weekday_control", "temporal_stability"))

    if sample.n >= policy.warning_below_n:
        sample_check = _check("sample_size", "passed", False, "sufficient_sample",
                              sample.n, policy.minimum_n)
    elif sample.n >= policy.minimum_n:
        sample_check = _check("sample_size", "failed", False, "small_sample",
                              sample.n, policy.minimum_n)
    else:
        sample_check = _check("sample_size", "failed", True, "insufficient_sample",
                              sample.n, policy.minimum_n)

    if coverage.pair_coverage is None:
        coverage_check = _check("coverage", "not_evaluable", False, "coverage_not_computed")
    elif coverage.pair_coverage >= policy.warning_below_pair_coverage:
        coverage_check = _check("coverage", "passed", False, "sufficient_coverage",
                                coverage.pair_coverage, policy.minimum_pair_coverage)
    elif coverage.pair_coverage >= policy.minimum_pair_coverage:
        coverage_check = _check("coverage", "failed", False, "moderate_coverage",
                                coverage.pair_coverage, policy.minimum_pair_coverage)
    else:
        coverage_check = _check("coverage", "failed", True, "insufficient_coverage",
                                coverage.pair_coverage, policy.minimum_pair_coverage)

    group = effect.group
    if group is None:
        balance_check = _check("group_balance", "not_applicable", False, "not_binary_comparison")
    elif (group.minority_count < policy.minimum_group_observations
          or (group.minority_share or 0.0) < policy.minimum_minority_share):
        balance_check = _check("group_balance", "failed", True, "insufficient_group_balance",
                               group.minority_count, policy.minimum_group_observations)
    elif (group.minimum_cell_count is not None
          and group.minimum_cell_count < policy.minimum_contingency_cell):
        balance_check = _check("group_balance", "failed", True, "sparse_contingency_cell",
                               group.minimum_cell_count, policy.minimum_contingency_cell)
    else:
        balance_check = _check("group_balance", "passed", False, "balanced_groups",
                               group.minority_count, policy.minimum_group_observations)

    if effect.absolute_coefficient is None:
        effect_check = _check("effect_size", "not_evaluable", False, "effect_not_computed")
    elif effect.meets_minimum:
        effect_check = _check("effect_size", "passed", False, "meaningful_effect",
                              effect.absolute_coefficient, policy.minimum_absolute_effect)
    else:
        effect_check = _check("effect_size", "failed", True, "below_effect_threshold",
                              effect.absolute_coefficient, policy.minimum_absolute_effect)

    if weekday.status == "not_applicable":
        weekday_check = _check("weekday_control", "not_applicable", False, weekday.outcome)
    elif weekday.outcome in WEEKDAY_BLOCKING:
        weekday_check = _check("weekday_control", "failed", True, WEEKDAY_BLOCKING[weekday.outcome])
    elif weekday.outcome == "not_evaluable":
        weekday_check = _check("weekday_control", "not_evaluable", False,
                               WEEKDAY_WARNING["not_evaluable"])
    elif weekday.outcome in WEEKDAY_WARNING:
        weekday_check = _check("weekday_control", "failed", False, WEEKDAY_WARNING[weekday.outcome])
    else:
        weekday_check = _check("weekday_control", "passed", False, "weekday_control_passed")

    if stability.segment_count == 0:
        temporal_check = _check("temporal_stability", "not_applicable", False, "not_segmented")
    elif stability.analyzable_segment_count < policy.temporal_minimum_analyzable_segments:
        # Too little analyzable history is missing evidence, never evidence of
        # instability: it warns and can never block.
        temporal_check = _check("temporal_stability", "failed", False,
                                "insufficient_temporal_evidence",
                                stability.analyzable_segment_count,
                                policy.temporal_minimum_analyzable_segments)
    elif stability.meaningful_reversal:
        temporal_check = _check("temporal_stability", "failed", True, "temporal_reversal",
                                stability.opposite_direction_count, 0)
    elif not stability.direction_consistent:
        temporal_check = _check("temporal_stability", "failed", True,
                                "temporal_direction_inconsistency", stability.same_direction_count,
                                stability.analyzable_segment_count)
    elif not stability.magnitude_stable:
        temporal_check = _check("temporal_stability", "failed", False, "magnitude_instability",
                                stability.maximum_deviation_from_full,
                                CONFIDENCE_POLICY.stable_maximum_deviation_from_full)
    else:
        temporal_check = _check("temporal_stability", "passed", False, "temporally_consistent",
                                stability.same_direction_count, stability.analyzable_segment_count)
    return (sample_check, coverage_check, balance_check, effect_check, weekday_check, temporal_check)


def analyze(dataset: AnalyticsDataset, start: date, end: date, hypotheses: tuple[Hypothesis, ...],
            *, mode: FamilyMode) -> GuardrailAnalytics:
    """Evaluate a whole analysis family on one already-loaded dataset."""
    if not hypotheses:
        raise ValueError("Нужна хотя бы одна гипотеза.")
    prepared = []
    for x_key, y_key, lag in hypotheses:
        lag = normalize_lags((lag,))[0]
        evaluation = evaluate_hypothesis(dataset, start, end, (x_key, y_key), lag)
        relationship = evaluation.relationship
        paired = paired_observations(dataset, start, end, (x_key, y_key), lag)
        effect = effect_evidence(relationship, group_evidence(paired, relationship), POLICY)
        weekday = weekday_control(paired, relationship, POLICY)
        checks = evaluate_checks(relationship, evaluation.sample, evaluation.coverage,
                                 evaluation.stability, weekday, effect, POLICY,
                                 evaluated=evaluation.evaluated)
        p_values = tuple(method_p_value(metric.method, metric.coefficient, relationship.n)
                         for metric in relationship.metrics)
        prepared.append((evaluation, effect, weekday, checks, p_values))

    tested = [index for index, item in enumerate(prepared) if item[4] and item[4][0] is not None]
    checked = len(tested) > 1
    adjusted = benjamini_hochberg(tuple(prepared[index][4][0] for index in tested)) if checked else ()
    q_values = dict(zip(tested, adjusted))
    ranks = {index: rank + 1 for rank, index in enumerate(sorted(
        tested, key=lambda index: (prepared[index][4][0], index)))}

    built = []
    for index, (evaluation, effect, weekday, checks, p_values) in enumerate(prepared):
        relationship = evaluation.relationship
        primary_p = p_values[0] if p_values else None
        q_value = q_values.get(index)
        if primary_p is None:
            status: CheckStatus = "not_evaluable"
        elif not checked:
            # A single pre-selected hypothesis needs no multiplicity control; the
            # raw p-value is still reported.
            status = "not_applicable"
        elif q_value is not None and q_value <= POLICY.fdr_threshold:
            status = "passed"
        else:
            status = "failed"
        comparison = MultipleComparisonEvidence(
            family_mode=mode, family_size=len(prepared), tested_size=len(tested),
            family_rank=ranks.get(index), method="benjamini_hochberg",
            threshold=POLICY.fdr_threshold, status=status, raw_p_value=primary_p,
            adjusted_q_value=q_value, passed=None if status in ("not_applicable", "not_evaluable")
            else status == "passed")
        detail = {"passed": "passes_fdr", "failed": "false_discovery_risk",
                  "not_applicable": "multiple_comparisons_not_applicable",
                  "not_evaluable": "multiple_comparisons_not_evaluable"}[status]
        family_check = _check("multiple_comparisons", status, blocking=status == "failed",
                              detail=detail, observed=q_value, threshold=POLICY.fdr_threshold)
        all_checks = (*checks, family_check)
        blocking = {check.detail for check in all_checks if check.blocking}
        blocking_codes = [code for code in BLOCKING_ORDER if code in blocking]
        warnings = {check.detail for check in all_checks
                    if check.status in ("failed", "not_evaluable") and not check.blocking}
        if (evaluation.evaluated and relationship.coverage is not None
                and relationship.coverage.losses["incomplete_period"] > 0):
            warnings.add("partial_period")
        if not evaluation.evaluated:
            verdict: GuardrailVerdict = "not_evaluable"
        elif blocking_codes:
            verdict = "blocked"
        elif warnings:
            verdict = "pass_with_warnings"
        else:
            verdict = "pass"
        built.append(GuardrailHypothesis(
            index=index, x=relationship.x, y=relationship.y, grain=relationship.grain,
            lag=relationship.lag, lag_unit=relationship.lag_unit,
            target_period=relationship.target_period, verdict=verdict,
            relationship=relationship, sample=evaluation.sample, coverage=evaluation.coverage,
            stability=evaluation.stability, effect=effect, weekday=weekday,
            multiple_comparisons=comparison, checks=all_checks,
            blocking_reasons=tuple(Reason(code, *BLOCKING_REASONS[code]) for code in blocking_codes),
            warnings=tuple(Reason(code, *WARNINGS[code]) for code in WARNING_ORDER
                           if code in warnings)))

    verdicts: dict[GuardrailVerdict, int] = {
        name: sum(1 for item in built if item.verdict == name)
        for name in ("pass", "pass_with_warnings", "blocked", "not_evaluable")}
    return GuardrailAnalytics(
        contract_version="7F.1", dataset_contract_version=dataset.contract_version,
        guardrail_policy_version=POLICY.version, today=dataset.today,
        target_period=Period(start, end), source_range=Period(dataset.start, dataset.end),
        habit_entry_source_range=Period(week_bounds(dataset.start)[0], week_bounds(dataset.end)[1]),
        lags=tuple(sorted({item.lag for item in built})), policy=POLICY,
        relationship_policy=RELATIONSHIP_POLICY,
        family=FamilySummary(
            mode=mode, requested_size=len(prepared),
            evaluable_size=sum(1 for item in prepared if item[0].evaluated),
            tested_size=len(tested), fdr_method="benjamini_hochberg",
            fdr_threshold=POLICY.fdr_threshold, multiple_comparisons_checked=checked,
            verdicts=verdicts),
        hypotheses=tuple(built))


def guardrail_summary(result: GuardrailAnalytics):
    """Compact verdict for one hypothesis, for the Stage 7E confidence response."""
    from app.domain.analytics.confidence_types import GuardrailSummary

    first = result.hypotheses[0]
    return GuardrailSummary(
        policy_version=result.guardrail_policy_version, status=first.verdict,
        family_size=result.family.tested_size,
        blocking_reasons=tuple(reason.code for reason in first.blocking_reasons),
        warnings=tuple(reason.code for reason in first.warnings))
