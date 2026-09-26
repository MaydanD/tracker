"""Typed Stage 11 records contracts.

Purely a projection: every value is already computed by the domain, so this module
only reshapes it for HTTP. The dashboard reuses :class:`RecordsPreviewRead`; the
records page uses :class:`RecordsRead`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.achievements import Achievement
from app.domain.records import (
    ConsistencyBest,
    LongestStreak,
    MostCompleted,
    RecordsBundle,
    ScoreDay,
    ScoreWeek,
)
from app.services.records import RecordsPreview, RecordsResult


class LongestStreakRead(BaseModel):
    habit_id: int
    name: str
    unit: Literal["days", "weeks"]
    current_streak: int
    best_streak: int
    best_start: date | None
    best_end: date | None
    archived: bool

    @classmethod
    def from_domain(cls, record: LongestStreak) -> LongestStreakRead:
        return cls(
            habit_id=record.habit_id, name=record.name, unit=record.unit,
            current_streak=record.current_streak, best_streak=record.best_streak,
            best_start=record.best_start, best_end=record.best_end,
            archived=record.archived,
        )


class BestDayRead(BaseModel):
    day: date
    score: float
    completed_weight: int
    required_weight: int
    ties: int

    @classmethod
    def from_domain(cls, record: ScoreDay) -> BestDayRead:
        return cls(
            day=record.day, score=record.score,
            completed_weight=record.completed_weight,
            required_weight=record.required_weight, ties=record.ties,
        )


class BestWeekRead(BaseModel):
    week_start: date
    week_end: date
    score: float
    coverage: float | None
    observed_days: int
    obligation_days: int
    ties: int

    @classmethod
    def from_domain(cls, record: ScoreWeek) -> BestWeekRead:
        return cls(
            week_start=record.week_start, week_end=record.week_end, score=record.score,
            coverage=record.coverage, observed_days=record.observed_days,
            obligation_days=record.obligation_days, ties=record.ties,
        )


class MostCompletedRead(BaseModel):
    day: date
    completed_count: int
    required_count: int
    ties: int

    @classmethod
    def from_domain(cls, record: MostCompleted) -> MostCompletedRead:
        return cls(
            day=record.day, completed_count=record.completed_count,
            required_count=record.required_count, ties=record.ties,
        )


class ConsistencyRead(BaseModel):
    habit_id: int
    name: str
    archived: bool
    period_start: date
    period_end: date
    done_days: int
    obligation_days: int
    ratio: float

    @classmethod
    def from_domain(cls, record: ConsistencyBest) -> ConsistencyRead:
        return cls(
            habit_id=record.habit_id, name=record.name, archived=record.archived,
            period_start=record.period_start, period_end=record.period_end,
            done_days=record.done_days, obligation_days=record.obligation_days,
            ratio=record.ratio,
        )


class RecordsSummaryRead(BaseModel):
    first_tracked_day: date | None
    tracked_days: int
    habit_completions: int
    experiments_created: int
    completed_experiments: int
    stable_insight_on: date | None
    well_supported_insight_on: date | None


class RecordSetRead(BaseModel):
    longest_streak: LongestStreakRead | None
    best_day: BestDayRead | None
    best_week: BestWeekRead | None
    most_completed: MostCompletedRead | None
    consistency: list[ConsistencyRead]


class AchievementProgressRead(BaseModel):
    current: int
    target: int


class AchievementRead(BaseModel):
    key: str
    title: str
    description: str
    category: str
    achieved: bool
    achieved_on: date | None
    progress: AchievementProgressRead

    @classmethod
    def from_domain(cls, achievement: Achievement) -> AchievementRead:
        return cls(
            key=achievement.key, title=achievement.title,
            description=achievement.description, category=achievement.category,
            achieved=achievement.achieved, achieved_on=achievement.achieved_on,
            progress=AchievementProgressRead(
                current=achievement.current, target=achievement.target,
            ),
        )


def _record_set(bundle: RecordsBundle) -> RecordSetRead:
    return RecordSetRead(
        longest_streak=(
            LongestStreakRead.from_domain(bundle.longest_streak)
            if bundle.longest_streak is not None else None
        ),
        best_day=(
            BestDayRead.from_domain(bundle.best_day)
            if bundle.best_day is not None else None
        ),
        best_week=(
            BestWeekRead.from_domain(bundle.best_week)
            if bundle.best_week is not None else None
        ),
        most_completed=(
            MostCompletedRead.from_domain(bundle.most_completed)
            if bundle.most_completed is not None else None
        ),
        consistency=[ConsistencyRead.from_domain(item) for item in bundle.consistency],
    )


class RecordsRead(BaseModel):
    summary: RecordsSummaryRead
    records: RecordSetRead
    achievements: list[AchievementRead]
    recent_achievements: list[AchievementRead]
    achieved_count: int
    total_count: int

    @classmethod
    def from_result(cls, result: RecordsResult) -> RecordsRead:
        bundle = result.bundle
        summary = bundle.summary
        return cls(
            summary=RecordsSummaryRead(
                first_tracked_day=summary.first_tracked_day,
                tracked_days=summary.tracked_days,
                habit_completions=summary.habit_completions,
                experiments_created=summary.experiments_created,
                completed_experiments=summary.completed_experiments,
                stable_insight_on=summary.stable_insight_on,
                well_supported_insight_on=summary.well_supported_insight_on,
            ),
            records=_record_set(bundle),
            achievements=[AchievementRead.from_domain(item) for item in result.achievements],
            recent_achievements=[
                AchievementRead.from_domain(item) for item in result.recent
            ],
            achieved_count=sum(1 for item in result.achievements if item.achieved),
            total_count=len(result.achievements),
        )


class RecordsPreviewRead(BaseModel):
    """The dashboard's compact records block."""

    longest_streak: LongestStreakRead | None
    latest_achievement: AchievementRead | None
    achieved_count: int
    total_count: int

    @classmethod
    def from_preview(cls, preview: RecordsPreview) -> RecordsPreviewRead:
        return cls(
            longest_streak=(
                LongestStreakRead.from_domain(preview.longest_streak)
                if preview.longest_streak is not None else None
            ),
            latest_achievement=(
                AchievementRead.from_domain(preview.latest_achievement)
                if preview.latest_achievement is not None else None
            ),
            achieved_count=preview.achieved_count,
            total_count=preview.total_count,
        )
