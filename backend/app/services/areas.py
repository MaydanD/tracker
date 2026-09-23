"""Area use cases.

Areas are archived, never deleted: habits and future historical entries keep
referencing them, and the user's areas are a small, long-lived set.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models import Area
from app.db.queries import active_habits_in_area
from app.domain.areas import area_name_key, normalise_area_color, normalise_area_name
from app.domain.errors import (
    AreaHasActiveHabitsError,
    AreaNameConflictError,
    AreaNotFoundError,
)


def list_areas(session: Session, *, include_archived: bool = False) -> list[Area]:
    """Active areas by name, or every area when asked to include archived ones."""
    statement = select(Area)
    if not include_archived:
        statement = statement.where(Area.is_archived.is_(False))
    areas = list(session.scalars(statement))
    # Case-insensitive ordering, done in Python because the dataset is a handful
    # of rows and SQLite's default collation is not case-insensitive.
    return sorted(areas, key=lambda area: area.name.casefold())


def get_area(session: Session, area_id: int) -> Area:
    """Fetch an area or raise :class:`AreaNotFoundError`."""
    area = session.get(Area, area_id)
    if area is None:
        raise AreaNotFoundError(details={"area_id": area_id})
    return area


def create_area(session: Session, *, name: str, color: str | None = None) -> Area:
    """Create an area, keeping active names unique (case-insensitive)."""
    normalised_name = normalise_area_name(name)
    _ensure_name_available(session, normalised_name)

    area = Area(name=normalised_name, color=normalise_area_color(color))
    session.add(area)
    session.commit()
    session.refresh(area)
    return area


def update_area(
    session: Session,
    area_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
) -> Area:
    """Rename and/or recolour an area.

    Area names are not versioned: the name is display metadata, and historical
    habit configuration keeps referential integrity through ``area_id``.
    """
    area = get_area(session, area_id)

    if name is not None:
        normalised_name = normalise_area_name(name)
        if not area.is_archived:
            _ensure_name_available(session, normalised_name, exclude_area_id=area.id)
        area.name = normalised_name

    if color is not None:
        area.color = normalise_area_color(color)

    session.commit()
    session.refresh(area)
    return area


def archive_area(session: Session, area_id: int) -> Area:
    """Archive an area (idempotent).

    Refuses while the area still holds active habits, which would otherwise
    leave an active habit pointing at an archived area. Archive or move those
    habits first.
    """
    area = get_area(session, area_id)
    if area.is_archived:
        return area

    active_habits = active_habits_in_area(session, area.id)
    if active_habits:
        raise AreaHasActiveHabitsError(
            details={"area_id": area.id, "active_habits": len(active_habits)}
        )

    area.is_archived = True
    area.archived_at = utc_now()
    session.commit()
    session.refresh(area)
    return area


def unarchive_area(session: Session, area_id: int) -> Area:
    """Bring an area back into the active list (idempotent)."""
    area = get_area(session, area_id)
    if not area.is_archived:
        return area

    # Restoring the name could collide with an area created while this one was
    # archived, so availability is re-checked here.
    _ensure_name_available(session, area.name, exclude_area_id=area.id)

    area.is_archived = False
    area.archived_at = None
    session.commit()
    session.refresh(area)
    return area


def _ensure_name_available(
    session: Session, name: str, *, exclude_area_id: int | None = None
) -> None:
    """Reject a name already used by another *active* area."""
    wanted = area_name_key(name)
    existing = session.scalars(
        select(Area).where(Area.is_archived.is_(False))
    )
    for area in existing:
        if area.id == exclude_area_id:
            continue
        if area_name_key(area.name) == wanted:
            raise AreaNameConflictError(details={"name": name})
