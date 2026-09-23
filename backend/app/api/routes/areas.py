"""Area endpoints.

There is deliberately no delete endpoint: areas are archived so historical habit
configuration and (from Stage 3) recorded entries keep resolving.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession
from app.schemas.areas import AreaCreate, AreaRead, AreaUpdate
from app.services import areas as area_service

router = APIRouter(prefix="/areas", tags=["areas"])


@router.get("", response_model=list[AreaRead], summary="List areas")
def list_areas(
    session: DbSession,
    include_archived: Annotated[
        bool, Query(description="Include archived areas (default: active only).")
    ] = False,
) -> list[AreaRead]:
    return [
        AreaRead.from_model(area)
        for area in area_service.list_areas(session, include_archived=include_archived)
    ]


@router.post("", response_model=AreaRead, status_code=201, summary="Create an area")
def create_area(payload: AreaCreate, session: DbSession) -> AreaRead:
    area = area_service.create_area(
        session, name=payload.name, color=payload.color
    )
    return AreaRead.from_model(area)


@router.get("/{area_id}", response_model=AreaRead, summary="Fetch an area")
def get_area(area_id: int, session: DbSession) -> AreaRead:
    return AreaRead.from_model(area_service.get_area(session, area_id))


@router.patch("/{area_id}", response_model=AreaRead, summary="Update an area")
def update_area(
    area_id: int, payload: AreaUpdate, session: DbSession
) -> AreaRead:
    area = area_service.update_area(
        session, area_id, name=payload.name, color=payload.color
    )
    return AreaRead.from_model(area)


@router.post(
    "/{area_id}/archive",
    response_model=AreaRead,
    summary="Archive an area",
    description=(
        "Archived areas stay queryable but leave the default list. Refused with "
        "409 while the area still holds active habits."
    ),
)
def archive_area(area_id: int, session: DbSession) -> AreaRead:
    return AreaRead.from_model(area_service.archive_area(session, area_id))


@router.post(
    "/{area_id}/unarchive",
    response_model=AreaRead,
    summary="Restore an archived area",
)
def unarchive_area(area_id: int, session: DbSession) -> AreaRead:
    return AreaRead.from_model(area_service.unarchive_area(session, area_id))
