"""HTTP wiring for independent daily observations."""

from datetime import date

from fastapi import APIRouter, Response

from app.api.dependencies import ClockDep, DbSession
from app.domain.daily_state import StateValues
from app.schemas.daily_state import DailyStateRead, DailyStateResponse, DailyStateWrite
from app.services import daily_state as service

router = APIRouter(tags=["daily-state"])


@router.get("/days/{state_date}/state", response_model=DailyStateResponse)
def read_state(state_date: date, session: DbSession, clock: ClockDep) -> DailyStateResponse:
    state = service.get_state(session, state_date)
    return DailyStateResponse(
        state_date=state_date, today=clock.today(),
        state=DailyStateRead.model_validate(state) if state is not None else None,
    )


@router.put("/days/{state_date}/state", response_model=DailyStateRead)
def save_state(state_date: date, payload: DailyStateWrite, session: DbSession, clock: ClockDep) -> DailyStateRead:
    state = service.save_state(session, state_date, StateValues(**payload.model_dump()), today=clock.today())
    return DailyStateRead.model_validate(state)


@router.delete("/days/{state_date}/state", status_code=204)
def delete_state(state_date: date, session: DbSession, clock: ClockDep) -> Response:
    service.delete_state(session, state_date, today=clock.today())
    return Response(status_code=204)
