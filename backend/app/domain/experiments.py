"""Stage 10 experiments: pure lifecycle, comparable windows and descriptive analysis.

An experiment is a bounded window the user defines. Nothing here proves
causation: the analysis only *describes* how already-existing Tracker data
differed before, during and after the window. It never recomputes a habit score,
streak or state metric — it aggregates the canonical Stage 7A dataset (which
itself reuses Stage 4 progress and Stage 7 state conventions).

Purity is deliberate: no database, no wall clock, no randomness. "Today" and the
cancellation date are passed in explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.domain.analytics.types import AnalyticsDataset, Availability as A
from app.domain.analytics.variables import STATE_FIELDS
from app.domain.analytics.types import VariableType as T
from app.domain.errors import InvalidExperimentError

ExperimentStatus = Literal["scheduled", "active", "completed", "cancelled"]
WindowKey = Literal["before", "during", "after"]

TITLE_MAX_LENGTH = 120
TEXT_MAX_LENGTH = 2000
MIN_DURATION_DAYS = 1
MAX_DURATION_DAYS = 366

# Coverage thresholds for a *comparable* period. Deliberately conservative: the
# UI must say "недостаточно данных" rather than imply a confident difference.
MIN_COVERAGE = 0.60
MIN_OBSERVED_DAYS = 3

_DAY = timedelta(days=1)


# --------------------------------------------------------------------------- #
# Validation helpers (single source of truth for what an experiment is)
# --------------------------------------------------------------------------- #


def normalise_title(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise InvalidExperimentError(details={"field": "title"})
    if len(text) > TITLE_MAX_LENGTH:
        raise InvalidExperimentError(details={"field": "title"})
    return text


def normalise_text(value: str, *, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise InvalidExperimentError(details={"field": field})
    if len(text) > TEXT_MAX_LENGTH:
        raise InvalidExperimentError(details={"field": field})
    return text


def validate_window(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise InvalidExperimentError(details={"field": "date_order"})
    length = (end_date - start_date).days + 1
    if length < MIN_DURATION_DAYS or length > MAX_DURATION_DAYS:
        raise InvalidExperimentError(details={"field": "duration"})


# --------------------------------------------------------------------------- #
# Lifecycle and windows
# --------------------------------------------------------------------------- #


def _shift(day: date, days: int) -> date:
    ordinal = max(date.min.toordinal(), min(date.max.toordinal(), day.toordinal() + days))
    return date.fromordinal(ordinal)


def effective_end(start_date: date, end_date: date, cancelled_on: date | None) -> date:
    """The last day the experiment actually ran.

    Cancelling never extends the planned window and never claims days that did not
    happen: the effective end is the cancellation date, or the planned end.
    """
    if cancelled_on is None:
        return end_date
    return min(end_date, cancelled_on)


def status_of(
    start_date: date, end_date: date, cancelled_on: date | None, today: date,
) -> ExperimentStatus:
    if cancelled_on is not None:
        return "cancelled"
    if today < start_date:
        return "scheduled"
    if today <= end_date:
        return "active"
    return "completed"


@dataclass(frozen=True)
class ExperimentWindow:
    key: WindowKey
    start: date
    end: date


def length_of(window: ExperimentWindow) -> int:
    return (window.end - window.start).days + 1 if window.end >= window.start else 0


@dataclass(frozen=True)
class ExperimentWindows:
    before: ExperimentWindow
    during: ExperimentWindow
    after: ExperimentWindow


def windows_for(
    start_date: date, end_date: date, *, cancelled_on: date | None = None,
) -> ExperimentWindows:
    """Comparable windows: same length, adjacent, never overlapping.

    A cancellation before the start yields empty windows — there is genuinely
    nothing to compare.
    """
    end = effective_end(start_date, end_date, cancelled_on)
    if end < start_date:
        empty_before = ExperimentWindow("before", start_date, _shift(start_date, -1))
        empty = ExperimentWindow("during", _shift(start_date, 1), start_date)
        return ExperimentWindows(empty_before, empty, ExperimentWindow("after", empty.start, empty.end))

    length = (end - start_date).days + 1
    return ExperimentWindows(
        before=ExperimentWindow("before", _shift(start_date, -length), _shift(start_date, -1)),
        during=ExperimentWindow("during", start_date, end),
        after=ExperimentWindow("after", _shift(end, 1), _shift(end, length)),
    )


@dataclass(frozen=True)
class ExperimentPhase:
    """Where the calendar sits relative to the experiment, for the list/detail UI."""

    status: ExperimentStatus
    stage: WindowKey
    day_index: int | None
    days_total: int | None
    days_until_start: int | None
    days_since_end: int | None
    after_collected_days: int
    after_total_days: int


def phase_for(
    start_date: date, end_date: date, cancelled_on: date | None, today: date,
) -> ExperimentPhase:
    windows = windows_for(start_date, end_date, cancelled_on=cancelled_on)
    status = status_of(start_date, end_date, cancelled_on, today)
    total = length_of(windows.during)
    if status == "scheduled":
        return ExperimentPhase(status, "before", None, total, (start_date - today).days,
                               None, 0, length_of(windows.after))
    if status == "active":
        return ExperimentPhase(status, "during", (today - start_date).days + 1, total, None,
                               None, 0, length_of(windows.after))
    # completed or cancelled: the experiment is over, the after window is filling.
    end = effective_end(start_date, end_date, cancelled_on)
    after_total = length_of(windows.after)
    elapsed = max(0, (today - end).days)
    collected = min(after_total, elapsed)
    return ExperimentPhase(status, "after", None, total, None, (today - end).days,
                           collected, after_total)


# --------------------------------------------------------------------------- #
# Descriptive analysis over the canonical dataset
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PeriodCoverage:
    calendar_days: int
    elapsed_days: int
    observed_days: int
    coverage: float | None


@dataclass(frozen=True)
class OverallPeriod:
    coverage: PeriodCoverage
    mean_score: float | None
    scored_days: int
    completed_weight: int
    required_weight: int


@dataclass(frozen=True)
class HabitPeriod:
    obligation_days: int
    observed_days: int
    done_days: int
    missed_days: int
    completion_ratio: float | None


@dataclass(frozen=True)
class HabitComparison:
    habit_id: int
    name: str
    before: HabitPeriod
    during: HabitPeriod
    after: HabitPeriod
    delta_during_vs_before: float | None


@dataclass(frozen=True)
class StatePeriod:
    observed_days: int
    value: float | None


@dataclass(frozen=True)
class StateComparison:
    key: str
    label: str
    kind: str
    before: StatePeriod
    during: StatePeriod
    after: StatePeriod
    delta_during_vs_before: float | None


@dataclass(frozen=True)
class OverallComparison:
    before: OverallPeriod
    during: OverallPeriod
    after: OverallPeriod
    delta_before_during: float | None
    delta_during_after: float | None
    delta_before_after: float | None


@dataclass(frozen=True)
class SeriesPoint:
    """One day of raw history. ``score``/``energy`` are ``None`` when unobserved."""

    date: date
    phase: WindowKey
    score: float | None
    energy: float | None


@dataclass(frozen=True)
class ExperimentAnalysis:
    windows: ExperimentWindows
    overall: OverallComparison
    habits: tuple[HabitComparison, ...]
    state: tuple[StateComparison, ...]
    series: tuple[SeriesPoint, ...]
    sufficient: bool
    summary: str


def _phase_of(day: date, windows: ExperimentWindows) -> WindowKey | None:
    for key, window in (("before", windows.before), ("during", windows.during),
                        ("after", windows.after)):
        if length_of(window) and window.start <= day <= window.end:
            return key
    return None


def _series(dataset: AnalyticsDataset, windows: ExperimentWindows) -> tuple[SeriesPoint, ...]:
    """Raw daily history across the three windows; gaps stay gaps, never zeros."""
    points: list[SeriesPoint] = []
    for row in dataset.daily:
        phase = _phase_of(row.date, windows)
        if phase is None:
            continue
        score_value = row.values.get("daily.score")
        energy_value = row.values.get("state.energy")
        points.append(SeriesPoint(
            date=row.date, phase=phase,
            score=(score_value.value if score_value is not None
                   and score_value.availability == A.PRESENT else None),
            energy=(energy_value.value if energy_value is not None
                    and energy_value.availability == A.PRESENT else None),
        ))
    return tuple(points)


def _rows_by_window(dataset: AnalyticsDataset, windows: ExperimentWindows) -> dict[WindowKey, list]:
    buckets: dict[WindowKey, list] = {"before": [], "during": [], "after": []}
    for row in dataset.daily:
        for key, window in (("before", windows.before), ("during", windows.during),
                            ("after", windows.after)):
            if length_of(window) and window.start <= row.date <= window.end:
                buckets[key].append(row)
                break
    return buckets


def _observed(row, habit_ids: tuple[int, ...]) -> bool:
    """A day counts as observed only when the user actually recorded something."""

    for habit_id in habit_ids:
        value = row.values.get(f"habit.{habit_id}.daily.completion")
        if value is not None and value.availability == A.PRESENT:
            return True
    for name, _label, _kind in STATE_FIELDS:
        value = row.values.get(f"state.{name}")
        if value is not None and value.availability == A.PRESENT:
            return True
    return False


def _coverage(window: ExperimentWindow, rows: list, today: date, habit_ids: tuple[int, ...]) -> PeriodCoverage:
    calendar = length_of(window)
    elapsed = sum(1 for row in rows if row.date <= today)
    observed = sum(1 for row in rows if row.date <= today and _observed(row, habit_ids))
    coverage = observed / calendar if calendar else None
    return PeriodCoverage(calendar, elapsed, observed, coverage)


def _overall(window: ExperimentWindow, rows: list, today: date,
             habit_ids: tuple[int, ...]) -> OverallPeriod:
    coverage = _coverage(window, rows, today, habit_ids)
    past = [row for row in rows if row.date <= today]
    scores = [row.values["daily.score"].value for row in past
              if row.values["daily.score"].availability == A.PRESENT]
    done = sum(int(row.values["daily.completed_weight"].value or 0) for row in past
               if row.values["daily.completed_weight"].availability == A.PRESENT)
    required = sum(int(row.values["daily.required_weight"].value or 0) for row in past
                   if row.values["daily.required_weight"].availability == A.PRESENT)
    return OverallPeriod(
        coverage=coverage,
        mean_score=(sum(scores) / len(scores)) if scores else None,
        scored_days=len(scores),
        completed_weight=done,
        required_weight=required,
    )


def _habit_period(window: ExperimentWindow, rows: list, today: date, habit_id: int) -> HabitPeriod:
    obligation = observed = done = missed = 0
    for row in rows:
        if row.date > today:
            continue
        required = row.values.get(f"habit.{habit_id}.daily.required_weight")
        if required is not None and required.availability == A.PRESENT:
            obligation += 1
        completion = row.values.get(f"habit.{habit_id}.daily.completion")
        if completion is not None and completion.availability == A.PRESENT:
            observed += 1
            if completion.value is True:
                done += 1
            else:
                missed += 1
    ratio = (done / obligation * 100) if obligation else None
    return HabitPeriod(obligation, observed, done, missed, ratio)


def _habit_comparisons(dataset, windows, buckets, today, habit_names: Mapping[int, str]):
    habit_ids = sorted({v.habit_id for v in dataset.variables if v.habit_id is not None})
    results: list[HabitComparison] = []
    for habit_id in habit_ids:
        before = _habit_period(windows.before, buckets["before"], today, habit_id)
        during = _habit_period(windows.during, buckets["during"], today, habit_id)
        after = _habit_period(windows.after, buckets["after"], today, habit_id)
        if not (before.obligation_days or during.obligation_days or after.obligation_days):
            continue
        delta = (during.completion_ratio - before.completion_ratio
                 if during.completion_ratio is not None and before.completion_ratio is not None
                 else None)
        results.append(HabitComparison(habit_id, habit_names.get(habit_id, f"Привычка #{habit_id}"),
                                       before, during, after, delta))
    return tuple(results)


def _state_period(window: ExperimentWindow, rows: list, today: date, name: str,
                  kind: T) -> StatePeriod:
    values = [row.values[f"state.{name}"].value for row in rows
              if row.date <= today and row.values[f"state.{name}"].availability == A.PRESENT]
    if not values:
        return StatePeriod(0, None)
    if kind == T.BOOLEAN:
        return StatePeriod(len(values), sum(1 for value in values if value) / len(values))
    return StatePeriod(len(values), sum(values) / len(values))


def _state_comparisons(windows, buckets, today):
    results: list[StateComparison] = []
    for name, label, kind in STATE_FIELDS:
        if kind not in (T.NUMERIC, T.ORDINAL, T.BOOLEAN):
            continue
        before = _state_period(windows.before, buckets["before"], today, name, kind)
        during = _state_period(windows.during, buckets["during"], today, name, kind)
        after = _state_period(windows.after, buckets["after"], today, name, kind)
        if before.observed_days == 0 and during.observed_days == 0 and after.observed_days == 0:
            continue
        delta = (during.value - before.value
                 if during.value is not None and before.value is not None else None)
        results.append(StateComparison(f"state.{name}", label, kind.value, before, during, after,
                                       delta))
    return tuple(results)


def _is_sufficient(before: OverallPeriod, during: OverallPeriod) -> bool:
    def ready(period: OverallPeriod) -> bool:
        return (period.coverage.calendar_days > 0
                and period.coverage.observed_days >= MIN_OBSERVED_DAYS
                and (period.coverage.coverage or 0.0) >= MIN_COVERAGE)
    return ready(before) and ready(during)


def _describe(overall: OverallComparison, after: OverallPeriod, *, sufficient: bool) -> str:
    """Deterministic, non-causal Russian summary."""
    if not sufficient:
        return ("Пока недостаточно данных для уверенного сравнения: отмеченных дней "
                "меньше, чем нужно для сопоставимых периодов.")
    before, during = overall.before.mean_score, overall.during.mean_score
    if before is None or during is None:
        return "Сравнение по общему прогрессу недоступно: не хватает оценки дней."
    delta = during - before
    if abs(delta) < 1:
        phrase = "примерно на том же уровне"
    else:
        direction = "выше" if delta > 0 else "ниже"
        phrase = f"{direction} примерно на {abs(delta):.0f} п.п."
    text = (f"Во время эксперимента средний дневной прогресс был {phrase}, "
            f"чем за предыдущий сопоставимый период.")
    if after.coverage.calendar_days and after.coverage.observed_days < after.coverage.calendar_days:
        text += (f" Данных после эксперимента пока: {after.coverage.observed_days} "
                 f"из {after.coverage.calendar_days} дней.")
    return text


def analyze(
    dataset: AnalyticsDataset,
    windows: ExperimentWindows,
    *,
    today: date,
    habit_names: Mapping[int, str] | None = None,
) -> ExperimentAnalysis:
    """Aggregate the already-built dataset over the three comparable windows."""

    habit_names = habit_names or {}
    habit_ids = tuple(sorted({v.habit_id for v in dataset.variables if v.habit_id is not None}))
    buckets = _rows_by_window(dataset, windows)
    before = _overall(windows.before, buckets["before"], today, habit_ids)
    during = _overall(windows.during, buckets["during"], today, habit_ids)
    after = _overall(windows.after, buckets["after"], today, habit_ids)

    def delta(first: OverallPeriod, second: OverallPeriod) -> float | None:
        if first.mean_score is None or second.mean_score is None:
            return None
        return second.mean_score - first.mean_score

    overall = OverallComparison(
        before=before, during=during, after=after,
        delta_before_during=delta(before, during),
        delta_during_after=delta(during, after),
        delta_before_after=delta(before, after),
    )
    sufficient = _is_sufficient(before, during)
    return ExperimentAnalysis(
        windows=windows,
        overall=overall,
        habits=_habit_comparisons(dataset, windows, buckets, today, habit_names),
        state=_state_comparisons(windows, buckets, today),
        series=_series(dataset, windows),
        sufficient=sufficient,
        summary=_describe(overall, after, sufficient=sufficient),
    )


__all__ = [
    "ExperimentAnalysis",
    "ExperimentPhase",
    "ExperimentStatus",
    "ExperimentWindow",
    "ExperimentWindows",
    "OverallComparison",
    "SeriesPoint",
    "analyze",
    "effective_end",
    "length_of",
    "normalise_text",
    "normalise_title",
    "phase_for",
    "status_of",
    "validate_window",
    "windows_for",
]
