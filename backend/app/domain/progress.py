"""Read-only schedule evaluation. No ORM, wall clock, or persisted counters.

Daily obligations use each day's version. A flexible weekly component uses the
first weekly-scheduled day's version in that Mon–Sun week (full quota, no
proration). Only weekly-scheduled dates feed that component; daily dates feed
their own obligations. Thus schedule changes never double-count a completion.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.domain.schedule import Schedule, ScheduleType

ProgressStatus = Literal["satisfied", "pending", "failed"]
DAY = timedelta(days=1)


def week_bounds(on: date) -> tuple[date, date]:
    """Calendar Monday–Sunday, also safe at Python's maximum supported date."""
    start = on - timedelta(days=on.weekday())
    return start, date.fromordinal(min(start.toordinal() + 6, date.max.toordinal()))


@dataclass(frozen=True)
class Version:
    effective_from: date
    name: str
    weight: int
    schedule: Schedule


@dataclass(frozen=True)
class HabitHistory:
    habit_id: int
    versions: tuple[Version, ...]
    entries: dict[date, str]
    # Exclusive local calendar cutoff. None means active, not an inferred date.
    archived_on: date | None = None

    def version_on(self, on: date) -> Version | None:
        return next((v for v in reversed(self.versions) if v.effective_from <= on), None)

    def active_on(self, on: date) -> bool:
        return self.archived_on is None or on < self.archived_on


@dataclass(frozen=True)
class Score:
    completed_weight: int
    required_weight: int

    @property
    def score(self) -> float | None:
        if self.required_weight == 0:
            return None
        return self.completed_weight / self.required_weight * 100


@dataclass(frozen=True)
class Obligation:
    habit_id: int
    name: str
    weight: int
    entry_status: str | None
    satisfied: bool


@dataclass(frozen=True)
class DayProgress(Score):
    entry_date: date
    obligations: tuple[Obligation, ...]


@dataclass(frozen=True)
class WeekHabitProgress(Score):
    habit_id: int
    name: str
    quota: int
    completed_count: int
    daily_required_count: int
    daily_completed_count: int
    weekly_quota: int
    weekly_completed_count: int
    weekly_weight: int | None
    weekly_effective_from: date | None
    preferred_weekdays: tuple[int, ...]
    status: ProgressStatus


@dataclass(frozen=True)
class WeekProgress(Score):
    week_start: date
    week_end: date
    habits: tuple[WeekHabitProgress, ...]


@dataclass(frozen=True)
class Streak:
    habit_id: int
    current_streak: int
    unit: Literal["days", "weeks"]
    as_of: date


def day_progress(histories: tuple[HabitHistory, ...], on: date) -> DayProgress:
    obligations: list[Obligation] = []
    for habit in histories:
        version = habit.version_on(on)
        if (
            not habit.active_on(on)
            or version is None
            or version.schedule.type != ScheduleType.DAILY
        ):
            continue
        status = habit.entries.get(on)
        obligations.append(Obligation(
            habit_id=habit.habit_id, name=version.name, weight=version.weight,
            entry_status=status, satisfied=status == "done",
        ))
    return DayProgress(
        completed_weight=sum(o.weight for o in obligations if o.satisfied),
        required_weight=sum(o.weight for o in obligations),
        entry_date=on, obligations=tuple(obligations),
    )


def week_habit_progress(
    habit: HabitHistory, on: date, today: date,
) -> WeekHabitProgress | None:
    start, end = week_bounds(on)
    daily_required = daily_done = required = completed = weekly_done = 0
    anchor: Version | None = None
    last: Version | None = None
    for ordinal in range(start.toordinal(), end.toordinal() + 1):
        day = date.fromordinal(ordinal)
        version = habit.version_on(day)
        if version is None or not habit.active_on(day):
            continue
        last = version
        done = habit.entries.get(day) == "done" and day <= today
        if version.schedule.type == ScheduleType.DAILY:
            daily_required += 1
            daily_done += int(done)
            required += version.weight
            completed += version.weight if done else 0
        else:
            anchor = anchor or version
            weekly_done += int(done)
    if last is None:
        return None
    quota = anchor.schedule.weekly_required_count if anchor else 0
    if anchor:
        required += quota * anchor.weight
        completed += min(quota, weekly_done) * anchor.weight
    satisfied = daily_done == daily_required and weekly_done >= quota
    status: ProgressStatus = (
        "satisfied" if satisfied else ("failed" if end < today else "pending")
    )
    return WeekHabitProgress(
        completed_weight=completed, required_weight=required,
        habit_id=habit.habit_id, name=last.name,
        quota=daily_required + quota, completed_count=daily_done + weekly_done,
        daily_required_count=daily_required, daily_completed_count=daily_done,
        weekly_quota=quota, weekly_completed_count=weekly_done,
        weekly_weight=anchor.weight if anchor else None,
        weekly_effective_from=anchor.effective_from if anchor else None,
        preferred_weekdays=anchor.schedule.weekdays if anchor else (),
        status=status,
    )


def week_progress(
    histories: tuple[HabitHistory, ...], on: date, today: date,
) -> WeekProgress:
    start, end = week_bounds(on)
    habits = tuple(
        p for h in histories
        if (p := week_habit_progress(h, on, today)) is not None
    )
    return WeekProgress(
        completed_weight=sum(p.completed_weight for p in habits),
        required_weight=sum(p.required_weight for p in habits),
        week_start=start, week_end=end, habits=habits,
    )


@dataclass(frozen=True)
class StreakSummary:
    """Current streak plus the best run that ended before it.

    ``previous_best_streak`` is the longest run that had already ended when the
    current run began. It is what lets a caller say "this is a new personal
    record" without keeping a second, parallel streak algorithm. Stage 9 (Owl)
    reads it; every other stage keeps using :func:`current_streak`.
    """

    habit_id: int
    current_streak: int
    previous_best_streak: int
    previous_best_end: date | None
    unit: Literal["days", "weeks"]
    as_of: date
    active: bool


def streak_summary(habit: HabitHistory, today: date) -> StreakSummary:
    """One forward pass over the authoritative history: current and best streaks.

    Deterministic and pure: no wall clock, no stored counters. The scan mirrors
    :func:`current_streak` semantics (today's incomplete day preserves
    yesterday's run; an archived period is frozen at its last active date) while
    additionally tracking the longest run that ended before the current one.
    """

    # Freeze at the last active date. An archived daily period is closed;
    # a started weekly quota still resolves at its calendar Sunday boundary.
    as_of = today
    if habit.archived_on and habit.archived_on > date.min:
        as_of = min(today, habit.archived_on - DAY)
    version = habit.version_on(as_of)
    unit: Literal["days", "weeks"] = (
        "days" if version is None or version.schedule.type == ScheduleType.DAILY
        else "weeks"
    )
    active = version is not None and habit.active_on(as_of)
    if not active:
        return StreakSummary(habit.habit_id, 0, 0, None, unit, as_of, active=False)

    first = habit.versions[0].effective_from
    run = 0
    run_end: date | None = None
    best = 0
    best_end: date | None = None

    if unit == "days":
        cursor = first
        while cursor <= as_of:
            # Today's unfinished day neither adds a day nor breaks the run; it
            # is simply skipped, exactly like the backward scan.
            if cursor == today and habit.entries.get(cursor) != "done":
                cursor += DAY
                continue
            config = habit.version_on(cursor)
            is_daily = config is not None and config.schedule.type == ScheduleType.DAILY
            if is_daily and habit.entries.get(cursor) == "done":
                run += 1
                run_end = cursor
            else:
                if run > best:
                    best, best_end = run, run_end
                run, run_end = 0, None
            if cursor == date.max:
                break
            cursor += DAY
    else:
        cursor, _ = week_bounds(first)
        last_week, _ = week_bounds(as_of)
        current_week, _ = week_bounds(today)
        while cursor <= last_week:
            progress = week_habit_progress(habit, cursor, today)
            if progress is None or progress.weekly_quota == 0:
                if run > best:
                    best, best_end = run, run_end
                run, run_end = 0, None
            elif progress.weekly_completed_count >= progress.weekly_quota:
                run += 1
                run_end = cursor
            elif cursor != current_week:
                # A completed week below quota closes the run; the current,
                # still-open week does not.
                if run > best:
                    best, best_end = run, run_end
                run, run_end = 0, None
            if cursor >= last_week:
                break
            cursor += timedelta(days=7)

    return StreakSummary(habit.habit_id, run, best, best_end, unit, as_of, active=True)


def current_streak(habit: HabitHistory, today: date) -> Streak:
    summary = streak_summary(habit, today)
    return Streak(habit.habit_id, summary.current_streak, summary.unit, summary.as_of)
