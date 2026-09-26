"""Schemas for dashboard, calendar aggregation, and day overview."""

from datetime import date

from pydantic import BaseModel, ConfigDict

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


class CalendarDaySummaryRead(ReadModel):
    entry_date: date
    daily_score: float | None
    completed_weight: int
    required_weight: int
    has_obligations: bool
    has_daily_state: bool
    mood: int | None
    is_future: bool


class DayOverviewRead(ReadModel):
    entry_date: date
    today: date
    is_future: bool
    progress: DayProgressRead
    items: list[DayItemRead]
    state: DailyStateRead | None
