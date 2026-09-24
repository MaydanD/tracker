"""Typed read-only API projections of domain calculation results."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.progress import ProgressStatus
from app.domain.daily import EntryStatus


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ScoreRead(ReadModel):
    score: float | None
    completed_weight: int
    required_weight: int


class ObligationRead(ReadModel):
    habit_id: int
    name: str
    weight: int
    entry_status: EntryStatus | None
    satisfied: bool


class DayProgressRead(ScoreRead):
    entry_date: date
    obligations: list[ObligationRead]


class WeekHabitProgressRead(ScoreRead):
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
    preferred_weekdays: list[int]
    status: ProgressStatus


class WeekProgressRead(ScoreRead):
    week_start: date
    week_end: date
    habits: list[WeekHabitProgressRead]


class StreakRead(ReadModel):
    habit_id: int
    current_streak: int
    unit: Literal["days", "weeks"]
    as_of: date


class ProgressRead(ReadModel):
    today: date
    day: DayProgressRead
    week: WeekProgressRead
    streaks: list[StreakRead]


class HabitProgressRead(ReadModel):
    today: date
    streak: StreakRead
    current_progress: WeekHabitProgressRead | None
