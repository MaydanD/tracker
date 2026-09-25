"""Stage 7D guardrail policy: boundaries, balance, effect, weekday, FDR families.

Guardrails decide whether a computed association is admissible evidence at all.
These tests pin every policy boundary, every reason code and the pure math, on
synthetic data whose numbers are asserted explicitly.
"""

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from app.domain.analytics.builder import build_dataset, dates
from app.domain.analytics.confidence import evaluate_hypothesis
from app.domain.analytics.guardrail_types import (
    BLOCKING_ORDER, BLOCKING_REASONS, POLICY, WARNING_ORDER, WARNINGS,
)
from app.domain.analytics.guardrails import (
    analyze, effect_evidence, group_evidence, guardrail_summary, weekday_control,
)
from app.domain.analytics.lags import align_lagged_pairs
from app.domain.analytics.relationships import analyze_paired, filter_pairs
from app.domain.analytics.types import DatasetInput, Grain, VariableType as T
from app.domain.daily_state import StateValues
from app.schemas.guardrails import GuardrailAnalyticsRead
from tests.test_relationships import MON, X, Y, points


TODAY = MON + timedelta(days=400)
SLEEP, COMPUTER = "state.sleep_minutes", "state.computer_minutes"
KEYS = (SLEEP, COMPUTER)


def lcg(count, seed=7):
    value, out = seed, []
    for _ in range(count):
        value = (value * 1103515245 + 12345) % (2 ** 31)
        out.append(200 + value % 1000)
    return out


def dataset(start, end, values=None, *, today=TODAY):
    days = list(dates(start, end))
    if values is None:
        values = [StateValues(sleep_minutes=i + 1, computer_minutes=2 * i + 3, mood=i % 5 + 1,
                              alcohol=bool(i % 2)) for i in range(len(days))]
    return build_dataset(DatasetInput((), dict(zip(days, values))), start, end, today=today)


def state_dataset(start, count, *, slope, today=TODAY):
    """sleep (X) against a noisy linear function of sleep (Y), both daily numeric."""
    x, z = lcg(count), lcg(count, seed=13)
    days = list(dates(start, start + timedelta(days=count - 1)))
    values = [StateValues(sleep_minutes=a,
                          computer_minutes=min(1440, max(0, int(slope * a + 0.55 * w))))
              for a, w in zip(x, z)]
    return build_dataset(DatasetInput((), dict(zip(days, values))), start, days[-1], today=today)


def observations(a, b, tx=T.NUMERIC, ty=T.NUMERIC, *, lag=0, grain=Grain.DAILY):
    """Aligned, pairwise-filtered observations plus their Stage 7C relationship.

    A positive lag joins X on an earlier date to its Y through the Stage 7D
    alignment primitive, so the sign convention under test is the engine's own;
    weekly series walk canonical Monday weeks instead of days.
    """
    x = replace(X, type=tx, grain=grain)
    y = replace(Y, type=ty, grain=grain)
    step = 7 if grain == Grain.WEEKLY else 1
    xs, ys = points(a, step=step), points(b, step=step)
    if lag:
        aligned = align_lagged_pairs(xs, ys, lag, grain)
        xs, ys = aligned.x, aligned.y
    paired = filter_pairs(x, y, xs, ys, today=TODAY)
    return x, y, paired, analyze_paired(x, y, xs, ys, paired)


def one(result, lag=0):
    return next(item for item in result.hypotheses if item.lag == lag)


def check(hypothesis, name):
    return next(item for item in hypothesis.checks if item.name == name)


def codes(reasons):
    return [reason.code for reason in reasons]


def balance(a, b, tx=T.BOOLEAN, ty=T.NUMERIC):
    x, y, paired, relationship = observations(a, b, tx, ty)
    return group_evidence(paired, relationship)


# --- minimum sample size -------------------------------------------------------------

@pytest.mark.parametrize("length,status,blocking", [
    (4, "not_evaluable", False),      # the coefficient itself is not computable
    (5, "failed", True),              # computable, but too little for evidence
    (9, "failed", True),
    (10, "failed", False),            # warning band
    (19, "failed", False),
    (20, "passed", False),
    (21, "passed", False),
])
def test_sample_size_boundaries(length, status, blocking):
    end = MON + timedelta(days=length - 1)
    hypothesis = analyze(dataset(MON, end), MON, end, (KEYS + (0,),), mode="single").hypotheses[0]
    if length < 5:
        assert hypothesis.verdict == "not_evaluable"
        assert all(item.status in ("not_evaluable", "not_applicable")
                   for item in hypothesis.checks)
        assert not any(item.blocking for item in hypothesis.checks)
        return
    assert hypothesis.sample.n == length
    assert check(hypothesis, "sample_size").status == status
    assert check(hypothesis, "sample_size").blocking is blocking
    assert hypothesis.sample.minimum_n_met is (length >= 5)
    assert hypothesis.sample.stable_n_met is (length >= 20)


def test_small_sample_warns_without_blocking_and_a_large_sample_passes():
    small = analyze(dataset(MON, MON + timedelta(days=18)), MON, MON + timedelta(days=18),
                    (KEYS + (0,),), mode="single").hypotheses[0]
    assert small.verdict == "pass_with_warnings"
    assert codes(small.warnings) == ["small_sample"]
    assert small.blocking_reasons == ()
    large = analyze(dataset(MON, MON + timedelta(days=19)), MON, MON + timedelta(days=19),
                    (KEYS + (0,),), mode="single").hypotheses[0]
    assert large.verdict == "pass" and large.warnings == ()


# --- pair coverage -------------------------------------------------------------------

def sparse_dataset(paired_days, *, length=30):
    days = list(dates(MON, MON + timedelta(days=length - 1)))
    values = [StateValues(sleep_minutes=600 + i,
                          computer_minutes=2 * i if i < paired_days else None)
              for i in range(length)]
    return build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)


@pytest.mark.parametrize("paired_days,status,blocking", [
    (8, "failed", True),      # 26.7% blocks
    (11, "failed", True),     # 36.7% still blocks
    (12, "failed", False),    # exactly 40% is a warning, not a blocker
    (17, "failed", False),
    (18, "passed", False),    # exactly 60% passes
    (30, "passed", False),
])
def test_coverage_boundaries(paired_days, status, blocking):
    end = MON + timedelta(days=29)
    hypothesis = analyze(sparse_dataset(paired_days), MON, end, (KEYS + (0,),),
                         mode="single").hypotheses[0]
    coverage = check(hypothesis, "coverage")
    assert coverage.observed == pytest.approx(paired_days / 30)
    assert coverage.status == status and coverage.blocking is blocking
    if blocking:
        assert "insufficient_coverage" in codes(hypothesis.blocking_reasons)
    elif status == "failed":
        assert "moderate_coverage" in codes(hypothesis.warnings)


def test_coverage_counts_eligible_pairs_not_calendar_days():
    end = MON + timedelta(days=29)
    hypothesis = analyze(sparse_dataset(8), MON, end, (KEYS + (0,),), mode="single").hypotheses[0]
    assert hypothesis.sample.requested_count == 30
    assert hypothesis.sample.n == 8
    assert hypothesis.coverage.pair_coverage == pytest.approx(8 / 30)
    assert hypothesis.coverage.stable_coverage_met is False
    assert hypothesis.coverage.low_coverage is True


# --- binary group balance ------------------------------------------------------------

def test_group_balance_balanced_and_eighty_twenty_pass():
    even = balance([True] * 50 + [False] * 50, list(range(100)))
    assert (even.true_count, even.false_count) == (50, 50)
    assert even.minority_share == pytest.approx(0.5)
    skewed = balance([True] * 80 + [False] * 20, list(range(100)))
    assert skewed.minority_count == 20 and skewed.minority_share == pytest.approx(0.20)


def test_group_balance_ninety_five_five_fails_but_the_coefficient_survives():
    x, y, paired, relationship = observations([True] * 95 + [False] * 5, list(range(100)),
                                              T.BOOLEAN)
    evidence = group_evidence(paired, relationship)
    assert evidence.minority_count == 5 and evidence.minority_share == pytest.approx(0.05)
    assert evidence.minority_share < POLICY.minimum_minority_share
    assert relationship.coefficient is not None       # imbalance never erases the number


@pytest.mark.parametrize("total,minority,expected", [
    (20, 4, False),     # too few in the minority group
    (20, 5, True),      # exactly five, well represented
    (100, 14, False),   # share just under 15%
    (100, 15, True),    # share exactly 15%
    (33, 5, True),      # 15.2% of a small sample
    (34, 5, False),     # 14.7% of a slightly larger one
])
def test_group_balance_boundaries(total, minority, expected):
    evidence = balance([True] * (total - minority) + [False] * minority, list(range(total)))
    assert evidence.minority_count == minority
    assert (evidence.minority_count >= POLICY.minimum_group_observations
            and evidence.minority_share >= POLICY.minimum_minority_share) is expected


def test_group_balance_ignores_null_and_never_turns_it_into_false():
    evidence = balance([True] * 5 + [False] * 5 + [None] * 5, list(range(15)))
    assert (evidence.true_count, evidence.false_count) == (5, 5)
    assert evidence.minority_share == pytest.approx(0.5)


def test_group_balance_counts_false_only_observations():
    evidence = balance([False] * 20, list(range(20)))
    assert (evidence.true_count, evidence.false_count) == (0, 20)
    assert evidence.minority_count == 0
    assert evidence.true_mean is None and evidence.false_mean is not None


def test_group_evidence_reports_means_medians_and_cohens_d():
    evidence = balance([True, True, False, False], [10.0, 12.0, 14.0, 16.0])
    assert evidence.true_mean == pytest.approx(11.0) and evidence.false_mean == pytest.approx(15.0)
    assert evidence.true_median == pytest.approx(11.0) and evidence.false_median == pytest.approx(15.0)
    assert evidence.absolute_mean_difference == pytest.approx(4.0)
    assert evidence.cohens_d == pytest.approx(-4.0 / (2 ** 0.5), abs=0.01)   # pooled sd = sqrt(2)


def test_group_evidence_is_absent_for_numeric_pairs_and_ordinal_effect_has_no_d():
    _, _, paired, numeric = observations(list(range(20)), [i % 5 + 1 for i in range(20)])
    assert group_evidence(paired, numeric) is None
    _, _, ordinal_paired, ordinal = observations([True] * 10 + [False] * 10,
                                                 [i % 5 + 1 for i in range(20)],
                                                 T.BOOLEAN, T.ORDINAL)
    evidence = group_evidence(ordinal_paired, ordinal)
    assert evidence.true_mean is not None and evidence.cohens_d is None


def test_sparse_contingency_cell_blocks_boolean_boolean():
    days = list(dates(MON, MON + timedelta(days=29)))
    values = [StateValues(alcohol=5 <= i <= 10, gaming=15 <= i <= 20) for i in range(30)]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)
    hypothesis = analyze(data, MON, days[-1], (("state.alcohol", "state.gaming", 0),),
                         mode="single").hypotheses[0]
    assert hypothesis.effect.group.contingency == hypothesis.relationship.contingency
    assert hypothesis.effect.group.minimum_cell_count == 0
    assert check(hypothesis, "group_balance").detail == "sparse_contingency_cell"
    assert "sparse_contingency_cell" in codes(hypothesis.blocking_reasons)


def test_dense_boolean_contingency_passes_balance():
    x_values = [True] * 10 + [False] * 10 + [True] * 10 + [False] * 10
    y_values = [True] * 10 + [True] * 10 + [False] * 10 + [False] * 10
    x, y, paired, relationship = observations(x_values, y_values, T.BOOLEAN, T.BOOLEAN)
    evidence = group_evidence(paired, relationship)
    assert evidence.minimum_cell_count == 10
    assert evidence.minority_share == pytest.approx(0.5)


# --- minimum meaningful effect -------------------------------------------------------

@pytest.mark.parametrize("coefficient,meets", [
    (0.15, True), (0.1500000001, True), (0.1499999, False),
    (-0.15, True), (-0.9, True), (-0.1499999, False),
    (0.0, False), (0.1, False), (None, False),
])
def test_effect_threshold_is_two_sided_and_never_hides_the_coefficient(coefficient, meets):
    _, _, _, relationship = observations(list(range(20)), list(range(20)))
    evidence = effect_evidence(replace(relationship, coefficient=coefficient), None, POLICY)
    assert evidence.minimum_absolute_effect == POLICY.minimum_absolute_effect == 0.15
    assert evidence.meets_minimum is meets
    assert evidence.coefficient == coefficient
    assert evidence.absolute_coefficient == (None if coefficient is None else abs(coefficient))


def test_below_effect_threshold_blocks_but_keeps_the_number():
    end = MON + timedelta(days=89)
    hypothesis = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),),
                         mode="single").hypotheses[0]
    assert hypothesis.effect.coefficient == pytest.approx(0.1205, abs=0.005)
    assert hypothesis.verdict == "blocked"
    assert codes(hypothesis.blocking_reasons) == ["below_effect_threshold"]
    assert check(hypothesis, "effect_size").blocking is True
    assert hypothesis.relationship.coefficient == hypothesis.effect.coefficient


def test_large_n_does_not_make_a_tiny_effect_meaningful():
    end = MON + timedelta(days=89)
    hypothesis = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),),
                         mode="single").hypotheses[0]
    assert hypothesis.sample.n == 90                      # plenty of observations
    assert hypothesis.sample.stable_n_met is True
    assert check(hypothesis, "effect_size").status == "failed"


def test_strong_effect_passes_and_strength_is_independent_of_the_verdict():
    end = MON + timedelta(days=89)
    strong = analyze(state_dataset(MON, 90, slope=0.6), MON, end, (KEYS + (0,),),
                     mode="single").hypotheses[0]
    weak = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),),
                   mode="single").hypotheses[0]
    assert check(strong, "effect_size").status == "passed"
    assert strong.relationship.strength == "strong" and strong.verdict == "pass"
    assert weak.verdict == "blocked" and weak.relationship.coefficient is not None


# --- weekday control -----------------------------------------------------------------

def weekday_series(length=70, weekday=4, value=1.0):
    return [value if (MON + timedelta(days=index)).weekday() == weekday else 0.0
            for index in range(length)]


def test_pure_weekday_confounder_is_explained_and_blocked():
    _, _, paired, relationship = observations(weekday_series(), weekday_series())
    assert relationship.coefficient == pytest.approx(1.0)       # raw association is strong
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "explained_by_weekday"
    assert evidence.status == "failed"
    assert evidence.adjusted_coefficient is None                # no fabricated number
    assert evidence.absolute_difference is None and evidence.relative_attenuation is None
    assert evidence.weekday_basis == "y_target_date"
    assert evidence.strata_count == evidence.usable_strata_count == 7


def weekday_structured(within_x, within_y, *, length=28, offsets=None):
    """Values laid out day by day so each real weekday gets its own baseline."""
    x_values, y_values = [], []
    for index in range(length):
        weekday, position = index % 7, index // 7
        offset = (offsets or (lambda item: 10.0 * item))(weekday)
        x_values.append(offset + within_x[position % len(within_x)])
        y_values.append(offset + within_y[position % len(within_y)])
    return x_values, y_values


def test_within_weekday_relationship_is_retained():
    values = [float(index % 5) for index in range(70)]
    _, _, paired, relationship = observations(values, [value * 2 + 5 for value in values])
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "retained" and evidence.status == "passed"
    assert evidence.adjusted_coefficient == pytest.approx(1.0)
    assert evidence.relative_attenuation == pytest.approx(0.0)
    assert evidence.direction_change is False


def test_ordinal_pair_uses_its_own_rank_statistic_for_the_adjusted_value():
    values = [float(index % 5) for index in range(70)]
    _, _, paired, relationship = observations(values, [value * 2 + 5 for value in values],
                                             T.ORDINAL, T.NUMERIC)
    assert relationship.method == "spearman"
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "retained"
    assert evidence.adjusted_coefficient == pytest.approx(1.0)


def test_weekday_reversal_is_blocked():
    x_values, y_values = weekday_structured([0.0, 1.0, 2.0, 3.0], [3.0, 2.0, 1.0, 0.0])
    _, _, paired, relationship = observations(x_values, y_values)
    assert relationship.coefficient > 0.5          # between-weekday trend dominates
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "reversed" and evidence.direction_change is True
    assert evidence.adjusted_coefficient < 0 and evidence.status == "failed"


def test_weekday_attenuation_is_a_warning_not_a_blocker():
    x_values, y_values = weekday_structured([0.0, 1.0, 2.0, 3.0], [1.0, -1.0, -1.0, 1.0],
                                            offsets=lambda weekday: 10.0 if weekday >= 5 else -10.0)
    _, _, paired, relationship = observations(x_values, y_values)
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "attenuated"
    assert evidence.relative_attenuation > POLICY.weekday_maximum_relative_attenuation
    assert evidence.direction_change is False and evidence.adjusted_coefficient is not None
    assert evidence.adjusted_coefficient == pytest.approx(0.0, abs=0.05)


def test_weekday_control_refuses_thin_strata():
    _, _, paired, relationship = observations([float(index) for index in range(7)],
                                             [float(index) for index in range(7)])
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.outcome == "insufficient_strata" and evidence.status == "not_evaluable"
    assert evidence.adjusted_coefficient is None


def test_weekday_control_is_not_applicable_to_weekly_or_categorical_pairs():
    weekly = observations([float(index) for index in range(20)],
                          [float(index) for index in range(20)], grain=Grain.WEEKLY)
    evidence = weekday_control(weekly[2], weekly[3], POLICY)
    assert evidence.status == "not_applicable" and evidence.outcome == "not_applicable"
    categorical = observations(["a", "b"] * 10, ["a", "b"] * 10, T.CATEGORICAL, T.CATEGORICAL)
    evidence = weekday_control(categorical[2], categorical[3], POLICY)
    assert evidence.status == "not_applicable" and evidence.outcome == "not_supported"


def test_lagged_weekday_control_stratifies_by_the_target_date():
    base = [float(index % 9) for index in range(80)]
    y = [value + 3.0 * ((MON + timedelta(days=index)).weekday())
         for index, value in enumerate(base)]
    x = y[1:] + [y[-1]]                       # X is the previous target day: lag +1
    _, _, paired, relationship = observations(x, y, lag=1)
    evidence = weekday_control(paired, relationship, POLICY)
    assert evidence.weekday_basis == "y_target_date"
    assert evidence.outcome == "retained" and evidence.adjusted_coefficient is not None
    assert all(first.date == second.date - timedelta(days=1)
               for first, second in zip(paired.x, paired.y))


def test_lagged_pure_weekday_rhythm_is_still_explained():
    y = weekday_series(weekday=5)
    x = y[1:] + [y[-1]]                       # X is the previous target day: lag +1
    _, _, paired, relationship = observations(x, y, lag=1)
    assert relationship.coefficient == pytest.approx(1.0)
    assert weekday_control(paired, relationship, POLICY).outcome == "explained_by_weekday"


# --- temporal stability (reusing Stage 7E evidence) ----------------------------------

def test_temporal_checks_reuse_the_stage_7e_evaluation_verbatim():
    data = state_dataset(MON, 90, slope=0.6)
    end = MON + timedelta(days=89)
    hypothesis = one(analyze(data, MON, end, (KEYS + (0,),), mode="single"))
    evaluation = evaluate_hypothesis(data, MON, end, KEYS, 0)
    assert hypothesis.stability == evaluation.stability
    assert hypothesis.sample == evaluation.sample
    assert hypothesis.coverage == evaluation.coverage
    assert hypothesis.relationship == evaluation.relationship
    assert check(hypothesis, "temporal_stability").status == "passed"
    assert hypothesis.stability.analyzable_segment_count == 3


def test_recent_reversal_blocks_with_temporal_reversal():
    x = lcg(90)
    y = [value if index < 60 else 1400 - value for index, value in enumerate(x)]
    days = list(dates(MON, MON + timedelta(days=89)))
    values = [StateValues(sleep_minutes=a, computer_minutes=b) for a, b in zip(x, y)]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)
    hypothesis = one(analyze(data, MON, days[-1], (KEYS + (0,),), mode="single"))
    assert hypothesis.stability.coefficients == pytest.approx((1.0, 1.0, -1.0))
    assert hypothesis.stability.meaningful_reversal is True
    assert check(hypothesis, "temporal_stability").detail == "temporal_reversal"
    assert codes(hypothesis.blocking_reasons) == ["temporal_reversal"]


def test_short_history_only_warns_about_temporal_evidence():
    end = MON + timedelta(days=7)
    hypothesis = analyze(dataset(MON, end), MON, end, (KEYS + (0,),), mode="single").hypotheses[0]
    temporal = check(hypothesis, "temporal_stability")
    assert temporal.status == "failed" and temporal.blocking is False
    assert temporal.detail == "insufficient_temporal_evidence"
    assert temporal.observed == 0
    assert "insufficient_temporal_evidence" in codes(hypothesis.warnings)


# --- multiple comparisons: family semantics ------------------------------------------

def test_single_hypothesis_needs_no_correction_but_keeps_the_raw_p_value():
    data = state_dataset(MON - timedelta(days=7), 37, slope=0.3)
    end = MON + timedelta(days=29)
    result = analyze(data, MON, end, (KEYS + (0,),), mode="single")
    hypothesis = one(result)
    comparison = hypothesis.multiple_comparisons
    assert result.family.mode == "single"
    assert result.family.multiple_comparisons_checked is False
    assert comparison.status == "not_applicable" and comparison.passed is None
    assert comparison.adjusted_q_value is None
    assert comparison.raw_p_value == pytest.approx(0.0224, abs=0.002)
    assert hypothesis.verdict == "pass_with_warnings"


def test_family_size_can_block_a_hypothesis_that_passes_the_raw_threshold():
    data = state_dataset(MON - timedelta(days=7), 37, slope=0.3)
    end = MON + timedelta(days=29)
    alone = one(analyze(data, MON, end, (KEYS + (0,),), mode="single"))
    assert alone.multiple_comparisons.raw_p_value < POLICY.fdr_threshold
    assert "false_discovery_risk" not in codes(alone.blocking_reasons)
    family = analyze(data, MON, end, tuple(KEYS + (lag,) for lag in range(8)), mode="lag_scan")
    target = one(family, lag=0)
    assert family.family.requested_size == family.family.tested_size == 8
    assert target.multiple_comparisons.raw_p_value < POLICY.fdr_threshold
    assert target.multiple_comparisons.family_rank == 1
    assert target.multiple_comparisons.adjusted_q_value > POLICY.fdr_threshold
    assert "false_discovery_risk" in codes(target.blocking_reasons)
    assert target.verdict == "blocked"


def test_lag_family_is_corrected_together_and_the_real_lag_survives():
    start = MON - timedelta(days=8)
    sleep = lcg(98)
    days = list(dates(start, start + timedelta(days=97)))
    values = [StateValues(sleep_minutes=a, computer_minutes=b) for a, b in zip(sleep, sleep[2:])]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), start, days[-1], today=TODAY)
    family = analyze(data, MON, MON + timedelta(days=89),
                     tuple((COMPUTER, SLEEP, lag) for lag in range(8)), mode="lag_scan")
    assert family.family.requested_size == 8
    assert [item.lag for item in family.hypotheses if item.verdict == "pass"] == [2]
    assert all("false_discovery_risk" in codes(item.blocking_reasons)
               for item in family.hypotheses if item.verdict == "blocked")
    assert sorted(item.multiple_comparisons.family_rank for item in family.hypotheses) == list(range(1, 9))


def test_matrix_family_is_one_family_and_only_the_real_association_passes():
    keys = (SLEEP, COMPUTER, "state.mood", "state.alcohol", "state.gaming")
    days = list(dates(MON, MON + timedelta(days=89)))
    x, z = lcg(90), lcg(90, seed=13)
    values = [StateValues(sleep_minutes=a,
                          computer_minutes=min(1440, max(0, int(0.6 * a + 0.5 * b))),
                          mood=1 + (index * 7) % 5, alcohol=(index * 5) % 11 < 2,
                          gaming=(index * 3) % 13 < 2)
              for index, (a, b) in enumerate(zip(x, z))]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)
    hypotheses = tuple((first, second, 0) for index, first in enumerate(keys)
                       for second in keys[index + 1:])
    result = analyze(data, MON, days[-1], hypotheses, mode="matrix")
    assert result.family.mode == "matrix"
    assert result.family.requested_size == len(hypotheses) == 10
    assert result.family.multiple_comparisons_checked is True
    assert {(item.x.key, item.y.key) for item in result.hypotheses
            if item.verdict == "pass"} == {(SLEEP, COMPUTER)}
    assert result.family.verdicts["pass"] == 1
    assert all(item.multiple_comparisons.adjusted_q_value is None
               or 0.0 <= item.multiple_comparisons.adjusted_q_value <= 1.0
               for item in result.hypotheses)


def test_blocked_hypotheses_are_reported_with_their_reasons():
    end = MON + timedelta(days=89)
    result = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),), mode="single")
    assert len(result.hypotheses) == result.family.requested_size == 1
    hypothesis = one(result)
    assert hypothesis.verdict == "blocked"
    assert hypothesis.relationship.coefficient is not None     # the number stays visible
    assert hypothesis.blocking_reasons
    assert all(reason.label and reason.message for reason in hypothesis.blocking_reasons)


def test_hypotheses_without_a_p_value_leave_the_denominator_but_stay_in_the_response():
    days = list(dates(MON, MON + timedelta(days=29)))
    values = [StateValues(sleep_minutes=600 + index % 7, computer_minutes=float(index),
                          sleep_status=("normal" if index % 2 else "underslept"))
              for index in range(30)]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)
    hypotheses = ((SLEEP, COMPUTER, 0), (SLEEP, "state.sleep_status", 0))
    result = analyze(data, MON, days[-1], hypotheses, mode="matrix")
    unsupported = next(item for item in result.hypotheses if item.y.key == "state.sleep_status")
    assert unsupported.verdict == "not_evaluable"
    assert unsupported.multiple_comparisons.raw_p_value is None
    assert unsupported.multiple_comparisons.status == "not_evaluable"
    assert result.family.requested_size == 2 and result.family.tested_size == 1
    assert result.family.multiple_comparisons_checked is False
    assert one(result).multiple_comparisons.status == "not_applicable"


# --- statuses, ordering, determinism and serialization -------------------------------

def test_grain_mismatch_stays_not_evaluable():
    end = MON + timedelta(days=29)
    hypothesis = analyze(dataset(MON, end), MON, end,
                         ((SLEEP, "weekly.state.mood.mean", 0),), mode="single").hypotheses[0]
    assert hypothesis.verdict == "not_evaluable" and hypothesis.grain is None
    assert hypothesis.effect.coefficient is None and hypothesis.effect.meets_minimum is False
    assert hypothesis.weekday.status == "not_applicable"
    assert all(item.status in ("not_evaluable", "not_applicable")
               for item in hypothesis.checks)
    assert not any(item.blocking for item in hypothesis.checks)


def test_constant_series_is_not_evaluable_rather_than_preliminary():
    days = list(dates(MON, MON + timedelta(days=29)))
    values = [StateValues(sleep_minutes=600, computer_minutes=float(index)) for index in range(30)]
    data = build_dataset(DatasetInput((), dict(zip(days, values))), MON, days[-1], today=TODAY)
    hypothesis = analyze(data, MON, days[-1], (KEYS + (0,),), mode="single").hypotheses[0]
    assert hypothesis.relationship.status == "constant_series"
    assert hypothesis.verdict == "not_evaluable"


def test_empty_family_is_rejected():
    with pytest.raises(ValueError):
        analyze(dataset(MON, MON + timedelta(days=9)), MON, MON + timedelta(days=9), (),
                mode="single")


def test_reason_order_is_fixed_and_deterministic():
    end = MON + timedelta(days=89)
    hypothesis = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),),
                         mode="single").hypotheses[0]
    blocking = codes(hypothesis.blocking_reasons)
    warnings = codes(hypothesis.warnings)
    assert blocking == [code for code in BLOCKING_ORDER if code in set(blocking)]
    assert warnings == [code for code in WARNING_ORDER if code in set(warnings)]
    assert all(code in BLOCKING_REASONS for code in blocking)
    assert all(code in WARNINGS for code in warnings)


def test_repeated_evaluation_is_byte_identical():
    data = state_dataset(MON - timedelta(days=7), 97, slope=0.6)
    hypotheses = tuple(KEYS + (lag,) for lag in range(4))
    first = GuardrailAnalyticsRead(
        analyze(data, MON, MON + timedelta(days=89), hypotheses, mode="lag_scan")).model_dump_json()
    second = GuardrailAnalyticsRead(
        analyze(data, MON, MON + timedelta(days=89), hypotheses, mode="lag_scan")).model_dump_json()
    assert first == second


@pytest.mark.parametrize("keys", [KEYS, ("state.alcohol", SLEEP), ("state.mood", COMPUTER),
                                  ("weekly.state.sleep_minutes.mean",
                                   "weekly.state.computer_minutes.mean")])
def test_payload_is_finite_and_round_trips(keys):
    end = MON + timedelta(days=89)
    result = analyze(dataset(MON - timedelta(days=7), end), MON, end, (keys + (0,),), mode="single")
    payload = GuardrailAnalyticsRead(result).model_dump_json()
    assert "NaN" not in payload and "Infinity" not in payload
    json.dumps(json.loads(payload), allow_nan=False)
    parsed = GuardrailAnalyticsRead.model_validate_json(payload).root
    assert parsed.guardrail_policy_version == POLICY.version
    assert parsed.policy.minimum_n == POLICY.minimum_n
    assert parsed.family.mode == "single"


def test_guardrail_summary_is_compact_and_matches_the_hypothesis():
    end = MON + timedelta(days=89)
    result = analyze(state_dataset(MON, 90, slope=0.05), MON, end, (KEYS + (0,),), mode="single")
    summary = guardrail_summary(result)
    hypothesis = one(result)
    assert summary.status == hypothesis.verdict == "blocked"
    assert summary.policy_version == POLICY.version
    assert summary.blocking_reasons == tuple(codes(hypothesis.blocking_reasons))
    assert summary.confidence_capped is False
    assert summary.family_size == result.family.tested_size


def test_policy_is_centralized_and_self_consistent():
    assert POLICY.version == "1"
    assert POLICY.minimum_n < POLICY.warning_below_n
    assert POLICY.minimum_pair_coverage < POLICY.warning_below_pair_coverage
    assert POLICY.weekday_maximum_relative_attenuation == 0.5
    assert POLICY.fdr_threshold == 0.10
    assert set(BLOCKING_ORDER) == set(BLOCKING_REASONS)
    assert set(WARNING_ORDER) == set(WARNINGS)
    assert all(label and message for label, message in (*BLOCKING_REASONS.values(),
                                                        *WARNINGS.values()))
