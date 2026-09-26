"""Stage 11 records: deterministic personal bests over the authoritative history.

Everything here is *derived* from data that already exists — habit versions and
daily entries (the Stage 4 histories), Daily State dates, completed experiments
and insight snapshots. There is no ``records`` table and no mutable counter: a
record is a pure function of the current history, so removing the underlying data
can legitimately change it.

Two ideas are kept apart:

* a **record** is a dynamic maximum that can be beaten (longest streak, best day,
  best week, most habits done in a day, best month per habit);
* an **achievement** (see :mod:`app.domain.achievements`) is a milestone that,
  once reached, stays reached.

Purity is deliberate: no database, no wall clock. ``today`` is passed in, and
``missing`` is never treated as failure — a day with no record simply does not
add to a streak, exactly like the canonical Stage 4 rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.domain.progress import (
    DAY,
    DailySpan,
    HabitHistory,
    day_progress,
    daily_runs,
    daily_streak_milestones,
    streak_as_of,
    streak_summary,
    week_bounds,
    week_progress,
)

RecordUnit = Literal["days", "weeks"]

# Product floors, not statistics. They stop a single recorded day becoming a
# "best week" and a two-day month becoming a "100% month".
MIN_WEEK_OBSERVED_DAYS = 4
MIN_WEEK_COVERAGE = 0.60
MIN_MONTH_OBLIGATION_DAYS = 10

# The streak lengths the achievement catalogue cares about.
STREAK_TARGETS: tuple[int, ...] = (7, 30, 100)


@dataclass(frozen=True)
class LongestStreak:
    """The single longest habit streak ever recorded (days or weeks)."""

    habit_id: int
    name: str
    unit: RecordUnit
    current_streak: int
    best_streak: int
    best_start: date | None
    best_end: date | None
    archived: bool


@dataclass(frozen=True)
class ScoreDay:
    """The best canonical daily progress, earliest day wins a tie."""

    day: date
    score: float
    completed_weight: int
    required_weight: int
    ties: int


@dataclass(frozen=True)
class ScoreWeek:
    """The best completed calendar week that met the coverage floor."""

    week_start: date
    week_end: date
    score: float
    coverage: float | None
    observed_days: int
    obligation_days: int
    ties: int


@dataclass(frozen=True)
class MostCompleted:
    """The day with the most satisfied obligations (unweighted count)."""

    day: date
    completed_count: int
    required_count: int
    ties: int


@dataclass(frozen=True)
class ConsistencyBest:
    """One habit's best fully elapsed calendar month by daily completion rate."""

    habit_id: int
    name: str
    archived: bool
    period_start: date
    period_end: date
    done_days: int
    obligation_days: int
    ratio: float


@dataclass(frozen=True)
class HistoryFacts:
    """Everything the achievement catalogue needs that comes from habit history.

    Computed in the same pass as the records, so no second scan is required.
    """

    completions_by_habit: Mapping[int, tuple[date, ...]]
    streak_milestones: Mapping[int, date]
    perfect_day_on: date | None
    perfect_week_on: date | None
    tracked_days: tuple[date, ...]
    longest_daily_run: int


@dataclass(frozen=True)
class RecordsSummary:
    first_tracked_day: date | None
    tracked_days: int
    habit_completions: int
    experiments_created: int
    completed_experiments: int
    stable_insight_on: date | None
    well_supported_insight_on: date | None


@dataclass(frozen=True)
class RecordsBundle:
    summary: RecordsSummary
    longest_streak: LongestStreak | None
    best_day: ScoreDay | None
    best_week: ScoreWeek | None
    most_completed: MostCompleted | None
    consistency: tuple[ConsistencyBest, ...]
    facts: HistoryFacts


def _configured(habit: HabitHistory, day: date) -> bool:
    """True when the habit had an active configuration on ``day``."""

    return habit.active_on(day) and habit.version_on(day) is not None


def _done_dates(habit: HabitHistory, today: date) -> tuple[date, ...]:
    """Recorded ``done`` dates on a configured, active day, oldest first."""

    return tuple(sorted(
        day for day, status in habit.entries.items()
        if status == "done" and day <= today and _configured(habit, day)
    ))


def _tracked_dates(
    histories: tuple[HabitHistory, ...], state_days: Iterable[date], today: date,
) -> tuple[date, ...]:
    """Days with a real record: any habit entry (even a skip) or a Daily State.

    A day with nothing recorded is simply absent — never inferred as a failure.
    """

    days: set[date] = {day for day in state_days if day <= today}
    for habit in histories:
        days.update(day for day in habit.entries if day <= today)
    return tuple(sorted(days))


def _longest_streak(
    histories: tuple[HabitHistory, ...], today: date,
) -> LongestStreak | None:
    """The habit with the longest all-time streak, days or weeks."""

    best: LongestStreak | None = None
    for habit in histories:
        if not habit.versions:
            continue
        summary = streak_summary(habit, today)
        if not summary.active:
            continue
        name = habit.versions[-1].name
        archived = habit.archived_on is not None
        if summary.unit == "days":
            spans = daily_runs(habit, today)
            if not spans:
                continue
            longest: DailySpan = max(spans, key=lambda span: span.length)
            candidate = LongestStreak(
                habit_id=habit.habit_id, name=name, unit="days",
                current_streak=summary.current_streak, best_streak=longest.length,
                best_start=longest.start, best_end=longest.end, archived=archived,
            )
        else:
            best_len = max(summary.previous_best_streak, summary.current_streak)
            if best_len == 0:
                continue
            if summary.current_streak > summary.previous_best_streak:
                end = summary.as_of
                start = end - timedelta(days=7 * (best_len - 1))
            else:
                end = summary.previous_best_end
                start = week_bounds(end)[0] if end is not None else None
            candidate = LongestStreak(
                habit_id=habit.habit_id, name=name, unit="weeks",
                current_streak=summary.current_streak, best_streak=best_len,
                best_start=start, best_end=end, archived=archived,
            )
        if best is None or (
            candidate.best_streak, candidate.current_streak, -candidate.habit_id
        ) > (best.best_streak, best.current_streak, -best.habit_id):
            best = candidate
    return best


def _consistency(
    histories: tuple[HabitHistory, ...], today: date,
) -> tuple[ConsistencyBest, ...]:
    """Each habit's best fully elapsed month of daily obligations.

    Only daily-scheduled days form the denominator, and only months with at least
    :data:`MIN_MONTH_OBLIGATION_DAYS` such days can win. Weekly-quota habits are
    represented by their streak instead.
    """

    results: list[ConsistencyBest] = []
    for habit in histories:
        if not habit.versions:
            continue
        name = habit.versions[-1].name
        archived = habit.archived_on is not None
        by_month: dict[tuple[int, int], list[int]] = {}
        as_of = streak_as_of(habit, today)
        first = habit.versions[0].effective_from
        cursor = first
        while cursor <= as_of:
            if _configured(habit, cursor):
                bucket = by_month.setdefault((cursor.year, cursor.month), [0, 0])
                bucket[1] += 1
                if habit.entries.get(cursor) == "done":
                    bucket[0] += 1
            if cursor == date.max:
                break
            cursor += DAY
        best: ConsistencyBest | None = None
        for (year, month), (done, obligation) in by_month.items():
            if obligation < MIN_MONTH_OBLIGATION_DAYS:
                continue
            period_start = date(year, month, 1)
            next_month = date(year + (month // 12), (month % 12) + 1, 1)
            period_end = next_month - DAY
            # A month is comparable only once it is fully over.
            if period_end >= today:
                continue
            ratio = done / obligation * 100
            candidate = ConsistencyBest(
                habit_id=habit.habit_id, name=name, archived=archived,
                period_start=period_start, period_end=period_end,
                done_days=done, obligation_days=obligation, ratio=ratio,
            )
            if best is None or (candidate.ratio, candidate.period_start) > (
                best.ratio, best.period_start
            ):
                best = candidate
        if best is not None:
            results.append(best)
    return tuple(sorted(
        results, key=lambda item: (-item.ratio, -item.obligation_days, item.habit_id)
    ))


def compute_records(
    histories: tuple[HabitHistory, ...],
    *,
    today: date,
    state_days: Sequence[date] = (),
    experiments_created: int = 0,
    completed_experiments: int = 0,
    stable_insight_on: date | None = None,
    well_supported_insight_on: date | None = None,
) -> RecordsBundle:
    """Compute every record, summary number and history fact in one bounded pass.

    The day scan walks ``[first configuration, today]`` once; weeks and months are
    derived from that same range. Nothing is loaded here — the service supplies
    already-batched histories and dates.
    """

    tracked = _tracked_dates(histories, state_days, today)
    completions_by_habit = {habit.habit_id: _done_dates(habit, today) for habit in histories}
    habit_completions = sum(len(days) for days in completions_by_habit.values())

    streak_milestones: dict[int, date] = {}
    longest_daily_run = 0
    for habit in histories:
        for span in daily_runs(habit, today):
            longest_daily_run = max(longest_daily_run, span.length)
        for target, on in daily_streak_milestones(habit, STREAK_TARGETS, today).items():
            current = streak_milestones.get(target)
            if current is None or on < current:
                streak_milestones[target] = on

    first = _scan_start(histories)
    best_day: ScoreDay | None = None
    best_week: ScoreWeek | None = None
    most_completed: MostCompleted | None = None
    perfect_day_on: date | None = None
    perfect_week_on: date | None = None
    week_observed: dict[date, list[int]] = {}

    if first is not None:
        cursor = first
        while cursor <= today:
            progress = day_progress(histories, cursor)
            obligations = progress.obligations
            completed_count = sum(1 for obligation in obligations if obligation.satisfied)
            if obligations:
                if most_completed is None or completed_count > most_completed.completed_count:
                    most_completed = MostCompleted(
                        day=cursor, completed_count=completed_count,
                        required_count=len(obligations), ties=1,
                    )
                elif completed_count == most_completed.completed_count:
                    most_completed = MostCompleted(
                        most_completed.day, most_completed.completed_count,
                        most_completed.required_count, most_completed.ties + 1,
                    )
                week_start, _ = week_bounds(cursor)
                bucket = week_observed.setdefault(week_start, [0, 0])
                bucket[1] += 1
                if any(obligation.entry_status is not None for obligation in obligations):
                    bucket[0] += 1
            if progress.required_weight > 0 and progress.score is not None:
                if best_day is None or progress.score > best_day.score:
                    best_day = ScoreDay(
                        day=cursor, score=progress.score,
                        completed_weight=progress.completed_weight,
                        required_weight=progress.required_weight, ties=1,
                    )
                elif progress.score == best_day.score:
                    best_day = ScoreDay(
                        best_day.day, best_day.score, best_day.completed_weight,
                        best_day.required_weight, best_day.ties + 1,
                    )
                if (
                    perfect_day_on is None
                    and progress.completed_weight >= progress.required_weight
                ):
                    perfect_day_on = cursor
            if cursor == date.max:
                break
            cursor += DAY

        # Weeks are derived from the same range, from the first full week onward.
        week_start, _ = week_bounds(first)
        while week_start <= today:
            _start, window_end = week_bounds(week_start)
            observed, obligation_days = week_observed.get(week_start, [0, 0])
            if window_end < today and obligation_days > 0:
                progress = week_progress(histories, week_start, today)
                coverage = observed / obligation_days if obligation_days else None
                if (
                    progress.score is not None
                    and observed >= MIN_WEEK_OBSERVED_DAYS
                    and (coverage or 0.0) >= MIN_WEEK_COVERAGE
                ):
                    if best_week is None or progress.score > best_week.score:
                        best_week = ScoreWeek(
                            week_start=week_start, week_end=window_end,
                            score=progress.score, coverage=coverage,
                            observed_days=observed, obligation_days=obligation_days, ties=1,
                        )
                    elif progress.score == best_week.score:
                        best_week = ScoreWeek(
                            best_week.week_start, best_week.week_end, best_week.score,
                            best_week.coverage, best_week.observed_days,
                            best_week.obligation_days, best_week.ties + 1,
                        )
                    if perfect_week_on is None and progress.score >= 100:
                        perfect_week_on = week_start
            if week_start == date.max:
                break
            week_start += timedelta(days=7)

    facts = HistoryFacts(
        completions_by_habit=completions_by_habit,
        streak_milestones=streak_milestones,
        perfect_day_on=perfect_day_on,
        perfect_week_on=perfect_week_on,
        tracked_days=tracked,
        longest_daily_run=longest_daily_run,
    )
    summary = RecordsSummary(
        first_tracked_day=tracked[0] if tracked else None,
        tracked_days=len(tracked),
        habit_completions=habit_completions,
        experiments_created=experiments_created,
        completed_experiments=completed_experiments,
        stable_insight_on=stable_insight_on,
        well_supported_insight_on=well_supported_insight_on,
    )
    return RecordsBundle(
        summary=summary,
        longest_streak=_longest_streak(histories, today),
        best_day=best_day,
        best_week=best_week,
        most_completed=most_completed,
        consistency=_consistency(histories, today),
        facts=facts,
    )


def _scan_start(histories: tuple[HabitHistory, ...]) -> date | None:
    """The earliest day a configuration existed, or ``None`` when there is none."""

    starts = [habit.versions[0].effective_from for habit in histories if habit.versions]
    return min(starts) if starts else None
