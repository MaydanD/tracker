"""Stage 11 records use case: load every fact once, then compute in memory.

The whole point of this layer is bounded I/O. A records page touches the entire
history, so a naive implementation would issue a query per habit or per day.
Instead there are at most five batched reads regardless of history size:

1. habit histories (habits + versions + daily entries), reused from the caller
   when the dashboard has already loaded them;
2. every Daily State date;
3. every experiment row;
4. the first evaluation date per insight confidence level;
5. nothing else.

All rules live in :mod:`app.domain.records` and :mod:`app.domain.achievements`;
this module only loads, then delegates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyState, Experiment, InsightSnapshot
from app.domain.achievements import (
    Achievement,
    AchievementMetrics,
    evaluate_achievements,
    recently_achieved,
)
from app.domain.experiments import effective_end, status_of
from app.domain.progress import HabitHistory
from app.domain.records import LongestStreak, RecordsBundle, compute_records
from app.services import progress as progress_service


@dataclass(frozen=True)
class RecordsResult:
    """Domain output, before it is projected into the HTTP contract."""

    bundle: RecordsBundle
    achievements: tuple[Achievement, ...]
    recent: tuple[Achievement, ...]


@dataclass(frozen=True)
class RecordsPreview:
    """The compact subset the dashboard shows."""

    longest_streak: LongestStreak | None
    latest_achievement: Achievement | None
    achieved_count: int
    total_count: int


def _load_state_days(session: Session, *, today: date) -> tuple[date, ...]:
    """Every calendar day that has a Daily State record, oldest first."""

    rows = session.scalars(
        select(DailyState.state_date).where(DailyState.state_date <= today)
    )
    return tuple(sorted(set(rows)))


def _load_experiment_dates(
    session: Session, *, today: date,
) -> tuple[tuple[date, ...], tuple[date, ...]]:
    """``(created_on, completed_on)`` experiment dates, both ascending.

    A cancelled experiment is *not* completed; only a window that ran to its end
    counts, dated by its effective last day.
    """

    created: list[date] = []
    completed: list[date] = []
    for experiment in session.scalars(select(Experiment)):
        created.append(experiment.created_at.date())
        if status_of(
            experiment.start_date, experiment.end_date, experiment.cancelled_on, today
        ) == "completed":
            completed.append(
                effective_end(experiment.start_date, experiment.end_date, experiment.cancelled_on)
            )
    return tuple(sorted(created)), tuple(sorted(completed))


def _load_insight_first_dates(session: Session) -> dict[str, date]:
    """The first evaluation day each confidence level ever appeared in history.

    Uses the Stage 8 snapshots that already exist rather than recomputing
    analytics, and never the current feed — which would misdate an insight that
    has been stable for months as if it were discovered today.
    """

    rows = session.execute(
        select(InsightSnapshot.confidence, func.min(InsightSnapshot.evaluated_on))
        .where(InsightSnapshot.confidence.is_not(None))
        .group_by(InsightSnapshot.confidence)
    ).all()
    return {confidence: first for confidence, first in rows if confidence is not None}


def get_records(
    session: Session, *, today: date, histories: tuple[HabitHistory, ...] | None = None,
) -> RecordsResult:
    """Compute records and achievements for the current history."""

    histories = (
        histories if histories is not None else progress_service.load_histories(session)
    )
    state_days = _load_state_days(session, today=today)
    created_on, completed_on = _load_experiment_dates(session, today=today)
    insight_dates = _load_insight_first_dates(session)

    bundle = compute_records(
        histories,
        today=today,
        state_days=state_days,
        experiments_created=len(created_on),
        completed_experiments=len(completed_on),
        stable_insight_on=insight_dates.get("stable"),
        well_supported_insight_on=insight_dates.get("well_supported"),
    )
    metrics = AchievementMetrics(
        completions_by_habit=bundle.facts.completions_by_habit,
        streak_milestones=bundle.facts.streak_milestones,
        longest_daily_run=bundle.facts.longest_daily_run,
        perfect_day_on=bundle.facts.perfect_day_on,
        perfect_week_on=bundle.facts.perfect_week_on,
        tracked_days=bundle.facts.tracked_days,
        state_days=state_days,
        experiments_created_on=created_on,
        experiments_completed_on=completed_on,
        stable_insight_on=insight_dates.get("stable"),
        well_supported_insight_on=insight_dates.get("well_supported"),
    )
    achievements = evaluate_achievements(metrics, today=today)
    return RecordsResult(
        bundle=bundle,
        achievements=achievements,
        recent=recently_achieved(achievements, today=today),
    )


def to_preview(result: RecordsResult) -> RecordsPreview:
    """Project the full result down to the dashboard's compact block."""

    latest: Achievement | None = None
    for achievement in result.achievements:
        if not achievement.achieved or achievement.achieved_on is None:
            continue
        if latest is None or achievement.achieved_on > (latest.achieved_on or date.min):
            latest = achievement
    return RecordsPreview(
        longest_streak=result.bundle.longest_streak,
        latest_achievement=latest,
        achieved_count=sum(1 for item in result.achievements if item.achieved),
        total_count=len(result.achievements),
    )


def records_preview(
    session: Session, *, today: date, histories: tuple[HabitHistory, ...] | None = None,
) -> RecordsPreview:
    """Convenience wrapper for the dashboard."""

    return to_preview(get_records(session, today=today, histories=histories))
