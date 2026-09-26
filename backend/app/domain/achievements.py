"""Stage 11 achievements: a small, static catalogue of real milestones.

Achievements are **not** stored. Each one is evaluated against the same
derived facts the records use (see :mod:`app.domain.records` plus experiment and
insight history), so there is no achievement table and no badge to "unlock" in the
database. Deleting the underlying history can legitimately un-earn a milestone,
which is the honest behaviour for a single-user local app.

The catalogue is deliberately short. There is no XP, no levels, no currency and no
reward for merely opening the app: every entry marks something the user actually
did. Wording is plain Russian — no congratulation boilerplate.

Purity is deliberate: ``today`` is passed in and used only to decide what counts
as "recent"; a historical ``achieved_on`` is the real date the milestone was
first reached, never today's date.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

AchievementCategory = Literal[
    "streak", "consistency", "tracking", "daily_state", "experiments", "insights"
]

# How long an achievement still counts as "recently achieved" (days). Policy.
RECENT_ACHIEVEMENT_DAYS = 7


@dataclass(frozen=True)
class Achievement:
    """One catalogue entry, evaluated against the current history."""

    key: str
    title: str
    description: str
    category: AchievementCategory
    achieved: bool
    achieved_on: date | None
    current: int
    target: int


@dataclass(frozen=True)
class AchievementMetrics:
    """Everything the catalogue may look at, all derived upstream."""

    completions_by_habit: Mapping[int, tuple[date, ...]]
    streak_milestones: Mapping[int, date]
    longest_daily_run: int
    perfect_day_on: date | None
    perfect_week_on: date | None
    tracked_days: tuple[date, ...]
    state_days: tuple[date, ...]
    experiments_created_on: tuple[date, ...]
    experiments_completed_on: tuple[date, ...]
    stable_insight_on: date | None
    well_supported_insight_on: date | None


@dataclass(frozen=True)
class _Definition:
    key: str
    title: str
    description: str
    category: AchievementCategory
    target: int
    # ``(current, achieved_on)``: the live progress value and the real date the
    # milestone was first reached (``None`` when it has not been, or when no
    # historical date can be reconstructed).
    read: Callable[[AchievementMetrics], tuple[int, date | None]]


def _all_completions(metrics: AchievementMetrics) -> tuple[date, ...]:
    return tuple(sorted(
        day for days in metrics.completions_by_habit.values() for day in days
    ))


def _best_habit_completions(metrics: AchievementMetrics, target: int) -> tuple[int, date | None]:
    """The habit with the most completions, and the date it reached ``target``."""

    counts = {habit_id: len(days) for habit_id, days in metrics.completions_by_habit.items()}
    current = max(counts.values(), default=0)
    reached = [
        days[target - 1]
        for days in metrics.completions_by_habit.values()
        if len(days) >= target
    ]
    return current, (min(reached) if reached else None)


def _nth(days: tuple[date, ...], target: int) -> date | None:
    return days[target - 1] if len(days) >= target else None


def _bool_metric(on: date | None) -> tuple[int, date | None]:
    return (1 if on is not None else 0), on


def _catalogue() -> tuple[_Definition, ...]:
    """The static, ordered catalogue. Order is the stable fallback tie-break."""

    def completions_total(metrics: AchievementMetrics) -> tuple[int, date | None]:
        days = _all_completions(metrics)
        return len(days), (days[0] if days else None)

    def streak(target: int):
        def read(metrics: AchievementMetrics) -> tuple[int, date | None]:
            return metrics.longest_daily_run, metrics.streak_milestones.get(target)
        return read

    def habit_count(target: int):
        def read(metrics: AchievementMetrics) -> tuple[int, date | None]:
            return _best_habit_completions(metrics, target)
        return read

    def tracked(target: int):
        def read(metrics: AchievementMetrics) -> tuple[int, date | None]:
            return len(metrics.tracked_days), _nth(metrics.tracked_days, target)
        return read

    def state(target: int):
        def read(metrics: AchievementMetrics) -> tuple[int, date | None]:
            return len(metrics.state_days), _nth(metrics.state_days, target)
        return read

    def created(metrics: AchievementMetrics) -> tuple[int, date | None]:
        return len(metrics.experiments_created_on), (
            metrics.experiments_created_on[0] if metrics.experiments_created_on else None
        )

    def completed(target: int):
        def read(metrics: AchievementMetrics) -> tuple[int, date | None]:
            return len(metrics.experiments_completed_on), _nth(
                metrics.experiments_completed_on, target
            )
        return read

    return (
        _Definition(
            "first_habit_completion", "Первое выполнение",
            "Первая привычка отмечена выполненной.", "consistency", 1, completions_total),
        _Definition(
            "streak_7", "Серия 7 дней",
            "Одна привычка держалась 7 дней подряд.", "streak", 7, streak(7)),
        _Definition(
            "streak_30", "Месяц без отрыва",
            "Одна привычка держалась 30 дней подряд.", "streak", 30, streak(30)),
        _Definition(
            "streak_100", "Сто дней подряд",
            "Одна привычка держалась 100 дней подряд.", "streak", 100, streak(100)),
        _Definition(
            "habit_50_completions", "50 выполнений",
            "Одна привычка выполнена 50 раз.", "consistency", 50, habit_count(50)),
        _Definition(
            "habit_100_completions", "100 выполнений",
            "Одна привычка выполнена 100 раз.", "consistency", 100, habit_count(100)),
        _Definition(
            "first_perfect_day", "Идеальный день",
            "Первый день, где выполнены все обязательные привычки.",
            "consistency", 1, lambda m: _bool_metric(m.perfect_day_on)),
        _Definition(
            "perfect_week", "Идеальная неделя",
            "Полная неделя со 100% и достаточным покрытием.",
            "consistency", 1, lambda m: _bool_metric(m.perfect_week_on)),
        _Definition(
            "tracked_30_days", "30 дней трекинга",
            "Записи есть за 30 разных дней.", "tracking", 30, tracked(30)),
        _Definition(
            "tracked_100_days", "100 дней трекинга",
            "Записи есть за 100 разных дней.", "tracking", 100, tracked(100)),
        _Definition(
            "daily_state_30", "30 дней состояния",
            "Состояние дня заполнено в 30 разных днях.", "daily_state", 30, state(30)),
        _Definition(
            "daily_state_100", "100 дней состояния",
            "Состояние дня заполнено в 100 разных днях.", "daily_state", 100, state(100)),
        _Definition(
            "first_experiment", "Первый эксперимент",
            "Создан первый личный эксперимент.", "experiments", 1, created),
        _Definition(
            "first_completed_experiment", "Первый завершённый эксперимент",
            "Первый эксперимент дошёл до конца.", "experiments", 1, completed(1)),
        _Definition(
            "experiments_5", "Пять экспериментов",
            "Завершено пять экспериментов.", "experiments", 5, completed(5)),
        _Definition(
            "first_stable_insight", "Первый устойчивый инсайт",
            "Появилась первая устойчивая связь.", "insights", 1,
            lambda m: _bool_metric(m.stable_insight_on)),
        _Definition(
            "first_well_supported_insight", "Первый подтверждённый инсайт",
            "Появилась первая хорошо подтверждённая связь.", "insights", 1,
            lambda m: _bool_metric(m.well_supported_insight_on)),
    )


def evaluate_achievements(
    metrics: AchievementMetrics, *, today: date,
) -> tuple[Achievement, ...]:
    """Evaluate the whole catalogue and return it in a stable, useful order.

    Order: recently achieved first (newest date first), then locked milestones by
    how close they are to their target, with the catalogue order as the final
    deterministic tie-break. Nothing about the order depends on the clock beyond
    the ``today`` used for the recency flag.
    """

    items: list[Achievement] = []
    for definition in _catalogue():
        current, achieved_on = definition.read(metrics)
        achieved = current >= definition.target
        items.append(Achievement(
            key=definition.key,
            title=definition.title,
            description=definition.description,
            category=definition.category,
            achieved=achieved,
            # A threshold can be met with no recoverable historical date (for
            # example a weekly-count streak); the UI shows "—" rather than today.
            achieved_on=achieved_on if achieved else None,
            current=current,
            target=definition.target,
        ))

    def sort_key(item: tuple[int, Achievement]) -> tuple[int, float, int]:
        index, achievement = item
        if achievement.achieved:
            reached = (
                achievement.achieved_on.toordinal()
                if achievement.achieved_on is not None else date.min.toordinal()
            )
            return (0, -float(reached), index)
        ratio = achievement.current / achievement.target if achievement.target else 0.0
        return (1, -ratio, index)

    return tuple(item for _, item in sorted(enumerate(items), key=sort_key))


def recently_achieved(
    achievements: tuple[Achievement, ...], *, today: date,
    window_days: int = RECENT_ACHIEVEMENT_DAYS,
) -> tuple[Achievement, ...]:
    """Achievements reached within the last ``window_days`` days, newest first."""

    recent = [
        achievement for achievement in achievements
        if achievement.achieved_on is not None
        and 0 <= (today - achievement.achieved_on).days <= window_days
    ]
    return tuple(sorted(recent, key=lambda item: item.achieved_on or date.min, reverse=True))


def completed_count(achievements: tuple[Achievement, ...]) -> int:
    return sum(1 for achievement in achievements if achievement.achieved)
