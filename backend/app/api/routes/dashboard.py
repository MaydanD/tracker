"""Dashboard and Calendar read-only aggregation endpoints."""

from datetime import date, time

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import ClockDep, DbSession
from app.domain.owl import PENDING_HOUR
from app.schemas.dashboard import CalendarDaySummaryRead, DashboardRead, DayOverviewRead
from app.services import dashboard as service

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardRead,
    summary="Dashboard aggregate view",
    description="Returns today's progress, weekly progress, streaks, yesterday's state, and today's habit overview.",
)
def read_dashboard(session: DbSession, clock: ClockDep) -> dict[str, object]:
    today = clock.today()
    # The only rule that needs a wall clock. Derived here from the injected clock
    # so the Owl domain stays deterministic and testable.
    after_hours = clock.now().time() >= time(PENDING_HOUR, 0)
    return service.get_dashboard_data(session, today=today, after_hours=after_hours)


@router.get(
    "/calendar",
    response_model=list[CalendarDaySummaryRead],
    summary="Calendar range summary",
    description="Returns day summaries for the requested date range (start to end inclusive).",
)
def read_calendar(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    session: DbSession = None,
    clock: ClockDep = None,
) -> list[dict[str, object]]:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Начальная дата не может быть позже конечной даты.",
        )
    if (end - start).days > 400:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Запрошенный диапазон превышает допустимый предел (400 дней).",
        )
    today = clock.today()
    return service.get_calendar_range(session, start, end, today=today)


@router.get(
    "/days/{entry_date}/overview",
    response_model=DayOverviewRead,
    summary="Complete day overview",
    description="Returns progress, habits overview, and daily state for a specific date.",
)
def read_day_overview(
    entry_date: date, session: DbSession, clock: ClockDep,
) -> dict[str, object]:
    today = clock.today()
    return service.get_day_overview(session, entry_date, today=today)
