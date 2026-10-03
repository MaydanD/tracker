"""Schemas for dashboard, calendar aggregation, and day overview."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.domain.owl import OwlState
from app.schemas.daily import DayItemRead
from app.schemas.daily_state import DailyStateRead
from app.schemas.progress import DayProgressRead, StreakRead, WeekProgressRead
from app.schemas.records import RecordsPreviewRead


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DashboardRead(ReadModel):
    today: date
    today_progress: DayProgressRead
    week_progress: WeekProgressRead
    streaks: list[StreakRead]
    yesterday_state: DailyStateRead | None
    today_items: list[DayItemRead]
    # Stage 9: the one contextual Owl state for the dashboard, or null.
    owl: OwlState | None = None
    # Stage 11: a compact records preview (top streak + latest achievement).
    records: RecordsPreviewRead | None = None


class CalendarAreaScoreRead(ReadModel):
    area_id: int
    name: str
    color: str
    score: float


class CalendarHabitScoreRead(ReadModel):
    habit_id: int
    name: str
    area_id: int
    area_name: str
    color: str
    score: float
    value: int | None = None
    value_type: str | None = None
    direction: str | None = None


class CalendarDaySummaryRead(ReadModel):
    entry_date: date
    total_items: int
    answered_items: int
    daily_score: float | None
    completed_weight: float
    required_weight: int
    has_obligations: bool
    has_daily_state: bool
    mood: int | None
    is_future: bool
    area_scores: list[CalendarAreaScoreRead] = Field(default_factory=list)
    habit_scores: list[CalendarHabitScoreRead] = Field(default_factory=list)


class DayOverviewRead(ReadModel):
    entry_date: date
    today: date
    is_future: bool
    progress: DayProgressRead
    items: list[DayItemRead]
    state: DailyStateRead | None
