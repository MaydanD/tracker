"""Calendar sign, boundary, sample and coverage invariants for pure Stage 7D."""

from dataclasses import asdict, fields, replace
from datetime import date, timedelta
import json
from math import sqrt

import pytest

from app.domain.analytics.builder import build_dataset, dates
from app.domain.analytics.descriptive_types import Period, SeriesPoint
from app.domain.analytics.lags import (
    align_lagged_pairs, analyze, normalize_lags, request_variables,
    required_source_range, select_lags, shift_date,
)
from app.domain.analytics.relationship_types import POLICY, Relationship
from app.domain.analytics.relationships import analyze as same_period, analyze_paired, filter_pairs
from app.domain.analytics.types import Availability as A, DatasetInput, Grain, VariableType as T
from app.domain.daily_state import StateValues
from app.schemas.lags import LagAnalyticsRead
from tests.test_relationships import MON, TODAY, X, Y, points


def lag_pair(a, b, lag=1, tx=T.NUMERIC, ty=T.NUMERIC):
    x, y = replace(X, type=tx), replace(Y, type=ty)
    xs, ys = points(a), points(b, start=MON + timedelta(days=lag))
    aligned = align_lagged_pairs(xs, ys, lag, Grain.DAILY)
    return analyze_paired(x, y, aligned.x, aligned.y,
                          filter_pairs(x, y, aligned.x, aligned.y, today=TODAY))


def dataset(start, end, *, today=TODAY, sparse=False):
    states = {on: StateValues(sleep_minutes=i + 1, computer_minutes=2 * i + 3,
                              mood=i % 5 + 1, alcohol=bool(i % 2))
              for i, on in enumerate(dates(start, end)) if not sparse or i % 7 < 3}
    return build_dataset(DatasetInput((), states), start, end, today=today)


@pytest.mark.parametrize("lag", [-7, -1, 0, 1, 2, 7])
def test_alignment_sign_keeps_original_coordinates_and_values(lag):
    xs, ys = points([1, None, 3]), points([10, 20, None], start=MON + timedelta(days=lag))
    aligned = align_lagged_pairs(tuple(reversed(xs)), tuple(reversed(ys)), lag, Grain.DAILY)
    assert aligned.x == xs and aligned.y == ys
    assert all((b.date - a.date).days == lag for a, b in zip(aligned.x, aligned.y))
    assert aligned.x[1].value is None and aligned.y[2].value is None


def test_alignment_joins_coordinates_never_positions_or_synthetic_points():
    xs, ys = points([1, 2, 3]), points([10, 20, 30], start=MON + timedelta(days=1))
    aligned = align_lagged_pairs(xs[::2], ys, 1, Grain.DAILY)
    assert aligned.x == xs[::2] and aligned.y == ys[::2]
    assert align_lagged_pairs((), ys, 1, Grain.DAILY).x == ()
    for a, b in ((xs + xs, ys), (xs, ys + ys)):
        with pytest.raises(ValueError):
            align_lagged_pairs(a, b, 1, Grain.DAILY)


def test_direction_is_unambiguous_on_nontrending_data():
    # Y tomorrow copies X today. Alternating / monotonic fixtures can mask a
    # reversed sign, so use an irregular sequence and verify both directions.
    values = [8, 1, 6, 3, 9, 2, 7, 0, 4, 5, 2, 9, 1, 7, 3, 6, 0, 8, 4, 2]
    states = {MON + timedelta(days=i): StateValues(
        sleep_minutes=values[i], computer_minutes=values[i - 1] if i else None)
        for i in range(len(values))}
    end = MON + timedelta(days=len(values) - 1)
    data = build_dataset(DatasetInput((), states), MON, end, today=TODAY)
    results = analyze(data, MON + timedelta(days=1), end - timedelta(days=1),
                      ("state.sleep_minutes", "state.computer_minutes"), (1, -1)).results
    negative, positive = results
    assert [r.lag for r in results] == [-1, 1]
    assert positive.coefficient == pytest.approx(1) and positive.strength == "strong"
    assert abs(negative.coefficient) < 0.8


@pytest.mark.parametrize("grain,lag,expected_start,expected_end", [
    (Grain.DAILY, 7, date(2026, 8, 25), date(2026, 9, 30)),
    (Grain.DAILY, -7, date(2026, 9, 1), date(2026, 10, 7)),
    (Grain.DAILY, 0, date(2026, 9, 1), date(2026, 9, 30)),
    (Grain.WEEKLY, 1, date(2026, 8, 25), date(2026, 9, 30)),
    (Grain.WEEKLY, -1, date(2026, 9, 1), date(2026, 10, 7)),
])
def test_required_range_extends_only_the_needed_boundary(grain, lag, expected_start, expected_end):
    period = Period(date(2026, 9, 1), date(2026, 9, 30))
    assert required_source_range(period, (lag,), grain) == Period(expected_start, expected_end)


def test_scan_extends_both_boundaries_and_preserves_all_target_days():
    start, end = date(2026, 9, 1), date(2026, 9, 30)
    required = required_source_range(Period(start, end), (7, -7, 0), Grain.DAILY)
    assert required == Period(date(2026, 8, 25), date(2026, 10, 7))
    data = dataset(required.start, required.end)
    result = analyze(data, start, end, ("state.sleep_minutes", "state.computer_minutes"), (7, -7, 0))
    assert result.source_range == required and result.target_period == Period(start, end)
    for r in result.results:
        assert r.n == r.potential_aligned_count == r.coverage.requested_count == 30
        assert r.coefficient == pytest.approx(1) and r.coverage.pair_coverage == 1
        assert r.x_period == Period(start - timedelta(days=r.lag), end - timedelta(days=r.lag))
    with pytest.raises(ValueError, match="расширенный"):
        analyze(dataset(start, end), start, end, ("state.sleep_minutes", "state.computer_minutes"), (7,))


@pytest.mark.parametrize("on,lag,grain,expected", [
    (date(2026, 1, 1), 1, Grain.DAILY, date(2025, 12, 31)),
    (date(2025, 12, 31), -1, Grain.DAILY, date(2026, 1, 1)),
    (date(2024, 3, 1), 1, Grain.DAILY, date(2024, 2, 29)),
    (date(2024, 3, 1), 2, Grain.DAILY, date(2024, 2, 28)),
    (date(2024, 2, 28), -1, Grain.DAILY, date(2024, 2, 29)),
    (date(2024, 2, 29), -1, Grain.DAILY, date(2024, 3, 1)),
    (MON, 1, Grain.DAILY, date(2026, 9, 6)),
    (date(2021, 1, 4), 1, Grain.WEEKLY, date(2020, 12, 28)),
    (date(2020, 12, 28), 1, Grain.WEEKLY, date(2020, 12, 21)),
    (date(2020, 12, 28), -1, Grain.WEEKLY, date(2021, 1, 4)),
])
def test_calendar_shifting(on, lag, grain, expected):
    assert shift_date(on, lag, grain) == expected
    xs, ys = points([1], start=expected), points([2], start=on)
    assert align_lagged_pairs(xs, ys, lag, grain).x == xs


@pytest.mark.parametrize("on,lag", [(date.min, 1), (date.max, -1)])
@pytest.mark.parametrize("grain", list(Grain))
def test_overflow_is_validation_error(on, lag, grain):
    with pytest.raises(ValueError, match="границы"):
        required_source_range(Period(on, on), (lag,), grain)
    assert shift_date(on, 0, grain) == on


@pytest.mark.parametrize("grain", list(Grain))
@pytest.mark.parametrize("target_start,target_end,today", [
    (MON, MON + timedelta(days=41), TODAY),
    (MON + timedelta(days=1), MON + timedelta(days=39), TODAY),
    (MON, MON + timedelta(days=41), MON + timedelta(days=34)),
    (date(2024, 2, 27), date(2024, 3, 7), TODAY),
])
def test_zero_lag_full_relationship_equals_7c_even_inside_scan(grain, target_start, target_end, today):
    prefix, suffix = ("weekly.", ".mean") if grain == Grain.WEEKLY else ("", "")
    keys = (f"{prefix}state.sleep_minutes{suffix}", f"{prefix}state.mood{suffix}")
    source = required_source_range(Period(target_start, target_end), (-7, 0, 7), grain)
    data = dataset(source.start, source.end, today=today)
    expected = same_period(data, target_start, target_end, keys, pair=True).relationships[0]
    result = analyze(data, target_start, target_end, keys, (7, 0, -7)).results[1]
    assert {f.name: getattr(result, f.name) for f in fields(Relationship)} == asdict_shallow(expected)


def asdict_shallow(value):
    return {f.name: getattr(value, f.name) for f in fields(value)}


@pytest.mark.parametrize("a,b,tx,ty,method,expected", [
    ([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], T.NUMERIC, T.NUMERIC, "pearson", 1),
    ([1, 2, 2, 4, 5], [5, 1, 1, 3, 2], T.ORDINAL, T.NUMERIC, "spearman", -3 / 19),
    ([False] * 3 + [True] * 3, [1, 2, 3, 4, 5, 6], T.BOOLEAN, T.NUMERIC, "point_biserial", 9 / sqrt(105)),
    ([1, 2, 3, 4, 5, 6], [False] * 3 + [True] * 3, T.NUMERIC, T.BOOLEAN, "point_biserial", 9 / sqrt(105)),
    ([False, True] * 3, [1, 5] * 3, T.BOOLEAN, T.ORDINAL, "point_biserial", 1),
    ([False, True] * 3, [False, True] * 3, T.BOOLEAN, T.BOOLEAN, "phi", 1),
])
def test_lagged_methods_reuse_7c(a, b, tx, ty, method, expected):
    result = lag_pair(a, b, tx=tx, ty=ty)
    assert result.method == method and result.coefficient == pytest.approx(expected)
    assert result.status == "ok" and result.strength is None
    if tx == ty == T.NUMERIC:
        assert [m.method for m in result.metrics] == ["pearson", "spearman"]


@pytest.mark.parametrize("n,status,strength", [(0, "insufficient_data", None), (4, "insufficient_data", None),
                                               (5, "ok", None), (9, "ok", None), (10, "ok", "strong")])
def test_sample_thresholds(n, status, strength):
    result = lag_pair(list(range(n)), list(range(n)))
    assert result.n == n and result.status == status and result.strength == strength


def test_constant_categorical_and_invalid_values():
    assert lag_pair([1] * 5, list(range(5))).status == "constant_series"
    assert lag_pair(["a"] * 5, list(range(5)), tx=T.CATEGORICAL).status == "unsupported"
    result = lag_pair([0, 1, 2, 3, 4, float("nan"), float("inf"), True], list(range(8)))
    assert result.n == 5 and result.coverage.losses["invalid_value"] == 3
    assert result.coefficient == pytest.approx(1)
    json.dumps(asdict(result), allow_nan=False)


def test_pairwise_null_boolean_false_and_zero_stay_distinct():
    result = lag_pair([False, True, None, True, False, True, False], [0, 1, 99, None, 0, 1, 0], tx=T.BOOLEAN)
    assert result.n == 5 and result.boolean_x.false_count == 3
    assert result.boolean_x.true_count == 2 and result.coverage.missing_count == 2
    assert result.coverage.eligible_count == result.coverage.requested_count == 7
    assert result.coverage.pair_coverage == 5 / 7
    assert result.coefficient == pytest.approx(1)


def test_current_day_and_future_x_or_y_even_for_present_calendar_values():
    today = MON + timedelta(days=7)
    data = dataset(MON - timedelta(days=7), MON + timedelta(days=14), today=today)
    keys = ("state.sleep_minutes", "state.computer_minutes")
    result = analyze(data, MON, today, keys, (1, -1)).results
    assert result[1].n == 8 and result[1].coverage.includes_today
    assert result[0].n == 7 and result[0].coverage.losses["future"] == 1
    assert result[0].coverage.includes_today  # X today is paired with Y yesterday.
    calendars = analyze(data, MON, today + timedelta(days=1), ("daily.weekend", "daily.year"), (-1, 1)).results
    assert calendars[0].coverage.losses["future"] == 2
    assert calendars[1].coverage.losses["future"] == 1


def test_weekly_alignment_and_partial_source_policy():
    start, end = date(2021, 1, 4), date(2021, 2, 14)
    data = dataset(start - timedelta(days=7), end + timedelta(days=7))
    keys = ("weekly.state.sleep_minutes.mean", "weekly.state.computer_minutes.mean")
    result = analyze(data, start, end, keys, (1,)).results[0]
    assert result.n == result.potential_aligned_count == 6
    assert result.lag_unit == "week" and result.coefficient == pytest.approx(1)
    assert result.coverage.paired_source_x.observed_count == 42
    # ISO 2020-W53 is a real previous-week coordinate, not week_number - 1.
    assert result.x_period.start == date(2020, 12, 28)
    partial = analyze(data, start + timedelta(days=1), end - timedelta(days=1), keys, (1,)).results[0]
    assert partial.n == 4 and partial.coverage.losses["incomplete_period"] == 2
    sparse = analyze(dataset(data.start, data.end, sparse=True), start, end, keys, (1,)).results[0]
    assert sparse.n == 0 and sparse.coverage.losses["low_source_coverage"] == 6
    assert sparse.coverage.source_x.ratio == 3 / 7
    with pytest.raises(ValueError, match="каноническое"):
        align_lagged_pairs(points([1], start=start + timedelta(days=1)), (), 1, Grain.WEEKLY)


@pytest.mark.parametrize("today_offset,lag,expected", [(34, 1, 4), (34, -1, 3), (35, 1, 5), (35, -1, 4)])
def test_current_week_including_sunday_excluded_on_both_sides(today_offset, lag, expected):
    data = dataset(MON - timedelta(days=7), MON + timedelta(days=48), today=MON + timedelta(days=today_offset))
    result = analyze(data, MON, MON + timedelta(days=41),
                     ("weekly.state.sleep_minutes.mean", "weekly.state.computer_minutes.mean"), (lag,)).results[0]
    assert result.n == expected and result.coverage.excluded_count == 6 - expected


def test_grain_mismatch_is_typed_and_not_aggregated():
    data = dataset(MON, MON + timedelta(days=6))
    result = analyze(data, data.start, data.end, ("state.mood", "weekly.state.mood.mean"), (-7, 0, 7))
    for r in result.results:
        assert r.status == "unsupported" and r.reason == "grain_mismatch"
        assert r.n == r.potential_aligned_count == 0
        assert r.coverage is r.grain is r.lag_unit is r.x_period is None


def test_normalization_and_all_request_limits():
    assert select_lags() == (0,)
    assert select_lags(lag=1) == (1,)
    assert select_lags(lags=(7, -1, 0, -1)) == (-1, 0, 7)
    assert select_lags(lag_start=-7, lag_end=7) == tuple(range(-7, 8))
    for invalid in ((), (8,), (-8,), (True,), (1.5,), ("1",), (0,) * 16):
        with pytest.raises(ValueError):
            normalize_lags(invalid)
    for kwargs in ({"lag": 0, "lags": (1,)}, {"lag_start": 0}, {"lag_end": 0},
                   {"lag_start": 2, "lag_end": 1}, {"lag_start": -999999, "lag_end": 999999},
                   {"lags": (1,), "lag_start": 0, "lag_end": 1}):
        with pytest.raises(ValueError):
            select_lags(**kwargs)
    request_variables(MON, MON + timedelta(days=POLICY.max_period_days - 1), ("state.mood", "state.energy"))
    for start, end, keys in ((MON, MON + timedelta(days=POLICY.max_period_days), ("state.mood", "state.energy")),
                             (MON, MON - timedelta(days=1), ("state.mood", "state.energy")),
                             (MON, MON, ("state.mood", "unknown")),
                             (MON, MON, ("state.mood", "state.mood"))):
        with pytest.raises(ValueError):
            request_variables(start, end, keys)


@pytest.mark.parametrize("on", [date.min, date.max])
def test_lag_zero_at_date_extremes_serializes_finite(on):
    data = dataset(on, on, today=on)
    result = analyze(data, on, on, ("state.sleep_minutes", "state.mood"), (0,))
    assert result.results[0].n == 1
    encoded = LagAnalyticsRead(result).model_dump_json()
    assert LagAnalyticsRead.model_validate_json(encoded).root == result
    json.dumps(json.loads(encoded), allow_nan=False)
