"""Stage 11 records endpoints.

Thin handlers: they resolve the injected clock, call the service and project the
result. No history scanning or achievement logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ClockDep, DbSession
from app.schemas.records import RecordsRead
from app.services import records as service

router = APIRouter(tags=["records"])


@router.get(
    "/records",
    response_model=RecordsRead,
    summary="Records and achievements",
    description=(
        "Personal bests and milestone achievements, derived from the current "
        "habit, Daily State, experiment and insight history. Nothing is stored: "
        "deleting the underlying data can change a record."
    ),
)
def read_records(session: DbSession, clock: ClockDep) -> RecordsRead:
    return RecordsRead.from_result(service.get_records(session, today=clock.today()))
