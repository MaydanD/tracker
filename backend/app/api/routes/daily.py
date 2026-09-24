"""Daily tracking endpoints.

Stage 3 is manual day-by-day recording. These routes expose one calendar date as
a whole (the day screen) and one habit's record on one date.

Notes on the shape of the API:

* saving an entry is a ``PUT``: the operation is an idempotent replace, so saving
  the same day twice leaves one row rather than creating a duplicate;
* clearing a day is a ``DELETE`` of an *entry*. Habits and areas still have no
  delete endpoint — they are archived, and recorded history must survive. A
  default day simply returns to the ``no entry`` state;
* every rule (existence, date, future rules, quantity against the historical
  configuration, skip reason) is enforced here on the server, independently of
  what the screen chooses to offer.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response, status

from app.api.dependencies import ClockDep, DbSession
from app.domain.errors import DailyEntryNotFoundError
from app.schemas.daily import DailyEntryRead, DailyEntryWrite, DayItemRead, DayRead
from app.services import daily as daily_service

router = APIRouter(tags=["daily"])


@router.get(
    "/days/{entry_date}",
    response_model=DayRead,
    summary="State of a calendar date",
    description=(
        "Every habit that existed on the date, with the configuration that "
        "applied then and the record for that day. An unrecorded habit has a "
        "null entry — 'no entry' is a state of its own and never means 'missed'."
    ),
)
def read_day(entry_date: date, session: DbSession, clock: ClockDep) -> DayRead:
    today = clock.today()
    return DayRead(
        entry_date=entry_date,
        today=today,
        is_future=entry_date > today,
        items=[
            DayItemRead.from_item(item)
            for item in daily_service.day_overview(session, entry_date)
        ],
    )


@router.get(
    "/habits/{habit_id}/entries/{entry_date}",
    response_model=DailyEntryRead,
    summary="Fetch one habit's entry for a date",
    description="404 when that day has no entry yet.",
)
def read_entry(
    habit_id: int, entry_date: date, session: DbSession
) -> DailyEntryRead:
    view = daily_service.get_entry(session, habit_id, entry_date)
    if view is None:
        raise DailyEntryNotFoundError(
            details={"habit_id": habit_id, "entry_date": entry_date.isoformat()}
        )
    return DailyEntryRead.from_model(view.entry, view.version)


@router.put(
    "/habits/{habit_id}/entries/{entry_date}",
    response_model=DailyEntryRead,
    summary="Create or replace a habit's entry for a date",
    description=(
        "Idempotent: the entry for (habit, date) is replaced, never duplicated. "
        "A future date only accepts `skipped` with a reason."
    ),
)
def save_entry(
    habit_id: int,
    entry_date: date,
    payload: DailyEntryWrite,
    session: DbSession,
    clock: ClockDep,
) -> DailyEntryRead:
    view = daily_service.save_entry(
        session,
        habit_id,
        entry_date,
        status=payload.status,
        today=clock.today(),
        quantity_value=payload.quantity_value,
        skip_reason=payload.skip_reason,
        note=payload.note,
    )
    return DailyEntryRead.from_model(view.entry, view.version)


@router.delete(
    "/habits/{habit_id}/entries/{entry_date}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a habit's entry for a date",
    description=(
        "Returns the day to 'no entry'. Idempotent: clearing a day that holds "
        "nothing is not an error."
    ),
)
def delete_entry(habit_id: int, entry_date: date, session: DbSession) -> Response:
    daily_service.delete_entry(session, habit_id, entry_date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
