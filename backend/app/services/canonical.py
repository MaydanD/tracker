"""The shipped habit set: created through the ordinary services, never duplicated.

Tracker starts every user with 24 daily habits in four spheres (see
:mod:`app.domain.canonical`) so that nothing has to be typed in by hand. They are
created through exactly the same service calls the Сферы / Привычки screens use —
:func:`app.services.areas.create_area`, :func:`app.services.habits.create_habit`
and a validated :class:`~app.domain.habits.HabitConfig` — which is what makes them
ordinary habits rather than a parallel subsystem. Once created they can be
renamed, recoloured, moved between areas, re-scaled, re-weighed, archived and
versioned like any habit the user creates themselves, and this module never
rewrites an existing habit: it only creates what is missing.

The one special thing is the stable ``key`` on the row. It is a machine
identifier (``body.walk``) that reconciliation uses to recognise the records it
owns; renaming a habit in the UI never breaks that recognition, and a habit the
user created by hand has no key at all.

Reconciliation also retires the *pre-canonical* habits: default habits from
before this set existed, which would otherwise leave the user with two active
systems for the same day. Retirement is archival — history, entries, notes and
versions all stay in the database and remain readable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.models import AppMetadata, Area, Habit, HabitVersion
from app.domain.areas import area_name_key
from app.domain.daily import EntryStatus
from app.domain.canonical import (
    CANONICAL_AREAS,
    CANONICAL_AREAS_BY_KEY,
    CANONICAL_HABITS,
    CanonicalArea,
    CanonicalHabit,
)
from app.domain.habits import DEFAULT_IMPORTANCE, HabitConfig
from app.domain.schedule import Schedule, ScheduleType
from app.domain.tracking import TrackingMode
from app.services import areas as area_service
from app.services import daily as daily_service
from app.services import habits as habit_service

#: Where the value-scale prototype parked its recorded answers (see the
#: ``5824a510506e`` migration). Read once, then cleared.
PARKED_ENTRIES_KEY = "legacy_indicator_entries"


@dataclass(frozen=True, slots=True)
class ReconcileSummary:
    """What a reconciliation run changed; every count is zero on a no-op run."""

    areas_created: int
    habits_created: int
    legacy_habits_archived: int = 0
    legacy_areas_archived: int = 0
    parked_entries_adopted: int = 0

    @property
    def changed(self) -> bool:
        return bool(
            self.areas_created
            or self.habits_created
            or self.legacy_habits_archived
            or self.legacy_areas_archived
            or self.parked_entries_adopted
        )


def reconcile_canonical(session: Session, *, today: date) -> ReconcileSummary:
    """Create the shipped areas and habits that are missing, then retire the old.

    Idempotent by construction: everything is looked up by its stable key first,
    so a second run finds every record and creates nothing.
    """
    first_bootstrap = session.get(AppMetadata, "canonical_habits_initialized") is None
    # Snapshot identities before creation, including old habits created today.
    legacy_ids = set(session.scalars(select(Habit.id).where(Habit.key.is_(None)))) if first_bootstrap else set()
    legacy_area_ids = set(session.scalars(select(Area.id).where(Area.key.is_(None)))) if first_bootstrap else set()
    areas: dict[str, Area] = {}
    areas_created = 0
    for definition in CANONICAL_AREAS:
        area, created = _ensure_area(session, definition)
        areas[definition.key] = area
        areas_created += int(created)

    habits_created = 0
    for definition in CANONICAL_HABITS:
        _, created = _ensure_habit(
            session, definition, area=areas[definition.area_key], today=today
        )
        habits_created += int(created)

    adopted = adopt_parked_entries(session, today=today)

    era_start = canonical_era_start(session)
    retirement = (
        LegacyRetirement(0, 0)
        if era_start is None
        else retire_pre_canonical(session, canonical_since=era_start)
    )

    if first_bootstrap:
        extra_habits = extra_areas = 0
        for habit_id in legacy_ids:
            habit = session.get(Habit, habit_id)
            if habit is not None and habit.key is None and not habit.is_archived:
                habit.is_archived, habit.archived_at = True, utc_now()
                extra_habits += 1
        for area_id in legacy_area_ids:
            area = session.get(Area, area_id)
            if area is not None and area.key is None and not area.is_archived:
                area.is_archived, area.archived_at = True, utc_now()
                extra_areas += 1
        retirement = LegacyRetirement(retirement.habits_archived + extra_habits,
                                      retirement.areas_archived + extra_areas)
        session.add(AppMetadata(key="canonical_habits_initialized", value=today.isoformat()))

    session.commit()
    return ReconcileSummary(
        areas_created=areas_created,
        habits_created=habits_created,
        legacy_habits_archived=retirement.habits_archived,
        legacy_areas_archived=retirement.areas_archived,
        parked_entries_adopted=adopted,
    )


def adopt_parked_entries(session: Session, *, today: date) -> int:
    """Write answers parked by the migration into the habits they belong to.

    A database upgrading from the value-scale prototype holds its recorded
    answers in ``app_metadata`` (the canonical habits do not exist yet while the
    migration runs). Each answer is matched to its habit by the stable key and
    written through the ordinary daily service, so it obeys exactly the same
    validation as an answer typed into the check-in screen.

    The parking row is cleared once nothing is left to adopt; anything that could
    not be written yet (a missing habit, a future date) is kept for a later
    start rather than dropped.
    """
    parked = session.get(AppMetadata, PARKED_ENTRIES_KEY)
    if parked is None:
        return 0

    try:
        payload = json.loads(parked.value)
    except ValueError:  # pragma: no cover - the migration always writes JSON
        payload = []
    if not isinstance(payload, list):
        payload = []

    adopted = 0
    leftover: list[object] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        habit = session.scalar(select(Habit).where(Habit.key == item.get("key")))
        if habit is None:
            leftover.append(item)
            continue
        try:
            entry_date = date.fromisoformat(str(item["entry_date"]))
            recorded = daily_service.get_entry(session, habit.id, entry_date) is not None
            if not recorded:
                daily_service.save_entry(
                    session,
                    habit.id,
                    entry_date,
                    status=EntryStatus.DONE,
                    today=today,
                    value=item["value"],
                    note=item.get("note"),
                )
                adopted += 1
        except (AppError, KeyError, TypeError, ValueError):
            leftover.append(item)

    if leftover:
        parked.value = json.dumps(leftover, ensure_ascii=False)
        session.commit()
        return adopted

    session.delete(parked)
    session.commit()
    return adopted


@dataclass(frozen=True, slots=True)
class LegacyRetirement:
    """How much pre-canonical habit content a reconciliation retired."""

    habits_archived: int
    areas_archived: int


def canonical_era_start(session: Session) -> date | None:
    """The first day a shipped habit's configuration was in force, if any."""
    return session.scalar(
        select(func.min(HabitVersion.effective_from))
        .select_from(HabitVersion)
        .join(Habit, Habit.id == HabitVersion.habit_id)
        .where(Habit.key.is_not(None))
    )


def retire_pre_canonical(
    session: Session, *, canonical_since: date
) -> LegacyRetirement:
    """Archive habit-system content that predates the shipped set.

    A default habit from before the canonical set existed is the mixture the
    shipped habits replace: two active records for the same daily observation.
    Only content that predates the era is retired, and the boundary is the era
    itself (the first day a shipped habit was in force) rather than "today", so a
    habit the user creates from that day on is never touched and a restart cannot
    retire something created inside the era. Running this again is a no-op,
    because an already archived entity is skipped.

    Nothing is deleted. Versions, entries, notes and daily states stay in the
    database, stay readable through their own endpoints, and an archived habit or
    area can be restored — archiving only takes it out of the *active* set.
    """
    now = utc_now()

    habits_archived = 0
    #: Areas still holding an active habit stay active themselves.
    busy_area_ids: set[int] = set()
    for habit in session.scalars(select(Habit).where(Habit.is_archived.is_(False))):
        if not habit.versions:  # pragma: no cover - every habit has a version
            continue
        current = habit.current_version
        if habit.key is not None or current.effective_from >= canonical_since:
            busy_area_ids.add(current.area_id)
            continue
        habit.is_archived = True
        habit.archived_at = now
        habits_archived += 1

    session.flush()

    areas_archived = 0
    for area in session.scalars(select(Area).where(Area.is_archived.is_(False))):
        if area.key is not None or area.id in busy_area_ids:
            continue
        # An area from inside the canonical era is the user's own grouping — even
        # an empty one — so it is left alone.
        if _created_on(area.created_at) >= canonical_since:
            continue
        area.is_archived = True
        area.archived_at = now
        areas_archived += 1

    session.flush()
    return LegacyRetirement(habits_archived, areas_archived)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def _ensure_area(session: Session, definition: CanonicalArea) -> tuple[Area, bool]:
    """Find the shipped area by key, or create it (once)."""
    existing = session.scalar(select(Area).where(Area.key == definition.key))
    if existing is not None:
        return existing, False

    # An area the user already created under this name *is* the shipped one:
    # active area names are unique, so a second area with that name cannot exist,
    # and adopting keeps the user's own history attached to it.
    adopted = _active_area_named(session, definition.name)
    if adopted is not None:
        adopted.key = definition.key
        adopted.sort_order = definition.sort_order
        session.commit()
        return adopted, False

    area = area_service.create_area(
        session, name=definition.name, color=definition.color
    )
    area.key = definition.key
    area.sort_order = definition.sort_order
    session.commit()
    return area, True


def _ensure_habit(
    session: Session,
    definition: CanonicalHabit,
    *,
    area: Area,
    today: date,
) -> tuple[Habit, bool]:
    """Find the shipped habit by key, or create it (once) with its full config."""
    existing = session.scalar(select(Habit).where(Habit.key == definition.key))
    if existing is not None:
        return existing, False

    habit = habit_service.create_habit(
        session,
        _config(definition, area_id=area.id),
        effective_date=today,
    )
    habit.key = definition.key
    habit.sort_order = definition.sort_order
    session.commit()
    return habit, True


def _config(definition: CanonicalHabit, *, area_id: int) -> HabitConfig:
    """The habit configuration a shipped definition describes.

    Importance is deliberately ordinary (``normal``) for every shipped habit:
    the user is the one who decides what matters to them, in the habit editor.
    """
    return HabitConfig.create(
        name=definition.name,
        area_id=area_id,
        importance=DEFAULT_IMPORTANCE,
        tracking_mode=TrackingMode.BINARY,
        schedule=Schedule.create(ScheduleType.DAILY),
        value_type=definition.value_type,
        value_labels=definition.labels,
        direction=definition.direction,
    )


def _active_area_named(session: Session, name: str) -> Area | None:
    """An active area whose name matches, ignoring case."""
    wanted = area_name_key(name)
    for area in session.scalars(select(Area).where(Area.is_archived.is_(False))):
        if area_name_key(area.name) == wanted:
            return area
    return None


def _created_on(created_at: datetime) -> date:
    """The calendar day a row was created; timestamps are stored naive UTC."""
    return created_at.date()


__all__ = [
    "CANONICAL_AREAS_BY_KEY",
    "LegacyRetirement",
    "PARKED_ENTRIES_KEY",
    "ReconcileSummary",
    "adopt_parked_entries",
    "canonical_era_start",
    "reconcile_canonical",
    "retire_pre_canonical",
]
