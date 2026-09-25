"""Stage 7E policy boundaries, segmentation, stability, caveats and scenarios."""

from dataclasses import asdict, fields, replace
from datetime import date, timedelta
import json

import pytest

from app.domain.analytics.builder import build_dataset, dates
from app.domain.analytics.confidence import (
    analyze, classify_confidence, collect_caveats, evaluate_coverage, evaluate_methods,
    evaluate_sample, evaluate_stability, evaluable, not_evaluable_reason, relation_to_full,
    segment_names, split_period,
)
from app.domain.analytics.confidence_types import (
    POLICY, Caveat, ConfidenceSegment, CoverageEvidence, MethodEvidence, SampleEvidence,
    StabilityEvidence,
)
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lag_types import LagResult
from app.domain.analytics.relationship_types import Relationship
from app.domain.analytics.relationships import analyze as same_period, analyze_pair
from app.domain.analytics.types import DatasetInput, Grain, VariableType as T
from app.domain.daily_state import StateValues
from app.schemas.confidence import ConfidenceAnalyticsRead
from tests.test_relationships import MON, X, Y, points


TODAY = MON + timedelta(days=400)
SLEEP, COMPUTER = "state.sleep_minutes", "state.computer_minutes"
RISING = list(range(1, 11))
FLAT = [1, 2, 3, 4, 5, 5, 4, 3, 2, 1]
# Pearson positive, Spearman near zero: the pair is method sensitive.
SENSITIVE = [-3, 6, 7, 8, 7, 5, 4, 4, 6, 7]
# Pearson negative while Spearman stays positive: the methods disagree.
DROPPING = [1, 2, 3, 4, 5, 6, 7, 8, 9, -20]


def dataset(start, end, *, today=TODAY, values=None):
    days = list(dates(start, end))
    if values is None:
        values = [StateValues(sleep_minutes=i + 1, computer_minutes=2 * i + 3, mood=i % 5 + 1,
                              alcohol=bool(i % 2)) for i in range(len(days))]
    return build_dataset(DatasetInput((), dict(zip(days, values))), start, end, today=today)


def state_pairs(sleep, computer):
    return [StateValues(sleep_minutes=s, computer_minutes=c) for s, c in zip(sleep, computer)]


def lag_result(relationship, *, lag=0):
    return LagResult(**{field.name: getattr(relationship, field.name) for field in fields(Relationship)},
                     lag=lag, lag_unit="day", target_period=Period(MON, MON), x_period=None,
                     potential_aligned_count=relationship.n)


def synthetic(coefficient, *, name="middle", full="positive", n=10):
    """A real Stage 7C relationship with a chosen full-period coefficient and direction."""
    x = replace(X, type=T.NUMERIC)
    y = replace(Y, type=T.NUMERIC)
    values = RISING[:n]
    other = [2 * value for value in values] if coefficient > 0 else (
        FLAT[:n] if coefficient == 0 else [2 * value for value in values][::-1])
    relationship = analyze_pair(x, y, points(values), points(other), today=TODAY)
    return ConfidenceSegment(0, name, Period(MON, MON), lag_result(relationship),
                             relation_to_full(full, relationship.direction),
                             relationship.direction, relationship.strength)


def pair(a, b, tx=T.NUMERIC, ty=T.NUMERIC):
    return analyze_pair(replace(X, type=tx), replace(Y, type=ty), points(a), points(b), today=TODAY)


# --- segmentation -------------------------------------------------------------------

@pytest.mark.parametrize("length", [1, 2, 3, 4, 5, 7, 30, 31, 90, 91])
def test_daily_split_is_contiguous_balanced_and_complete(length):
    period = Period(MON, MON + timedelta(days=length - 1))
    segments = split_period(period, Grain.DAILY)
    assert len(segments) == min(POLICY.segment_count, length)
    assert segments[0].start == period.start and segments[-1].end == period.end
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end + timedelta(days=1) == later.start
    sizes = [(item.end - item.start).days + 1 for item in segments]
    assert sum(sizes) == length and max(sizes) - min(sizes) <= 1


def test_daily_split_is_deterministic_and_gives_extra_days_to_the_earliest_segment():
    period = Period(MON, MON + timedelta(days=9))
    assert split_period(period, Grain.DAILY) == split_period(period, Grain.DAILY)
    assert split_period(period, Grain.DAILY) == (
        Period(MON, MON + timedelta(days=3)),
        Period(MON + timedelta(days=4), MON + timedelta(days=6)),
        Period(MON + timedelta(days=7), MON + timedelta(days=9)),
    )


def test_weekly_split_uses_whole_canonical_weeks():
    period = Period(MON, MON + timedelta(days=62))  # nine Monday-start weeks
    segments = split_period(period, Grain.WEEKLY)
    assert len(segments) == 3
    for index, item in enumerate(segments):
        assert item.start == MON + timedelta(days=21 * index)
        assert item.end == MON + timedelta(days=21 * index + 20)
        assert item.start.weekday() == 0 and item.end.weekday() == 6


def test_weekly_split_clips_edge_weeks_to_the_requested_period_without_gaps():
    period = Period(MON + timedelta(days=1), MON + timedelta(days=33))  # Tuesday..Tuesday
    segments = split_period(period, Grain.WEEKLY)
    assert segments[0].start == period.start and segments[-1].end == period.end
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end + timedelta(days=1) == later.start
    for item in segments:
        assert period.start <= item.start <= item.end <= period.end


@pytest.mark.parametrize("start,end", [
    (date(2024, 2, 28), date(2024, 3, 5)),          # leap day
    (date(2024, 2, 1), date(2024, 3, 31)),
    (date(2026, 12, 25), date(2027, 1, 20)),        # December -> January
    (date(2020, 12, 21), date(2021, 1, 17)),        # ISO 2020-W53
    (date(2026, 9, 7), date(2026, 9, 7)),           # single day
    (date(2026, 9, 7), date(2026, 9, 8)),           # two days
])
@pytest.mark.parametrize("grain", list(Grain))
def test_split_covers_the_period_exactly_for_hard_calendars(start, end, grain):
    segments = split_period(Period(start, end), grain)
    assert 1 <= len(segments) <= POLICY.segment_count
    assert segments[0].start == start and segments[-1].end == end
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end + timedelta(days=1) == later.start
    assert all(start <= item.start <= item.end <= end for item in segments)


def test_segment_names_are_deterministic():
    assert segment_names(1) == ("only",)
    assert segment_names(2) == ("early", "recent")
    assert segment_names(3) == ("early", "middle", "recent")
    with pytest.raises(ValueError):
        segment_names(4)


# --- direction, stability, coverage and methods -------------------------------------

@pytest.mark.parametrize("full,part,expected", [
    ("positive", "positive", "same"), ("negative", "negative", "same"),
    ("near_zero", "near_zero", "same"),
    ("positive", "near_zero", "near_zero"), ("near_zero", "positive", "near_zero"),
    ("positive", "negative", "opposite"), ("negative", "positive", "opposite"),
    (None, "positive", "insufficient"), ("positive", None, "insufficient"),
])
def test_relation_to_full_distinguishes_confirmation_uncertainty_and_reversal(full, part, expected):
    assert relation_to_full(full, part) == expected


def test_stability_metrics_measure_direction_and_magnitude():
    full = pair(RISING, [2 * value for value in RISING])
    insufficient = synthetic(1.0, n=4)
    stability = evaluate_stability(full, (synthetic(1.0, name="early"), synthetic(0.0),
                                          synthetic(-1.0, name="recent"), insufficient), POLICY)
    assert (stability.segment_count, stability.analyzable_segment_count) == (4, 3)
    assert stability.insufficient_segment_count == 1
    assert (stability.same_direction_count, stability.near_zero_count) == (1, 1)
    assert stability.opposite_direction_count == 1
    assert stability.coefficients == (1.0, 0.0, -1.0)
    assert stability.median_coefficient == 0.0 and stability.median_absolute_coefficient == 1.0
    assert stability.coefficient_range == 2.0 and stability.maximum_deviation_from_full == 2.0
    assert stability.direction_consistent is False and stability.meaningful_reversal is True
    assert stability.magnitude_stable is False and stability.magnitude_well_supported is False


def test_magnitude_stability_accepts_small_variation_around_the_full_coefficient():
    full = pair(RISING, [2 * value for value in RISING])
    segments = tuple(synthetic(1.0, name=name) for name in ("early", "middle", "recent"))
    stability = evaluate_stability(full, segments, POLICY)
    assert stability.maximum_deviation_from_full == 0
    assert stability.magnitude_stable is True and stability.magnitude_well_supported is True
    assert stability.direction_consistent is True and stability.meaningful_reversal is False


def test_coverage_evidence_uses_eligible_pairs_not_calendar_days():
    full = pair(RISING + [None] * 30, [2 * value for value in RISING] + [None] * 30)
    evidence = evaluate_coverage(full, (), POLICY)
    assert full.coverage.pair_coverage == 10 / 40
    assert evidence.pair_coverage == 10 / 40 and evidence.eligible_count == 40
    assert evidence.stable_coverage_met is False and evidence.well_supported_coverage_met is False
    assert evidence.low_coverage is True


def test_coverage_evidence_flags_uneven_segment_quality():
    strong = synthetic(1.0, name="early")
    thin = ConfidenceSegment(
        1, "recent", Period(MON, MON), lag_result(pair(RISING + [None] * 10,
                                                       [2 * value for value in RISING])),
        "same", "positive", "strong")
    full = pair(RISING + [None] * 10, [2 * value for value in RISING])
    evidence = evaluate_coverage(full, (strong, thin), POLICY)
    assert evidence.segment_pair_coverage == (1.0, 0.5)
    assert evidence.coverage_imbalance == 0.5 and evidence.segment_instability is True


@pytest.mark.parametrize("a,b,expected", [
    (RISING, [2 * value for value in RISING], "agree"),
    (RISING, SENSITIVE, "partial"),
    (RISING, DROPPING, "disagree"),
])
def test_method_agreement_between_pearson_and_spearman(a, b, expected):
    assert evaluate_methods(pair(a, b)).agreement == expected


def test_method_agreement_handles_single_and_unavailable_metrics():
    assert evaluate_methods(pair(RISING, [2 * value for value in RISING])).agreement == "agree"
    assert evaluate_methods(pair([True, False] * 5, [True, False] * 5, T.BOOLEAN,
                                 T.BOOLEAN)).agreement == "single_method"
    categorical = evaluate_methods(pair(["a"] * 10, ["b"] * 10, T.CATEGORICAL))
    assert categorical.agreement == "unavailable" and categorical.methods == ()


def test_sample_evidence_exposes_every_sample_threshold():
    evidence = evaluate_sample(pair(RISING, [2 * value for value in RISING]), POLICY)
    assert (evidence.n, evidence.eligible_count, evidence.minimum_n_met) == (10, 10, True)
    assert evidence.stable_n_met is False and evidence.well_supported_n_met is False


# --- policy classification ----------------------------------------------------------

def evidence(*, n=50, coverage=1.0, segment_count=3, analyzable=3, same=3, near=0, opposite=0,
             deviation=0.0, consistent=True, reversal=False, agreement="agree"):
    sample = SampleEvidence(n, n, n, 0, 0, 0, coverage, n >= 5, n >= POLICY.stable_minimum_n,
                            n >= POLICY.well_supported_minimum_n)
    coverage_evidence = CoverageEvidence(
        coverage, n, coverage >= POLICY.stable_minimum_pair_coverage,
        coverage >= POLICY.well_supported_minimum_pair_coverage, (), coverage, coverage, 0.0,
        coverage < POLICY.stable_minimum_pair_coverage, False)
    stability = StabilityEvidence(
        segment_count, analyzable, segment_count - analyzable, same, near, opposite, (0.0,),
        0.0, 0.0, 0.0, deviation, consistent, reversal,
        deviation <= POLICY.stable_maximum_deviation_from_full,
        deviation <= POLICY.well_supported_maximum_deviation_from_full)
    methods = MethodEvidence("pearson", ("pearson",), (0.0,), ("positive",), agreement)
    return classify_confidence(sample, coverage_evidence, stability, methods, POLICY)


@pytest.mark.parametrize("overrides,expected", [
    ({}, "well_supported"),
    ({"n": 40}, "well_supported"),
    ({"n": 39}, "stable"),
    ({"n": 20}, "stable"),
    ({"n": 19}, "preliminary"),
    ({"coverage": 0.75}, "well_supported"),
    ({"coverage": 0.7499}, "stable"),
    ({"coverage": 0.60}, "stable"),
    ({"coverage": 0.5999}, "preliminary"),
    ({"segment_count": 2, "analyzable": 2, "same": 2}, "stable"),
    ({"analyzable": 2, "same": 2}, "stable"),
    ({"analyzable": 1, "same": 1}, "preliminary"),
    ({"analyzable": 3, "same": 2, "near": 1}, "well_supported"),
    ({"analyzable": 3, "same": 1, "near": 2}, "stable"),
    ({"consistent": False}, "preliminary"),
    ({"reversal": True}, "preliminary"),
    ({"deviation": POLICY.stable_maximum_deviation_from_full}, "stable"),
    ({"deviation": 0.3501}, "preliminary"),
    ({"deviation": POLICY.well_supported_maximum_deviation_from_full}, "well_supported"),
    ({"deviation": 0.2001}, "stable"),
    ({"agreement": "partial"}, "well_supported"),
    ({"agreement": "disagree"}, "preliminary"),
    ({"opposite": 1, "consistent": True}, "stable"),
    ({"n": 19, "coverage": 0.1, "analyzable": 0, "consistent": False}, "preliminary"),
])
def test_confidence_policy_boundaries(overrides, expected):
    assert evidence(**overrides) == expected


def test_policy_thresholds_are_centralized():
    assert POLICY.version == "1"
    assert POLICY.stable_minimum_n == 20 and POLICY.well_supported_minimum_n == 40
    assert (POLICY.stable_minimum_pair_coverage, POLICY.well_supported_minimum_pair_coverage) == (0.60, 0.75)
    assert POLICY.preliminary_minimum_n == 5 and POLICY.segment_count == 3


# --- caveats and not-evaluable ------------------------------------------------------

def test_caveats_are_ordered_and_only_include_relevant_codes():
    full = pair(RISING, [2 * value for value in RISING])
    segments = (synthetic(1.0, name="early"), synthetic(0.0), synthetic(-1.0, name="recent"))
    sample, coverage = evaluate_sample(full, POLICY), evaluate_coverage(full, segments, POLICY)
    stability = evaluate_stability(full, segments, POLICY)
    methods = evaluate_methods(full)
    caveats = collect_caveats(full, sample, coverage, stability, methods, POLICY, evaluated=True)
    assert [caveat.code for caveat in caveats] == [
        "small_sample", "segment_inconsistency", "direction_reversal", "magnitude_instability",
        "autocorrelation_possible", "association_not_causation"]
    assert all(isinstance(caveat, Caveat) and caveat.label and caveat.message for caveat in caveats)
    assert collect_caveats(full, sample, coverage, stability, methods, POLICY, evaluated=True) == caveats


def test_universal_caveats_apply_without_an_evaluated_coefficient():
    categorical = pair(["a"] * 6, ["b"] * 6, T.CATEGORICAL)
    caveats = collect_caveats(categorical, evaluate_sample(categorical, POLICY),
                              evaluate_coverage(categorical, (), POLICY),
                              evaluate_stability(categorical, (), POLICY),
                              evaluate_methods(categorical), POLICY, evaluated=False)
    assert [caveat.code for caveat in caveats] == [
        "unsupported_variable_types", "autocorrelation_possible", "association_not_causation"]


def test_ordinal_distance_caveat_applies_to_ordinal_variables():
    weekly = pair(RISING, [2 * value for value in RISING], T.ORDINAL)
    stability = evaluate_stability(weekly, (), POLICY)
    codes = [caveat.code for caveat in collect_caveats(
        weekly, evaluate_sample(weekly, POLICY), evaluate_coverage(weekly, (), POLICY), stability,
        evaluate_methods(weekly), POLICY, evaluated=True)]
    assert "ordinal_distance_limitation" in codes and "constant_series" not in codes


@pytest.mark.parametrize("values,tx,expected", [
    ([1, 2, 3, 4], T.NUMERIC, "insufficient_data"),
    ([1] * 6, T.NUMERIC, "constant_series"),
    (["a"] * 6, T.CATEGORICAL, "unsupported_types"),
])
def test_not_evaluable_reason_maps_relationship_status(values, tx, expected):
    variable = replace(X, type=tx)
    relationship = analyze_pair(variable, Y, points(values), points([1, 2, 3, 4, 5, 6][:len(values)]),
                               today=TODAY)
    assert evaluable(relationship) is False
    assert not_evaluable_reason(relationship) == expected


def test_grain_mismatch_is_not_evaluable():
    data = dataset(MON, MON + timedelta(days=20))
    result = analyze(data, data.start, data.end, (SLEEP, "weekly.state.sleep_minutes.mean"))
    assert result.status == "not_evaluable" and result.confidence is None and result.grain is None
    assert result.reason == "grain_mismatch" and result.segments == ()
    assert result.evidence.stability.segment_count == 0
    assert [caveat.code for caveat in result.caveats] == ["association_not_causation"]


# --- scenarios ----------------------------------------------------------------------

def amplitude_history(days=90):
    """Early segment dominates the coefficient; the middle is flat; the recent reverses."""
    sleep, computer = [], []
    for index in range(days):
        stage, offset = divmod(index, 30)
        value = offset * 48 if stage == 0 else 700 + offset
        sleep.append(value)
        computer.append(value if stage == 0 else (
            700 + (15 - offset // 2 if offset % 2 else 15 + offset // 2)
            if stage == 1 else 700 + (29 - offset)))
    return sleep, computer


def repeating_history(days=91, *, noise):
    sleep, computer = [], []
    for index in range(days):
        base = 700 + (index % 30) * 4
        sleep.append(base)
        computer.append(base + noise * ((index * 7) % 5 - 2))
    return sleep, computer


def test_strong_coefficient_on_six_pairs_is_only_preliminary():
    values = state_pairs(RISING[:6], [2 * value for value in RISING[:6]])
    data = dataset(MON, MON + timedelta(days=5), values=values)
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.relationship.coefficient == pytest.approx(1) and result.relationship.n == 6
    assert result.relationship.strength is None and result.relationship.direction == "positive"
    assert result.confidence == "preliminary" and result.status == "evaluated"
    assert [caveat.code for caveat in result.caveats] == [
        "small_sample", "segment_inconsistency", "autocorrelation_possible",
        "association_not_causation"]


@pytest.mark.parametrize("noise,strength", [(30, "strong"), (60, "moderate"), (200, "weak")])
def test_strength_and_confidence_are_independent(noise, strength):
    sleep, computer = repeating_history(days=90, noise=noise)
    data = dataset(MON, MON + timedelta(days=89), values=state_pairs(sleep, computer))
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.relationship.strength == strength
    assert result.confidence == "well_supported"
    assert result.relationship.n == 90 and result.evidence.coverage.pair_coverage == 1
    assert result.evidence.stability.maximum_deviation_from_full == pytest.approx(0, abs=1e-9)
    assert result.evidence.methods.agreement == "agree"
    assert [caveat.code for caveat in result.caveats] == ["autocorrelation_possible",
                                                          "association_not_causation"]


def test_full_period_coefficient_can_hide_an_unstable_history():
    sleep, computer = amplitude_history()
    data = dataset(MON, MON + timedelta(days=89), values=state_pairs(sleep, computer))
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.relationship.coefficient > 0.7
    assert [item.relationship.coefficient for item in result.segments] == pytest.approx(
        [1, 0, -1], abs=0.06)
    assert [item.relation_to_full for item in result.segments] == ["same", "near_zero", "opposite"]
    assert result.confidence == "preliminary"
    assert [caveat.code for caveat in result.caveats] == [
        "segment_inconsistency", "direction_reversal", "magnitude_instability",
        "autocorrelation_possible", "association_not_causation"]


def test_missing_days_are_not_imputed_and_explicit_zero_stays_observed():
    values = [StateValues(sleep_minutes=0, computer_minutes=0),
              StateValues(sleep_minutes=60, computer_minutes=None),
              None,
              StateValues(sleep_minutes=120, computer_minutes=120),
              StateValues(sleep_minutes=180, computer_minutes=180),
              StateValues(sleep_minutes=240, computer_minutes=240),
              StateValues(sleep_minutes=300, computer_minutes=300)]
    data = dataset(MON, MON + timedelta(days=6), values=values)
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.status == "evaluated" and result.relationship.coefficient == pytest.approx(1)
    assert result.relationship.n == 5
    assert result.relationship.coverage.requested_count == 7
    assert result.relationship.coverage.missing_count == 2
    assert result.evidence.sample.pair_coverage == 5 / 7
    assert result.confidence == "preliminary"


def test_large_sample_with_weak_coverage_stays_preliminary():
    sleep, computer = repeating_history(days=90, noise=30)
    values = [None if index % 2 else StateValues(sleep_minutes=sleep[index],
                                                 computer_minutes=computer[index])
              for index in range(90)]
    data = dataset(MON, MON + timedelta(days=89), values=[v for v in values if v is not None])
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.relationship.n == 45 and result.evidence.sample.well_supported_n_met is True
    assert result.evidence.coverage.pair_coverage == 0.5
    assert result.confidence == "preliminary"
    codes = [caveat.code for caveat in result.caveats]
    assert "low_coverage" in codes and "systematic_missingness_possible" in codes


def test_history_with_two_empty_segments_cannot_be_well_supported():
    sleep, computer = repeating_history(days=90, noise=30)
    values = [StateValues(sleep_minutes=sleep[index], computer_minutes=computer[index])
              if 30 <= index < 60 else None for index in range(90)]
    data = dataset(MON, MON + timedelta(days=89), values=[v for v in values if v is not None])
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.evidence.stability.analyzable_segment_count == 1
    assert result.confidence == "preliminary"
    assert "segment_inconsistency" in [caveat.code for caveat in result.caveats]


def test_uneven_segment_coverage_is_reported_without_hiding_it():
    sleep, computer = repeating_history(days=90, noise=30)
    values = [StateValues(sleep_minutes=sleep[index], computer_minutes=computer[index])
              if index < 75 else None for index in range(90)]
    data = dataset(MON, MON + timedelta(days=89), values=[v for v in values if v is not None])
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.evidence.coverage.segment_pair_coverage == (1.0, 1.0, 0.5)
    assert result.evidence.coverage.segment_instability is True
    codes = [caveat.code for caveat in result.caveats]
    assert "systematic_missingness_possible" in codes and "low_coverage" not in codes


def test_method_sensitivity_is_reported_when_pearson_and_spearman_split():
    values = state_pairs([value + 10 for value in RISING], [value + 10 for value in SENSITIVE])
    data = dataset(MON, MON + timedelta(days=9), values=values)
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.evidence.methods.agreement == "partial"
    assert "method_disagreement" in [caveat.code for caveat in result.caveats]


def test_method_disagreement_blocks_a_stable_classification():
    values = state_pairs([value + 20 for value in RISING], [value + 20 for value in DROPPING]) * 10
    data = dataset(MON, MON + timedelta(days=99), values=values)
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.evidence.methods.agreement == "disagree"
    assert result.confidence == "preliminary"
    assert "method_disagreement" in [caveat.code for caveat in result.caveats]


# --- lags ---------------------------------------------------------------------------

def test_positive_lag_confidence_uses_the_stage_7d_source_range():
    sleep, computer = repeating_history(noise=30)
    values = state_pairs(sleep, computer)
    data = dataset(MON - timedelta(days=1), MON + timedelta(days=89), values=values)
    result = analyze(data, MON, MON + timedelta(days=89), (COMPUTER, SLEEP), 1)
    assert result.lag == 1 and result.lag_unit == "day" and result.grain == Grain.DAILY
    assert result.source_range.start == MON - timedelta(days=1)
    assert result.confidence == "well_supported"
    assert [item.relationship.n for item in result.segments] == [30, 30, 30]
    assert all(item.period.start >= MON for item in result.segments)
    assert [caveat.code for caveat in result.caveats] == ["autocorrelation_possible",
                                                          "association_not_causation"]


def test_positive_lag_keeps_x_before_each_segment_start():
    sleep, computer = repeating_history(noise=30)
    data = dataset(MON - timedelta(days=1), MON + timedelta(days=89), values=state_pairs(sleep, computer))
    result = analyze(data, MON, MON + timedelta(days=89), (COMPUTER, SLEEP), 1)
    earliest = result.segments[0]
    assert earliest.period.start == MON
    assert earliest.relationship.x_period.start == MON - timedelta(days=1)
    assert earliest.relationship.n == earliest.relationship.coverage.requested_count == 30
    assert earliest.relationship.coverage.losses["missing"] == 0
    assert all(item.relationship.n == 30 for item in result.segments)


def test_lagged_recent_reversal_lowers_confidence():
    sleep, computer = amplitude_history()
    values = state_pairs([sleep[0], *sleep], [*computer, computer[-1]])
    data = dataset(MON - timedelta(days=1), MON + timedelta(days=89), values=values)
    result = analyze(data, MON, MON + timedelta(days=89), (COMPUTER, SLEEP), 1)
    assert result.relationship.coefficient > 0.7
    assert result.segments[2].relationship.coefficient == pytest.approx(-1, abs=0.01)
    assert result.confidence == "preliminary"
    assert "direction_reversal" in [caveat.code for caveat in result.caveats]


def test_lag_zero_equals_the_stage_7c_relationship():
    sleep, computer = repeating_history(days=90, noise=120)
    data = dataset(MON, MON + timedelta(days=89), values=state_pairs(sleep, computer))
    expected = same_period(data, data.start, data.end, (SLEEP, COMPUTER), pair=True).relationships[0]
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.lag == 0 and result.lag_unit == "day"
    assert {field.name: getattr(result.relationship, field.name) for field in fields(Relationship)} == {
        field.name: getattr(expected, field.name) for field in fields(Relationship)}


def test_weekly_confidence_segments_use_whole_weeks_and_reuse_7c_rules():
    start, end = MON, MON + timedelta(days=314)  # forty-five Monday-start weeks
    values = [StateValues(sleep_minutes=600 + (index // 7 % 5) * 50,
                          computer_minutes=900 + (index // 7 % 5) * 30) for index in range(315)]
    data = dataset(start, end, values=values)
    result = analyze(data, start, end, ("weekly.state.sleep_minutes.mean",
                                       "weekly.state.computer_minutes.mean"))
    assert result.grain == Grain.WEEKLY and result.lag_unit == "week"
    assert [item.relationship.n for item in result.segments] == [15, 15, 15]
    assert all(item.period.start.weekday() == 0 and item.period.end.weekday() == 6
               for item in result.segments)
    assert result.relationship.coverage.losses["incomplete_period"] == 0
    assert result.confidence == "well_supported"


def test_weekly_partial_edge_weeks_are_excluded_and_flagged():
    values = [StateValues(sleep_minutes=600 + index % 5 * 20,
                          computer_minutes=900 + index % 5 * 30) for index in range(70)]
    data = dataset(MON, MON + timedelta(days=69), values=values)
    result = analyze(data, MON + timedelta(days=1), MON + timedelta(days=60),
                     ("weekly.state.sleep_minutes.mean", "weekly.state.computer_minutes.mean"))
    assert result.relationship.coverage.losses["incomplete_period"] == 2
    assert result.relationship.n == 7
    assert "partial_period" in [caveat.code for caveat in result.caveats]


def test_missing_variable_uncovered_range_and_invalid_lag_are_validation_errors():
    data = dataset(MON, MON + timedelta(days=10))
    with pytest.raises(ValueError, match="отсутствуют"):
        analyze(data, MON, MON + timedelta(days=9), (SLEEP, "habit.999.daily.completion"))
    with pytest.raises(ValueError, match="расширенный"):
        analyze(data, MON, MON + timedelta(days=10), (SLEEP, COMPUTER), 7)
    with pytest.raises(ValueError):
        analyze(data, MON, MON + timedelta(days=9), (SLEEP, COMPUTER), 8)


def test_confidence_analytics_round_trips_without_nan():
    sleep, computer = repeating_history(days=90, noise=200)
    data = dataset(MON, MON + timedelta(days=89), values=state_pairs(sleep, computer))
    result = analyze(data, data.start, data.end, (SLEEP, COMPUTER))
    assert result.confidence_policy_version == result.policy.version == POLICY.version
    encoded = ConfidenceAnalyticsRead(result).model_dump_json()
    assert ConfidenceAnalyticsRead.model_validate_json(encoded).root == result
    json.dumps(json.loads(encoded), allow_nan=False)
    json.dumps(asdict(result.evidence.stability), allow_nan=False)
    json.dumps(asdict(result.evidence.sample), allow_nan=False)
