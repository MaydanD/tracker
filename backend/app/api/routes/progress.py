"""Derived state only; requesting progress never writes entries or counters."""

from datetime import date

from fastapi import APIRouter

from app.api.dependencies import ClockDep, DbSession
from app.domain.progress import (
    WeekProgress, current_streak, day_progress, week_habit_progress, week_progress,
)
from app.schemas.progress import HabitProgressRead, ProgressRead, WeekProgressRead
from app.services.progress import load_histories

router = APIRouter(tags=["progress"])


@router.get("/progress/days/{on}", response_model=ProgressRead)
def read_progress(on: date, session: DbSession, clock: ClockDep) -> dict[str, object]:
    today = clock.today()
    histories = load_histories(session)
    return {
        "today": today,
        "day": day_progress(histories, on),
        "week": week_progress(histories, on, today),
        "streaks": [current_streak(h, today) for h in histories],
    }


@router.get("/progress/weeks/{on}", response_model=WeekProgressRead)
def read_week(on: date, session: DbSession, clock: ClockDep) -> WeekProgress:
    return week_progress(load_histories(session), on, clock.today())


@router.get("/habits/{habit_id}/progress", response_model=HabitProgressRead)
def read_habit_progress(
    habit_id: int, session: DbSession, clock: ClockDep,
) -> dict[str, object]:
    today = clock.today()
    habit = load_histories(session, habit_id)[0]
    return {
        "today": today,
        "streak": current_streak(habit, today),
        "current_progress": week_habit_progress(habit, today, today),
    }
