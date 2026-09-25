"""Pure descriptive analytics over canonical 7A cells; no source-domain rules.

Policy and response types live in descriptive_types; the full semantics are in
docs/analytics-descriptive.md. No function here reads the database or wall clock.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import date
from math import ceil, isfinite
from statistics import mean, pstdev

from app.domain.analytics.builder import slice_dataset, validate_range
from app.domain.analytics.descriptive_types import (
    POLICY, BooleanStatistics, CategoricalStatistics, Comparison, Coverage,
    DescriptiveAnalytics, Frequency, HabitCompletion, NumericStatistics, Period,
    RollingPoint, SeriesPoint, Status, Summary, Trend, VariableAnalysis, WeekCoverage,
)
from app.domain.analytics.types import (
    AnalyticsDataset, Availability as A, DailyRow, Grain, Value, Variable,
    VariableType as T,
)


MISSING = (A.SOURCE_MISSING, A.FIELD_MISSING, A.NO_OBSERVATIONS)


def request_periods(start: date, end: date, keys: tuple[str, ...]) -> tuple[Period, Period]:
    validate_range(start, end)
    length = (end - start).days + 1
    if length > POLICY.max_period_days:
        raise ValueError(f"Период аналитики не должен превышать {POLICY.max_period_days} дней.")
    if not 1 <= len(keys) <= POLICY.max_variables:
        raise ValueError(f"Выберите от 1 до {POLICY.max_variables} переменных.")
    if len(set(keys)) != len(keys) or any(not key or len(key) > 160 for key in keys):
        raise ValueError("Ключи переменных должны быть непустыми, уникальными и не длиннее 160 символов.")
    if start.toordinal() <= length:
        raise ValueError("Предыдущий период выходит за границы допустимых дат.")
    return Period(start, end), Period(date.fromordinal(start.toordinal() - length),
                                     date.fromordinal(start.toordinal() - 1))


def coverage(cells: Iterable[Value | SeriesPoint]) -> Coverage:
    counts = Counter(cell.availability for cell in cells)
    return coverage_from_counts(counts)


def coverage_from_counts(counts: dict[A, int]) -> Coverage:
    reasons = {reason: counts.get(reason, 0) for reason in A}
    total = sum(reasons.values())
    observed = reasons[A.PRESENT]
    missing = sum(reasons[reason] for reason in MISSING)
    eligible = observed + missing
    return Coverage(total, eligible, observed, missing, total - observed,
                    observed / eligible if eligible else None, reasons)


def source_coverage(points: Iterable[SeriesPoint]) -> Coverage | None:
    counts: Counter = Counter()
    found = False
    for point in points:
        if point.source_coverage is not None:
            found = True
            counts.update(point.source_coverage.counts_by_availability)
    return coverage_from_counts(counts) if found else None


def finite_calculation(operation) -> float | None:
    """Finite inputs can still overflow during subtraction or dispersion."""
    try:
        result = float(operation())
        return result if isfinite(result) else None
    except (OverflowError, ValueError):
        return None


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return float(ordered[middle]) if len(ordered) % 2 else mean(ordered[middle - 1:middle + 1])


def distribution(values: list, categories: Iterable) -> tuple[Frequency, ...]:
    counts = Counter(values)
    # Registry order is display order, never an analytical ordinal mapping.
    order = list(categories)
    order.extend(sorted(set(counts) - set(order)))
    return tuple(Frequency(value, counts[value], counts[value] / len(values) if values else None)
                 for value in order)


def numeric_statistics(variable: Variable, values: list[float], *, mixed_units: bool = False
                       ) -> NumericStatistics:
    frequencies = (distribution(values, range(variable.minimum, variable.maximum + 1))
                   if variable.type == T.ORDINAL and variable.minimum is not None
                   and variable.maximum is not None else
                   distribution(values, sorted(set(values))) if variable.type == T.ORDINAL else None)
    status: Status = "incompatible_units" if mixed_units else "insufficient_data" if not values else "ok"
    if status != "ok":
        return NumericStatistics(variable.type.value, status, None, None, None, None, None,
                                 None, status, frequencies)
    average = finite_calculation(lambda: mean(values))
    middle = finite_calculation(lambda: median(values))
    spread = finite_calculation(lambda: max(values) - min(values))
    enough = len(values) >= POLICY.variability_minimum
    sd = finite_calculation(lambda: pstdev(values)) if enough else None
    variability_status: Status = ("insufficient_data" if not enough else
                                  "ok" if sd is not None else "numerical_overflow")
    if average is None or middle is None or spread is None:
        status = "numerical_overflow"
    return NumericStatistics(variable.type.value, status, average, middle, min(values), max(values),
                             spread, sd, variability_status, frequencies)


def make_series(dataset: AnalyticsDataset, variable: Variable,
                by_week: dict[date, list[DailyRow]]) -> tuple[SeriesPoint, ...]:
    points = []
    if variable.grain == Grain.DAILY:
        for row in dataset.daily:
            cell = row.values[variable.key]
            unit = None
            if variable.habit_id is not None and variable.key.endswith(".quantity"):
                context = row.habits[variable.habit_id]
                if context.configuration is not None:
                    unit = context.configuration.configuration.quantity_unit
            points.append(SeriesPoint(row.date, cell.value, cell.availability,
                                      row.date >= dataset.today, unit))
    else:
        for row in dataset.weekly:
            cell = row.values[variable.key]
            state_key = (variable.key.removeprefix("weekly.").rsplit(".", 1)[0]
                         if variable.key.startswith("weekly.state.") else None)
            days = by_week[row.week_start]
            sources = coverage(day.values[state_key] for day in days) if state_key else None
            habit_days = (sum(day.habits[variable.habit_id].applicable for day in days)
                          if variable.habit_id is not None else None)
            calendar_days = (row.week_end - row.week_start).days + 1
            partial_activity = (0 < habit_days < calendar_days if habit_days is not None else
                                0 < row.active_habit_days < calendar_days
                                if variable.source.startswith("stage4.") else False)
            week = WeekCoverage(
                row.week_start, row.week_end, row.requested_start, row.requested_end,
                row.requested_days, row.elapsed_requested_days, row.calendar_elapsed_days,
                row.partial_requested_week, row.unfinished_week, row.active_habit_days,
                habit_days, "requested_elapsed_dates" if state_key else "calendar_week")
            points.append(SeriesPoint(
                row.week_start, cell.value, cell.availability,
                row.partial_requested_week or row.unfinished_week or partial_activity,
                week=week, source_coverage=sources))
    return tuple(points)


def observed(points: Iterable[SeriesPoint]) -> list:
    return [point.value for point in points if point.availability == A.PRESENT]


def units(points: Iterable[SeriesPoint]) -> tuple[str, ...]:
    return tuple(sorted({p.unit for p in points if p.availability == A.PRESENT and p.unit is not None}))


def summarize(variable: Variable, points: tuple[SeriesPoint, ...], period: Period) -> Summary:
    covered = coverage(points)
    values = observed(points)
    observed_units = units(points)
    if variable.type in (T.NUMERIC, T.ORDINAL):
        stats = numeric_statistics(variable, values, mixed_units=len(observed_units) > 1)
    elif variable.type == T.BOOLEAN:
        true_count = sum(value is True for value in values)
        false_count = sum(value is False for value in values)
        stats = BooleanStatistics("boolean", true_count, false_count,
                                  true_count / len(values) if values else None)
    else:
        frequencies = distribution(values, variable.categories)
        maximum = max((item.count for item in frequencies), default=0)
        completion = None
        if variable.habit_id is not None and variable.key.endswith(".status"):
            counts = Counter(values)
            completion = HabitCompletion(counts["done"], counts["missed"], counts["skipped"],
                                         covered.missing_count, covered.eligible_count,
                                         counts["done"] / len(values) if values else None)
        stats = CategoricalStatistics("categorical", frequencies,
                                      tuple(item.value for item in frequencies
                                            if maximum and item.count == maximum), completion)
    return Summary(period, covered, source_coverage(points), any(p.incomplete for p in points),
                   observed_units, stats)


def adequate(variable: Variable, summary: Summary, minimum: int) -> bool:
    cov = summary.coverage
    if cov.observed_count < minimum or cov.ratio is None or cov.ratio < POLICY.minimum_coverage:
        return False
    if variable.source.startswith("observed_mean:"):
        source = summary.source_coverage
        if source is None or source.ratio is None or source.ratio < POLICY.minimum_coverage:
            return False
    return True


def compare(variable: Variable, current: Summary, previous: Summary) -> Comparison:
    metric = "true_rate" if variable.type == T.BOOLEAN else (
        "distribution" if variable.type == T.CATEGORICAL else "mean")
    minimum = (POLICY.daily_comparison_minimum if variable.grain == Grain.DAILY else
               POLICY.weekly_comparison_minimum)
    status: Status = "ok"
    if current.incomplete or previous.incomplete:
        status = "incomplete_period"
    elif len(set(current.units + previous.units)) > 1:
        status = "incompatible_units"
    elif not all(adequate(variable, s, minimum) for s in (current, previous)):
        status = "insufficient_data"
    else:
        pairs = [(current.coverage, previous.coverage)]
        if variable.source.startswith("observed_mean:"):
            pairs.append((current.source_coverage, previous.source_coverage))
        if any(a.eligible_count != b.eligible_count or
               abs(a.ratio - b.ratio) > POLICY.maximum_coverage_difference for a, b in pairs):
            status = "coverage_mismatch"
    delta = relative = percentage = None
    if status == "ok" and metric != "distribution":
        a = getattr(current.statistics, metric)
        b = getattr(previous.statistics, metric)
        if a is None or b is None:
            status = "numerical_overflow"
        else:
            delta = finite_calculation(lambda: a - b)
            if delta is None:
                status = "numerical_overflow"
            elif b != 0:
                relative = finite_calculation(lambda: delta / abs(b))
                percentage = finite_calculation(lambda: relative * 100) if relative is not None else None
                if relative is None or percentage is None:
                    status = "numerical_overflow"
    return Comparison(status, metric, current, previous, delta, relative, percentage)


def rolling(variable: Variable, points: tuple[SeriesPoint, ...]) -> tuple[RollingPoint, ...]:
    if variable.type not in (T.NUMERIC, T.ORDINAL):
        return ()
    daily = variable.grain == Grain.DAILY
    windows = POLICY.daily_windows if daily else POLICY.weekly_windows
    result = []
    # Windows are fixed and bounded (<= 28 cells); never rescan the full series.
    for index, point in enumerate(points):
        for size in windows:
            window = points[max(0, index - size + 1):index + 1]
            cov = coverage(window)
            required = ceil(size * POLICY.minimum_coverage)
            start_ordinal = point.date.toordinal() - (size - 1) * (1 if daily else 7)
            start = date.fromordinal(start_ordinal) if start_ordinal >= 1 else None
            status: Status = "ok"
            if len(window) < size or cov.observed_count < required:
                status = "insufficient_data"
            elif any(p.incomplete for p in window):
                status = "incomplete_period"
            elif len(units(window)) > 1:
                status = "incompatible_units"
            elif variable.source.startswith("observed_mean:"):
                source = source_coverage(window)
                if source is None or source.ratio is None or source.ratio < POLICY.minimum_coverage:
                    status = "insufficient_data"
            average = finite_calculation(lambda: mean(observed(window))) if status == "ok" else None
            if status == "ok" and average is None:
                status = "numerical_overflow"
            result.append(RollingPoint(point.date, start, size, "days" if daily else "weeks",
                                       len(window), cov.observed_count, required, cov, status, average))
    return tuple(result)


def trend(variable: Variable, points: tuple[SeriesPoint, ...], period: Period) -> Trend:
    def result(status, first=0, second=0, a=None, b=None, delta=None, threshold=None, direction=None):
        return Trend(status, direction or ("not_supported" if status == "not_supported" else
                                           "insufficient_data"), "half_period_medians",
                     points[len(points) // 2].date if points else None,
                     first, second, a, b, delta, threshold)

    if variable.type not in (T.NUMERIC, T.ORDINAL):
        return result("not_supported")
    split = len(points) // 2
    left, right = points[:split], points[split:]
    first, second = observed(left), observed(right)
    counts = (len(first), len(second))
    if any(p.incomplete for p in points):
        return result("incomplete_period", *counts)
    if len(units(points)) > 1:
        return result("incompatible_units", *counts)
    minimum = (POLICY.daily_trend_half_minimum if variable.grain == Grain.DAILY else
               POLICY.weekly_trend_half_minimum)
    if not all(adequate(variable, summarize(variable, half, period), minimum) for half in (left, right)):
        return result("insufficient_data", *counts)
    a, b = median(first), median(second)
    sd = finite_calculation(lambda: pstdev(first + second))
    delta = finite_calculation(lambda: b - a)
    if sd is None or delta is None:
        return result("numerical_overflow", *counts, a, b)
    floor = (POLICY.ordinal_trend_threshold if variable.type == T.ORDINAL else
             abs(a) * POLICY.trend_relative_threshold)
    threshold = max(floor, sd * POLICY.trend_sd_threshold)
    direction = "rising" if delta > threshold else "falling" if delta < -threshold else "stable"
    return result("ok", *counts, a, b, delta, threshold, direction)


def analyze(dataset: AnalyticsDataset, start: date, end: date,
            keys: tuple[str, ...]) -> DescriptiveAnalytics:
    current_period, previous_period = request_periods(start, end, keys)
    registry = {variable.key: variable for variable in dataset.variables}
    unknown = sorted(set(keys) - registry.keys())
    if unknown:
        raise ValueError("Неизвестные переменные аналитики: " + ", ".join(unknown))
    current = slice_dataset(dataset, start, end)
    previous = slice_dataset(dataset, previous_period.start, previous_period.end)

    def index(data):
        weeks: dict[date, list[DailyRow]] = {}
        for row in data.daily:
            weeks.setdefault(row.week_start, []).append(row)
        return weeks

    current_index, previous_index = index(current), index(previous)
    analyses = []
    for key in sorted(keys):
        variable = registry[key]
        points = make_series(current, variable, current_index)
        prior_points = make_series(previous, variable, previous_index)
        summary = summarize(variable, points, current_period)
        prior_summary = summarize(variable, prior_points, previous_period)
        analyses.append(VariableAnalysis(variable, summary, points, rolling(variable, points),
                                         compare(variable, summary, prior_summary),
                                         trend(variable, points, current_period)))
    return DescriptiveAnalytics("7B.1", dataset.contract_version, dataset.today,
                                current_period, previous_period, POLICY, tuple(analyses))
