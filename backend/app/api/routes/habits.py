"""Habit endpoints.

Stage 2 manages habit *configuration*. Recording habit completions for a day
belongs to Stage 3, and schedule/streak evaluation to Stage 4.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession
from app.schemas.habits import (
    HabitCreate,
    HabitRead,
    HabitUpdate,
    HabitVersionRead,
)
from app.services import habits as habit_service

router = APIRouter(prefix="/habits", tags=["habits"])


@router.get("", response_model=list[HabitRead], summary="List habits")
def list_habits(
    session: DbSession,
    include_archived: Annotated[
        bool, Query(description="Include archived habits (default: active only).")
    ] = False,
    area_id: Annotated[
        int | None, Query(description="Only habits currently in this area.")
    ] = None,
) -> list[HabitRead]:
    return [
        HabitRead.from_model(habit)
        for habit in habit_service.list_habits(
            session, include_archived=include_archived, area_id=area_id
        )
    ]


@router.post("", response_model=HabitRead, status_code=201, summary="Create a habit")
def create_habit(payload: HabitCreate, session: DbSession) -> HabitRead:
    habit = habit_service.create_habit(session, payload.to_domain())
    return HabitRead.from_model(habit)


@router.get("/{habit_id}", response_model=HabitRead, summary="Fetch a habit")
def get_habit(habit_id: int, session: DbSession) -> HabitRead:
    return HabitRead.from_model(habit_service.get_habit(session, habit_id))


@router.put(
    "/{habit_id}",
    response_model=HabitRead,
    summary="Replace a habit's configuration",
    description=(
        "The full configuration is required because each save is recorded as a "
        "configuration version. An unchanged configuration is a no-op, and an "
        "edit made on the same day updates that day's version."
    ),
)
def update_habit(
    habit_id: int, payload: HabitUpdate, session: DbSession
) -> HabitRead:
    habit = habit_service.update_habit(session, habit_id, payload.to_domain())
    return HabitRead.from_model(habit)


@router.post(
    "/{habit_id}/archive",
    response_model=HabitRead,
    summary="Archive a habit",
    description="Archived habits keep their history and stay queryable.",
)
def archive_habit(habit_id: int, session: DbSession) -> HabitRead:
    return HabitRead.from_model(habit_service.archive_habit(session, habit_id))


@router.post(
    "/{habit_id}/unarchive",
    response_model=HabitRead,
    summary="Restore an archived habit",
)
def unarchive_habit(habit_id: int, session: DbSession) -> HabitRead:
    return HabitRead.from_model(habit_service.unarchive_habit(session, habit_id))


@router.get(
    "/{habit_id}/versions",
    response_model=list[HabitVersionRead],
    summary="Habit configuration history",
    description="Every configuration version, newest first.",
)
def list_habit_versions(habit_id: int, session: DbSession) -> list[HabitVersionRead]:
    return [
        HabitVersionRead.from_model(version)
        for version in habit_service.list_versions(session, habit_id)
    ]


@router.get(
    "/{habit_id}/configuration",
    response_model=HabitVersionRead,
    summary="Configuration effective on a date",
    description=(
        "Answers 'what weight, schedule and area applied on this date?'. "
        "404 when the date precedes the habit's first version."
    ),
)
def get_habit_configuration(
    habit_id: int,
    session: DbSession,
    on: Annotated[date, Query(description="Calendar date (YYYY-MM-DD).")],
) -> HabitVersionRead:
    version = habit_service.configuration_on(session, habit_id, on)
    return HabitVersionRead.from_model(version)
