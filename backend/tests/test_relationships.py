"""Statistical reference cases, exact alignment, coverage and policy boundaries."""

from dataclasses import asdict, replace
from datetime import date, timedelta
import json
from math import sqrt

import pytest

from app.domain.analytics.builder import build_dataset
from app.domain.analytics.correlation import average_ranks, pearson, phi, point_biserial, spearman
from app.domain.analytics.descriptive_types import SeriesPoint
from app.domain.analytics.relationship_types import POLICY
from app.domain.analytics.relationships import analyze, analyze_pair, classify, extract_pairs, validate_request
from app.domain.analytics.types import Availability as A, DatasetInput, Grain, Variable, VariableType as T
from app.domain.daily_state import StateValues


MON = date(2026, 9, 7)
TODAY = MON + timedelta(days=100)
X = Variable("x", "X", T.NUMERIC, Grain.DAILY, "test", "Missing stays missing")
Y = replace(X, key="y", label="Y")


def points(values, *, start=MON, step=1):
    return tuple(SeriesPoint(start + timedelta(days=step * i), v,
                             A.PRESENT if v is not None else A.SOURCE_MISSING, False)
                 for i, v in enumerate(values))


def pair(a, b, tx=T.NUMERIC, ty=T.NUMERIC):
    return analyze_pair(replace(X, type=tx), replace(Y, type=ty), points(a), points(b), today=TODAY)


@pytest.mark.parametrize("a,b,expected", [
    ([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], 1),
    ([1, 2, 3, 4, 5], [10, 8, 6, 4, 2], -1),
    ([-2, -1, 0, 1, 2], [2, -1, -2, -1, 2], 0),
    ([1, 2, 3, 4, 5], [1, 2, 4, 8, 16], 36 / sqrt(1488)),
])
def test_pearson_reference(a, b, expected):
    result = pearson(a, b)
    assert result.status == "ok" and result.coefficient == pytest.approx(expected)
    assert pearson(b, a).coefficient == pytest.approx(expected)


@pytest.mark.parametrize("function", [pearson, spearman])
@pytest.mark.parametrize("a,b,status", [
    ([3] * 5, list(range(5)), "constant_series"),
    (list(range(5)), [3] * 5, "constant_series"),
    ([], [], "insufficient_data"), ([1], [2], "insufficient_data"),
    ([1, 2, 3, 4], [2, 3, 4, 5], "insufficient_data"),
    ([1] * 5, [1] * 4, "invalid_values"),
    ([1, 2, 3, 4, float("nan")], list(range(5)), "invalid_values"),
    (list(range(5)), [1, 2, 3, 4, float("inf")], "invalid_values"),
    ([None] * 5, list(range(5)), "invalid_values"),
    ([False] * 5, list(range(5)), "invalid_values"),
    ([10**1000] * 5, list(range(5)), "invalid_values"),
])
def test_math_undefined_and_invalid(function, a, b, status):
    result = function(a, b)
    assert result.status == status and result.coefficient is None
    json.dumps(asdict(result), allow_nan=False)


@pytest.mark.parametrize("a,b,expected", [
    ([1, 2, 3, 4, 5], [1, 2, 4, 8, 16], 1),
    ([1, 2, 3, 4, 5], [16, 8, 4, 2, 1], -1),
    ([1, 2, 2, 4, 5], [5, 1, 1, 3, 2], -3 / 19),
    ([1, 1, 2, 2, 3], [0, 0, 1, 1, 20], 1),
])
def test_spearman_reference_and_ties(a, b, expected):
    assert spearman(a, b).coefficient == pytest.approx(expected)


def test_average_ranks():
    assert average_ranks([40, 10, 20, 20, 10]) == [5, 1.5, 3.5, 3.5, 1.5]


@pytest.mark.parametrize("values", [
    [-1e308, -5e307, 0, 5e307, 1e308],
    [5e-324, 1e-323, 1.5e-323, 2e-323, 2.5e-323],
    [1e15 + i / 8 for i in range(5)],
])
def test_numerical_stability(values):
    assert pearson(values, values).coefficient == pytest.approx(1)
    assert pearson(values, list(reversed(values))).coefficient == pytest.approx(-1)
    json.dumps(asdict(pair(values, values)), allow_nan=False)


def test_point_biserial_reference_and_observed_counts():
    a, b = [False, False, False, True, True, True], [1, 2, 3, 4, 5, 6]
    assert point_biserial(a, b).coefficient == pytest.approx(9 / sqrt(105))
    result = pair(a + [None, False], b + [1000, None], T.BOOLEAN)
    assert result.n == 6 and result.coverage.missing_count == 2
    assert result.boolean_x.true_count == result.boolean_x.false_count == 3
    assert result.coefficient == pytest.approx(9 / sqrt(105))
    assert pair(b, a, ty=T.BOOLEAN).coefficient == pytest.approx(result.coefficient)
    assert point_biserial([True] * 6, b).status == "constant_series"
    assert point_biserial([False] * 5 + [None], b).status == "invalid_values"
    assert pair(a, b, T.BOOLEAN, T.ORDINAL).limitations == ("ordinal_spacing_assumed",)


@pytest.mark.parametrize("a,b,expected", [
    ([True, False] * 4, [True, False] * 4, 1),
    ([True, False] * 4, [False, True] * 4, -1),
    ([True, True, False, False] * 2, [True, False, True, False] * 2, 0),
    ([True] * 4 + [False] * 6, [True] * 3 + [False] + [True] * 2 + [False] * 4, 1 / sqrt(6)),
])
def test_phi_reference_and_contingency(a, b, expected):
    assert phi(a, b).coefficient == pytest.approx(expected)
    result = pair(a + [None, True], b + [False, None], T.BOOLEAN, T.BOOLEAN)
    assert result.n == len(a) and result.coverage.missing_count == 2
    assert result.coefficient == pytest.approx(expected)
    table = result.contingency
    assert sum(asdict(table).values()) == len(a)
    assert table.true_true + table.true_false == result.boolean_x.true_count
    assert table.true_true + table.false_true == result.boolean_y.true_count
    assert phi([True] * len(a), b).status == "constant_series"
    assert phi(a, [None] * len(a)).status == "invalid_values"


@pytest.mark.parametrize("tx", list(T))
@pytest.mark.parametrize("ty", list(T))
def test_method_selection_all_type_combinations(tx, ty):
    values = {T.NUMERIC: [1, 2, 3, 4, 5], T.ORDINAL: [1, 2, 3, 4, 5],
              T.BOOLEAN: [True, False, True, False, True], T.CATEGORICAL: ["a", "b", "c", "b", "a"]}
    result = pair(values[tx], values[ty], tx, ty)
    expected = (None if T.CATEGORICAL in (tx, ty) else "phi" if tx == ty == T.BOOLEAN else
                "point_biserial" if T.BOOLEAN in (tx, ty) else "spearman" if T.ORDINAL in (tx, ty) else "pearson")
    assert result.method == expected
    assert result.status == ("unsupported" if expected is None else "ok")
    assert result.n == 5 and result.strength is None
    assert len(result.metrics) == (0 if expected is None else 2 if tx == ty == T.NUMERIC else 1)
    if expected is None:
        assert result.coefficient is result.direction is None


def test_exact_requested_missingness_and_no_imputation():
    result = pair([1, 2, None, 4], [2, None, 6, 8])
    assert result.n == 2 and result.status == "insufficient_data"
    assert result.coverage.requested_count == result.coverage.eligible_count == 4
    assert result.coverage.missing_count == 2 and result.coverage.pair_coverage == 0.5
    extracted = extract_pairs(X, Y, points([1, 2, None, 4]), points([2, None, 6, 8]), today=TODAY)
    assert [(a.value, b.value) for a, b in zip(extracted.x, extracted.y)] == [(1, 2), (4, 8)]
    enough = pair([0, 1, None, 2, 3, 4, None], [0, 2, 99, 4, 6, 8, 100])
    assert enough.n == 5 and all(m.coefficient == pytest.approx(1) for m in enough.metrics)
    for a, b, n in [([None] * 5, [1] * 5, 0), ([None, 0], [1, 0], 1)]:
        result = pair(a, b)
        assert result.n == n and result.coefficient is None and result.status == "insufficient_data"


def test_all_missingness_reasons_and_denominators():
    reasons = [A.SOURCE_MISSING, A.FIELD_MISSING, A.NO_OBSERVATIONS,
               A.NOT_APPLICABLE, A.NO_OBLIGATIONS, A.FUTURE]
    xs = tuple(SeriesPoint(MON + timedelta(days=i), None, reason, False) for i, reason in enumerate(reasons))
    result = extract_pairs(X, Y, xs, points([1] * 6), today=TODAY).coverage
    assert result.requested_count == 6 and result.eligible_count == 3
    assert result.missing_count == 3 and result.excluded_count == 3 and result.pair_coverage == 0
    assert all(result.x.counts_by_availability[reason] == 1 for reason in reasons)
    assert sum(result.losses.values()) == result.unavailable_count == 6
    empty = extract_pairs(X, Y, xs[3:], points([1] * 6)[3:], today=TODAY).coverage
    assert empty.eligible_count == 0 and empty.pair_coverage is None


@pytest.mark.parametrize("grain,step", [(Grain.DAILY, 1), (Grain.WEEKLY, 7)])
def test_alignment_uses_keys_not_array_position(grain, step):
    xs, ys = points([1, 2, 3], step=step), points([20, 30, 40], start=MON + timedelta(days=step), step=step)
    extracted = extract_pairs(replace(X, grain=grain), replace(Y, grain=grain),
                              tuple(reversed(xs)), ys, today=TODAY)
    assert [(a.value, b.value) for a, b in zip(extracted.x, extracted.y)] == [(2, 20), (3, 30)]
    assert extracted.coverage.requested_count == 4 and extracted.coverage.missing_count == 2
    with pytest.raises(ValueError):
        extract_pairs(X, Y, xs + xs, ys, today=TODAY)


def test_grain_mismatch_never_aligns_or_aggregates():
    result = analyze_pair(X, replace(Y, grain=Grain.WEEKLY), points([1] * 10), points([2] * 10), today=TODAY)
    assert result.status == "unsupported" and result.reason == "grain_mismatch"
    assert result.grain is result.coverage is result.coefficient is None and result.n == 0


def test_invalid_values_deleted_before_encoding_or_ranking():
    result = pair([0, 1, 2, 3, 4, float("nan"), float("inf"), True], list(range(8)))
    assert result.n == 5 and result.coverage.losses["invalid_value"] == 3
    assert result.coefficient == pytest.approx(1)
    json.dumps(asdict(result), allow_nan=False)
    boolean = pair([False, True, None, 0, "false"], list(range(5)), T.BOOLEAN)
    assert boolean.n == 2 and boolean.boolean_x.false_count == 1


@pytest.mark.parametrize("r,strength,direction", [
    (0, "negligible", "near_zero"), (0.099, "negligible", "near_zero"),
    (0.1, "weak", "positive"), (-0.3, "moderate", "negative"), (0.5, "strong", "positive"),
])
def test_strength_and_direction_boundaries(r, strength, direction):
    assert classify(r, POLICY.strength_minimum) == (direction, strength)
    assert classify(r, POLICY.strength_minimum - 1) == (direction, None)
    assert classify(None, 100) == (None, None)


def canonical(start, end, today, *, sparse=False):
    states = {start + timedelta(days=i): StateValues(mood=i % 5 + 1, sleep_minutes=100 + i)
              for i in range((end - start).days + 1) if not sparse or i % 7 == 0}
    return build_dataset(DatasetInput((), states), start, end, today=today)


@pytest.mark.parametrize("start,end", [(date(2023, 12, 25), date(2024, 1, 7)),
                                       (date(2024, 2, 26), date(2024, 3, 3))])
def test_calendar_boundaries_daily_and_weekly(start, end):
    data = canonical(start, end, end + timedelta(days=1))
    result = analyze(data, start, end, ("state.mood", "state.sleep_minutes"), pair=True).relationships[0]
    assert result.n == (end - start).days + 1 and result.coverage.pair_coverage == 1
    result = analyze(data, start, end, ("weekly.state.mood.mean", "weekly.state.sleep_minutes.mean"), pair=True).relationships[0]
    assert result.n == ((end - start).days + 1) // 7
    assert result.coverage.paired_source_x.observed_count == (end - start).days + 1


@pytest.mark.parametrize("today_offset,expected", [(33, 4), (34, 4), (35, 5), (41, 5), (42, 6)])
def test_current_partial_week_including_sunday(today_offset, expected):
    end, today = MON + timedelta(days=41), MON + timedelta(days=today_offset)
    data = canonical(MON, end, today)
    result = analyze(data, MON, end, ("weekly.state.mood.mean", "weekly.state.sleep_minutes.mean")).relationships[0]
    assert result.n == expected
    assert result.coverage.excluded_count == 6 - expected
    assert result.coverage.paired_source_x.observed_count == expected * 7


def test_partial_requested_weeks_and_sparse_source_coverage():
    end = MON + timedelta(days=41)
    data = canonical(MON, end, TODAY)
    keys = ("weekly.state.mood.mean", "weekly.state.sleep_minutes.mean")
    result = analyze(data, MON + timedelta(days=1), end - timedelta(days=1), keys).relationships[0]
    assert result.n == 4 and result.coverage.losses["incomplete_period"] == 2
    sparse = analyze(canonical(MON, end, TODAY, sparse=True), MON, end, keys).relationships[0]
    assert sparse.n == 0 and sparse.coverage.losses["low_source_coverage"] == 6
    assert sparse.coverage.source_x.ratio == 1 / 7 and sparse.coverage.pair_coverage == 0


def test_daily_today_only_present_and_future_calendar_excluded():
    data = canonical(MON, MON + timedelta(days=6), MON + timedelta(days=4))
    result = analyze(data, data.start, data.end, ("state.mood", "state.sleep_minutes")).relationships[0]
    assert result.n == 5 and result.coverage.includes_today
    assert result.coverage.losses["future"] == 2 and result.coverage.eligible_count == 5
    result = analyze(data, data.start, data.end, ("daily.weekend", "daily.year")).relationships[0]
    assert result.n == 5 and result.coverage.losses["future"] == 2


def test_matrix_unique_deterministic_and_pair_orientation():
    data = canonical(MON, MON + timedelta(days=6), TODAY)
    keys = ("state.sleep_minutes", "state.energy", "state.mood", "daily.score")
    result = analyze(data, data.start, data.end, keys)
    assert result == analyze(data, data.start, data.end, tuple(reversed(keys)))
    identities = [(r.x.key, r.y.key) for r in result.relationships]
    assert len(identities) == len(set(identities)) == 6
    assert identities == sorted(identities) and all(a < b for a, b in identities)
    explicit = analyze(data, data.start, data.end, keys[:2], pair=True)
    assert explicit.relationships[0].x.key == keys[0]


@pytest.mark.parametrize("keys", [(), ("x",), ("x", "x"), ("", "y"), (" " , "y"),
                                  ("x" * 161, "y"), tuple(str(i) for i in range(25))])
def test_request_variable_limits(keys):
    with pytest.raises(ValueError):
        validate_request(MON, MON, keys)


def test_request_date_limits():
    validate_request(MON, MON + timedelta(days=POLICY.max_period_days - 1), ("x", "y"))
    validate_request(date.min, date.min, ("x", "y"))
    validate_request(date.max, date.max, ("x", "y"))
    with pytest.raises(ValueError):
        validate_request(MON, MON + timedelta(days=POLICY.max_period_days), ("x", "y"))
    with pytest.raises(ValueError):
        validate_request(MON, MON - timedelta(days=1), ("x", "y"))


@pytest.mark.parametrize("day", [date.min, date.max])
def test_canonical_date_extremes(day):
    data = canonical(day, day, day)
    result = analyze(data, day, day, ("state.mood", "state.sleep_minutes")).relationships[0]
    assert result.n == 1 and result.status == "insufficient_data"
    assert result.coverage.includes_today


def test_today_missing_boolean_stays_missing():
    xs, ys = points([True, False, None]), points([1, 2, 3])
    result = analyze_pair(replace(X, type=T.BOOLEAN), Y, xs, ys, today=MON + timedelta(days=2))
    assert result.n == 2 and not result.coverage.includes_today
    assert result.boolean_x.false_count == result.boolean_x.true_count == 1
    assert result.coverage.missing_count == 1


def test_weekly_mean_source_coverage_threshold_and_counts():
    end = MON + timedelta(days=41)
    keys = ("weekly.state.mood.mean", "weekly.state.sleep_minutes.mean")
    for days_per_week, expected in [(3, 0), (4, 6)]:
        states = {MON + timedelta(days=i): StateValues(mood=i % 5 + 1, sleep_minutes=100 + i)
                  for i in range(42) if i % 7 < days_per_week}
        data = build_dataset(DatasetInput((), states), MON, end, today=TODAY)
        result = analyze(data, MON, end, keys).relationships[0]
        assert result.n == expected
        assert result.coverage.source_x.ratio == days_per_week / 7
        assert result.coverage.eligible_count == 6
        assert result.coverage.losses["low_source_coverage"] == 6 - expected
    empty = build_dataset(DatasetInput((), {}), MON, end, today=TODAY)
    result = analyze(empty, MON, end, ("weekly.state.mood.observed_count",
                                      "weekly.state.sleep_minutes.observed_count")).relationships[0]
    assert result.n == 6 and result.status == "constant_series"
    assert result.coverage.source_x.ratio == 0
