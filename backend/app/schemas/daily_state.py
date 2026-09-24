"""Strict input shapes; domain owns ranges and cross-field rules."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt


class DailyStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mood: StrictInt | None = None
    energy: StrictInt | None = None
    wellbeing: StrictInt | None = None
    sleep_status: str | None = None
    sleep_minutes: StrictInt | None = None
    alcohol: StrictBool | None = None
    alcohol_detail: str | None = None
    gaming: StrictBool | None = None
    gaming_minutes: StrictInt | None = None
    computer_overuse: StrictBool | None = None
    computer_minutes: StrictInt | None = None
    note: str | None = None


class DailyStateRead(DailyStateWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state_date: date
    created_at: datetime
    updated_at: datetime


class DailyStateResponse(BaseModel):
    state_date: date
    today: date
    state: DailyStateRead | None
