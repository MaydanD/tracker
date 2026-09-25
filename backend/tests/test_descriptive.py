"""Pure analytical rules and canonical dataset projection; no database needed."""

from dataclasses import replace
from datetime import date, timedelta
import json
from math import sqrt

import pytest

from app.domain.analytics.builder import build_dataset, slice_dataset
from app.domain.analytics.descriptive import (
    analyze, compare, coverage, request_periods, rolling, summarize, trend,
)
from app.domain.analytics.descriptive_types import POLICY, Period, SeriesPoint
from app.domain.analytics.types import (
    AnalyticsDataset, Availability as A, DailyRow, DatasetInput, Grain, Value, Variable,
    VariableType as T,
)
from app.domain.daily_state import StateValues
from app.schemas.descriptive import DescriptiveAnalyticsRead


MON = date(2026, 9, 7)
NUMERIC = Variable("test", "Число", T.NUMERIC, Grain.DAILY, "test", "Без подстановки")
ORDINAL = replace(NUMERIC, type=T.ORDINAL, minimum=1, maximum=5)
BOOLEAN = replace(NUMERIC, type=T.BOOLEAN)
CATEGORY = replace(NUMERIC, type=T.CATEGORICAL, categories=("underslept", "normal", "overslept"))


def points(values, start=MON, reasons=None, units=None):
    return tuple(SeriesPoint(start + timedelta(days=i), value,
                             A.PRESENT if value is not None else
                             reasons[i] if reasons else A.SOURCE_MISSING,
                             False, units[i] if units else None)
                 for i, value in enumerate(values))


def summary(values, variable=NUMERIC, **kwargs):
    series = points(values, **kwargs)
    return summarize(variable, series, Period(series[0].date, series[-1].date))


@pytest.mark.parametrize("values,expected_mean,expected_median,expected_range,sd", [
    ([None, None], None, None, None, None),
    ([0], 0, 0, 0, None),
    ([5], 5, 5, 0, None),
    ([0, -2, None, 4], 2 / 3, 0, 6, sqrt(56 / 9)),
    ([1, 2, 3, 4], 2.5, 2.5, 3, sqrt(1.25)),
    ([3, 3, None, 3], 3, 3, 0, 0),
])
def test_numeric(values, expected_mean, expected_median, expected_range, sd):
    result = summary(values)
    stats = result.statistics
    assert stats.mean == pytest.approx(expected_mean) if expected_mean is not None else stats.mean is None
    assert stats.median == expected_median
    assert stats.range == expected_range
    assert stats.standard_deviation == pytest.approx(sd) if sd is not None else stats.standard_deviation is None
    count = sum(v is not None for v in values)
    assert result.coverage.observed_count == count
    assert result.coverage.missing_count == len(values) - count
    assert stats.variability_status == ("ok" if count >= 2 else "insufficient_data")
    assert stats.status == ("ok" if count else "insufficient_data")


def test_boolean_tristate_denominator():
    result = summary([True, True, False, None, None], BOOLEAN)
    assert result.coverage.observed_count == 3
    assert result.coverage.missing_count == 2
    assert result.coverage.ratio == 3 / 5
    assert result.statistics.true_count == 2
    assert result.statistics.false_count == 1
    assert result.statistics.true_rate == 2 / 3
    assert summary([None], BOOLEAN).statistics.true_rate is None
    assert summary([False], BOOLEAN).statistics.true_rate == 0


def test_each_unavailable_reason_is_preserved():
    reasons = list(A)
    result = coverage(points([0] + [None] * (len(reasons) - 1), reasons=reasons))
    assert result.total_count == 7
    assert result.observed_count == 1 and result.missing_count == 3
    assert result.eligible_count == 4 and result.ratio == 0.25
    assert result.unavailable_count == 6
    assert result.counts_by_availability == {reason: 1 for reason in A}
    excluded = coverage(points([None] * 3, reasons=[A.NOT_APPLICABLE, A.FUTURE, A.NO_OBLIGATIONS]))
    assert excluded.eligible_count == 0 and excluded.ratio is None


def test_ordinal_distribution_includes_all_scale_values():
    result = summary([1, 2, 3, 4, 5, None, 5], ORDINAL)
    assert result.statistics.mean == 20 / 6
    assert result.statistics.median == 3.5
    assert [(f.value, f.count) for f in result.statistics.distribution] == [(1, 1), (2, 1), (3, 1), (4, 1), (5, 2)]
    assert result.statistics.distribution[-1].proportion == 2 / 6
    assert all(f.proportion is None for f in summary([None], ORDINAL).statistics.distribution)
    window = rolling(ORDINAL, points([1, 2, 3, 4, 5, None, 5]))[-2]
    assert window.mean == 20 / 6 and window.observed_count == 6


def test_categorical_distribution_and_tied_modes():
    result = summary(["normal", "overslept", None, "normal", "overslept"], CATEGORY)
    assert [(f.value, f.count, f.proportion) for f in result.statistics.distribution] == [
        ("underslept", 0, 0), ("normal", 2, 0.5), ("overslept", 2, 0.5)]
    assert result.statistics.modes == ("normal", "overslept")
    assert summary([None], CATEGORY).statistics.modes == ()
    assert not hasattr(result.statistics, "mean")
    assert not rolling(CATEGORY, points(["normal"] * 7))


@pytest.mark.parametrize("size,observations,expected", [(7, 3, None), (7, 4, 2), (28, 13, None), (28, 14, 2)])
def test_rolling_minimum_observations(size, observations, expected):
    values = [2] * observations + [None] * (size - observations)
    result = [p for p in rolling(NUMERIC, points(values)) if p.window_size == size][-1]
    assert result.mean == expected and result.observed_count == observations
    assert result.required_count == (size + 1) // 2
    assert result.status == ("ok" if expected is not None else "insufficient_data")


def test_rolling_exact_boundaries_and_no_start_fabrication():
    result = [p for p in rolling(NUMERIC, points([100] + list(range(1, 8)))) if p.window_size == 7]
    assert all(p.mean is None for p in result[:6])
    assert result[6].mean == 121 / 7
    assert result[7].mean == 4 and result[7].window_start == MON + timedelta(days=1)
    empty = rolling(NUMERIC, points([None] * 28))[-1]
    assert empty.mean is None and empty.observed_count == 0
    zero = rolling(NUMERIC, points([0] * 7))[-2]
    assert zero.mean == 0
    earliest = rolling(NUMERIC, points([1], start=date.min))[0]
    assert earliest.window_start is None and earliest.mean is None


def test_rolling_today_and_mixed_units_suppressed():
    series = points([1] * 7)
    live = series[:-1] + (replace(series[-1], incomplete=True),)
    assert rolling(NUMERIC, live)[-2].status == "incomplete_period"
    mixed = points([1] * 7, units=["км"] * 6 + ["м"])
    assert rolling(NUMERIC, mixed)[-2].status == "incompatible_units"
    assert summary([1, 10], units=["км", "м"]).statistics.mean is None


@pytest.mark.parametrize("current,previous,status,delta,relative", [
    ([4] * 4, [2] * 4, "ok", 2, 1),
    ([1] * 4, [0] * 4, "ok", 1, None),
    ([-1] * 4, [-2] * 4, "ok", 1, 0.5),
    ([1, None, None, None], [2] * 4, "insufficient_data", None, None),
    ([1] * 3 + [None] * 4, [2] * 7, "insufficient_data", None, None),
    ([1] * 4 + [None] * 3, [2] * 7, "coverage_mismatch", None, None),
    ([1] * 3 + [None], [2] * 4, "ok", -1, -0.5),
])
def test_comparison(current, previous, status, delta, relative):
    result = compare(NUMERIC, summary(current), summary(previous))
    assert result.status == status and result.absolute_delta == delta
    assert result.relative_delta == relative
    assert result.percentage_delta == (relative * 100 if relative is not None else None)


def test_comparison_boolean_and_categorical():
    result = compare(BOOLEAN, summary([True, True, False, None], BOOLEAN),
                     summary([False, False, True, None], BOOLEAN))
    assert result.metric == "true_rate" and result.absolute_delta == pytest.approx(1 / 3)
    categories = compare(CATEGORY, summary(["normal"] * 3, CATEGORY), summary(["overslept"] * 3, CATEGORY))
    assert categories.status == "ok" and categories.metric == "distribution"
    assert categories.absolute_delta is categories.relative_delta is None
    assert categories.previous.statistics.modes == ("overslept",)


def test_comparison_units_and_applicability_mismatch():
    assert compare(NUMERIC, summary([1] * 3, units=["м"] * 3),
                   summary([1] * 3, units=["км"] * 3)).status == "incompatible_units"
    partial = summary([1, 1, 1, None], reasons=[A.PRESENT] * 3 + [A.NOT_APPLICABLE])
    assert compare(NUMERIC, partial, summary([1] * 4)).status == "coverage_mismatch"


@pytest.mark.parametrize("values,variable,direction", [
    ([1] * 3 + [5] * 3, ORDINAL, "rising"),
    ([5] * 3 + [1] * 3, ORDINAL, "falling"),
    ([2] * 6, ORDINAL, "stable"),
    ([100] * 3 + [102] * 3, NUMERIC, "stable"),
    ([100] * 3 + [120] * 3, NUMERIC, "rising"),
    ([0] * 6, NUMERIC, "stable"),
    ([1, 2, 3, None, 4, 5], ORDINAL, "insufficient_data"),
    ([True] * 6, BOOLEAN, "not_supported"),
    (["normal"] * 6, CATEGORY, "not_supported"),
    ([0, 10, 0, 10, 0, 10, 0, 10], NUMERIC, "stable"),
])
def test_trend(values, variable, direction):
    series = points(values)
    result = trend(variable, series, Period(series[0].date, series[-1].date))
    assert result.direction == direction
    if result.status == "ok":
        assert result.absolute_delta == result.second_median - result.first_median
        assert result.threshold >= 0 and result.first_observed_count >= 3
        assert result.split_date == series[len(series) // 2].date


@pytest.mark.parametrize("start,end,previous_start,previous_end", [
    (date(2026, 9, 1), date(2026, 9, 30), date(2026, 8, 2), date(2026, 8, 31)),
    (date(2024, 3, 1), date(2024, 3, 29), date(2024, 2, 1), date(2024, 2, 29)),
    (date(2026, 1, 1), date(2026, 1, 7), date(2025, 12, 25), date(2025, 12, 31)),
    (date.max, date.max, date.max - timedelta(days=1), date.max - timedelta(days=1)),
])
def test_period_boundaries(start, end, previous_start, previous_end):
    current, previous = request_periods(start, end, ("test",))
    assert current == Period(start, end) and previous == Period(previous_start, previous_end)
    assert (current.end - current.start) == (previous.end - previous.start)


@pytest.mark.parametrize("start,end,keys", [
    (date.min, date.min, ("test",)), (MON, MON - timedelta(days=1), ("test",)),
    (MON, MON + timedelta(days=POLICY.max_period_days), ("test",)),
    (MON, MON, ()), (MON, MON, ("test", "test")), (MON, MON, ("",)),
    (MON, MON, tuple(str(i) for i in range(65))), (MON, MON, ("x" * 161,)),
])
def test_invalid_requests(start, end, keys):
    with pytest.raises(ValueError):
        request_periods(start, end, keys)


def state_dataset(start, end, today, **fields):
    return build_dataset(DatasetInput((), {day: StateValues(**values) for day, values in
                         ((start + timedelta(days=i), fields) for i in range((end - start).days + 1))}),
                         start, end, today=today)


def test_single_dataset_projection_separates_state_in_shared_week():
    states = {MON + timedelta(days=i): StateValues(mood=1 if i < 3 else 5) for i in range(6)}
    dataset = build_dataset(DatasetInput((), states), MON, MON + timedelta(days=5), today=MON + timedelta(days=9))
    result = analyze(dataset, MON + timedelta(days=3), MON + timedelta(days=5),
                     ("weekly.state.mood.mean", "state.mood"))
    weekly = result.variables[1]
    assert weekly.summary.statistics.mean == 5
    assert weekly.comparison.previous.statistics.mean == 1
    assert weekly.comparison.status == "incomplete_period"
    assert weekly.series[0].source_coverage.observed_count == 3
    assert weekly.series[0].week.requested_days == 3
    assert dataset.weekly[0].values["weekly.state.mood.mean"].value == 3
    assert DescriptiveAnalyticsRead.model_validate_json(DescriptiveAnalyticsRead(result).model_dump_json()).root == result


def test_weekly_windows_use_weeks_and_expose_daily_coverage():
    end = MON + timedelta(days=111)
    dataset = state_dataset(MON, end, end + timedelta(days=1), mood=3)
    result = analyze(dataset, MON + timedelta(days=56), end, ("weekly.state.mood.mean",)).variables[0]
    assert len(result.series) == 8 and all(p.date.weekday() == 0 for p in result.series)
    windows = [p for p in result.rolling if p.window_size == 4]
    assert all(p.mean is None for p in windows[:3])
    assert all(p.mean == 3 for p in windows[3:])
    assert windows[3].window_unit == "weeks" and windows[3].observed_count == 4
    assert windows[3].window_start == MON + timedelta(days=56)
    assert result.summary.source_coverage.observed_count == 56
    assert result.comparison.status == "ok" and result.comparison.absolute_delta == 0
    assert result.trend.direction == "stable"


def test_weekly_sparse_means_not_mistaken_for_complete_coverage():
    end = MON + timedelta(days=55)
    states = {MON + timedelta(days=i): StateValues(mood=3) for i in range(0, 56, 7)}
    dataset = build_dataset(DatasetInput((), states), MON, end, today=end + timedelta(days=1))
    result = analyze(dataset, MON + timedelta(days=28), end, ("weekly.state.mood.mean",)).variables[0]
    assert result.summary.coverage.ratio == 1
    assert result.summary.source_coverage.ratio == 1 / 7
    assert result.comparison.status == "insufficient_data"
    assert result.rolling[-2].status == "insufficient_data"
    assert result.trend.status == "insufficient_data"


@pytest.mark.parametrize("today_offset", [27, 28, 30, 34, 35])
def test_current_week_and_sunday_are_incomplete(today_offset):
    dataset = state_dataset(MON, MON + timedelta(days=41), MON + timedelta(days=today_offset), mood=3)
    result = analyze(dataset, MON + timedelta(days=21), MON + timedelta(days=41),
                     ("weekly.state.mood.mean", "state.mood"))
    assert all(v.comparison.status == "incomplete_period" for v in result.variables)
    daily = result.variables[0]
    assert all(p.availability == A.FUTURE and p.value is None for p in daily.series if p.date > dataset.today)
    assert daily.summary.coverage.counts_by_availability[A.FUTURE] == 41 - today_offset


def test_extreme_finite_values_never_leak_nonfinite_json():
    values = [-1e308] * 3 + [1e308] * 3
    daily = tuple(DailyRow(MON + timedelta(days=i), MON, {"test": Value(v)}, {}, None)
                  for i, v in enumerate(values))
    dataset = AnalyticsDataset("7A.1", MON, MON + timedelta(days=5), MON + timedelta(days=6),
                               (NUMERIC,), daily, ())
    result = analyze(dataset, MON + timedelta(days=3), MON + timedelta(days=5), ("test",))
    payload = DescriptiveAnalyticsRead(result).model_dump(mode="json")
    json.dumps(payload, allow_nan=False)
    assert result.variables[0].comparison.status == "numerical_overflow"
    assert summary([-1e308, 1e308]).statistics.range is None
    assert summary([1e308, 1e308]).statistics.mean == 1e308


def test_projection_date_edges_and_no_mutation():
    start, end = date(2024, 2, 25), date(2024, 3, 3)
    dataset = state_dataset(start, end, date(2024, 3, 4), mood=4)
    view = slice_dataset(dataset, date(2024, 2, 26), end)
    assert len(view.daily) == 7 and len(view.weekly) == 1
    assert not view.weekly[0].partial_requested_week
    assert view.daily[3].date == date(2024, 2, 29)
    assert len(dataset.daily) == 8 and len(dataset.weekly) == 2
    with pytest.raises(ValueError):
        slice_dataset(dataset, start - timedelta(days=1), end)


def test_rolling_twelve_weeks_requires_six_observations():
    variable = replace(NUMERIC, grain=Grain.WEEKLY)
    series = tuple(replace(p, date=MON + timedelta(weeks=i))
                   for i, p in enumerate(points([2] * 6 + [None] * 6)))
    result = rolling(variable, series)[-1]
    assert result.window_size == 12 and result.required_count == 6
    assert result.window_start == MON and result.mean == 2
    assert result.observed_count == 6
    assert all(p.mean is None for p in rolling(variable, series[:-1]) if p.window_size == 12)


def test_trend_threshold_equality_and_insufficient_halves():
    series = points([100] * 3 + [105] * 3)
    result = trend(NUMERIC, series, Period(MON, series[-1].date))
    assert result.threshold == 5 and result.direction == "stable"
    for variable in (NUMERIC, ORDINAL):
        assert trend(variable, points([None] * 8), Period(MON, MON)).status == "insufficient_data"
        assert trend(variable, points([1]), Period(MON, MON)).status == "insufficient_data"
    mixed = points([1] * 3 + [2] * 3, units=["м"] * 3 + ["км"] * 3)
    assert trend(NUMERIC, mixed, Period(MON, mixed[-1].date)).status == "incompatible_units"


def test_relative_overflow_is_safe_and_extreme_mean_does_not_overflow():
    result = compare(NUMERIC, summary([1e308] * 3), summary([5e-324] * 3))
    assert result.status == "numerical_overflow"
    assert result.relative_delta is result.percentage_delta is None
    assert result.absolute_delta == 1e308
    result = compare(NUMERIC, summary([1e308] * 3), summary([1e308] * 3))
    assert result.status == "ok" and result.absolute_delta == 0


def test_weekly_source_coverage_difference_suppresses_delta():
    end = MON + timedelta(days=55)
    states = {MON + timedelta(days=i): StateValues(mood=3)
              for i in range(56) if i < 28 or i % 7 < 4}
    dataset = build_dataset(DatasetInput((), states), MON, end, today=end + timedelta(days=1))
    result = analyze(dataset, MON + timedelta(days=28), end, ("weekly.state.mood.mean",)).variables[0]
    assert result.summary.coverage.ratio == 1
    assert result.summary.source_coverage.ratio == 4 / 7
    assert result.comparison.status == "coverage_mismatch" and result.comparison.absolute_delta is None


def test_daily_known_future_plan_stays_present_without_making_comparison_complete():
    start, end = MON - timedelta(days=2), MON + timedelta(days=1)
    dataset = build_dataset(DatasetInput((), {}), start, end, today=MON)
    result = analyze(dataset, MON, end, ("daily.required_weight", "daily.score"))
    plan, score = result.variables
    assert plan.series[-1].availability == A.PRESENT and plan.series[-1].value == 0
    assert plan.series[-1].incomplete and plan.comparison.status == "incomplete_period"
    assert score.series[0].availability == A.NO_OBLIGATIONS
    assert score.series[1].availability == A.FUTURE
    assert score.summary.coverage.eligible_count == 0


def test_limit_allows_full_year_and_maximum_selected_span():
    start = date(2020, 1, 1)
    current, previous = request_periods(start, start + timedelta(days=1829), ("test",))
    assert (current.end - previous.start).days + 1 == 3660
    current, previous = request_periods(date(2024, 1, 1), date(2024, 12, 31), ("test",))
    assert (previous.end - previous.start).days + 1 == 366
