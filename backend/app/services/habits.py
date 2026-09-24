"""Habit use cases, including configuration versioning.

Every habit has at least one configuration version. Creating a habit writes
version 1; changing its configuration appends (or, for a same-day edit, updates)
a version according to :func:`app.domain.history.plan_version_change`. History is
therefore never rewritten silently: the configuration effective on any past date
stays recoverable.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.time import SYSTEM_CLOCK, utc_now
from app.db.models import Area, Habit, HabitVersion
from app.db.queries import effective_version, load_habits
from app.domain.errors import (
    AreaArchivedError,
    HabitConfigurationNotFoundError,
    HabitNotFoundError,
)
from app.domain.habits import HabitConfig
from app.domain.history import (
    EffectiveConfiguration,
    VersionAction,
    plan_version_change,
)
from app.services.areas import get_area

FIRST_VERSION_NUMBER = 1


def list_habits(
    session: Session,
    *,
    include_archived: bool = False,
    area_id: int | None = None,
) -> list[Habit]:
    """Habits sorted by area then name, filtered by archive state and/or area."""
    habits = load_habits(session, include_archived=include_archived)

    if area_id is not None:
        habits = [
            habit
            for habit in habits
            if habit.current_version.area_id == area_id
        ]

    return sorted(
        habits,
        key=lambda habit: (
            habit.current_version.area.name.casefold(),
            habit.current_version.name.casefold(),
        ),
    )


def get_habit(session: Session, habit_id: int) -> Habit:
    """Fetch a habit or raise :class:`HabitNotFoundError`."""
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HabitNotFoundError(details={"habit_id": habit_id})
    return habit


def create_habit(
    session: Session,
    config: HabitConfig,
    *,
    effective_date: date | None = None,
) -> Habit:
    """Create a habit and its initial configuration version."""
    _ensure_area_usable(session, config.area_id)

    habit = Habit()
    session.add(habit)
    session.flush()  # assigns habit.id for the version's foreign key

    session.add(
        HabitVersion.from_config(
            habit_id=habit.id,
            version_number=FIRST_VERSION_NUMBER,
            effective_from=effective_date or SYSTEM_CLOCK.today(),
            config=config,
        )
    )
    session.commit()
    return _reload(session, habit)


def update_habit(
    session: Session,
    habit_id: int,
    config: HabitConfig,
    *,
    effective_date: date | None = None,
) -> Habit:
    """Replace a habit's configuration, recording it in history.

    Passing a configuration identical to the effective one is a no-op, so
    opening the edit form and saving without changes does not fabricate a
    version.
    """
    habit = get_habit(session, habit_id)
    _ensure_area_usable(session, config.area_id)

    effective_date = effective_date or SYSTEM_CLOCK.today()
    current = habit.current_version

    action = plan_version_change(
        current=EffectiveConfiguration(
            version_number=current.version_number,
            effective_from=current.effective_from,
            config=current.configuration,
        ),
        new_config=config,
        effective_date=effective_date,
    )

    if action is VersionAction.NO_CHANGE:
        return habit

    if action is VersionAction.REPLACE_CURRENT:
        current.apply_config(config)
    else:
        session.add(
            HabitVersion.from_config(
                habit_id=habit.id,
                version_number=current.version_number + 1,
                effective_from=effective_date,
                config=config,
            )
        )

    habit.updated_at = utc_now()
    session.commit()
    return _reload(session, habit)


def archive_habit(session: Session, habit_id: int) -> Habit:
    """Archive a habit (idempotent). Archived habits stay queryable."""
    habit = get_habit(session, habit_id)
    if habit.is_archived:
        return habit

    habit.is_archived = True
    habit.archived_at = utc_now()
    session.commit()
    session.refresh(habit)
    return habit


def unarchive_habit(session: Session, habit_id: int) -> Habit:
    """Return a habit to the active list (idempotent)."""
    habit = get_habit(session, habit_id)
    if not habit.is_archived:
        return habit

    _ensure_area_usable(session, habit.current_version.area_id)
    habit.is_archived = False
    habit.archived_at = None
    session.commit()
    session.refresh(habit)
    return habit


def list_versions(session: Session, habit_id: int) -> list[HabitVersion]:
    """Configuration history, newest first."""
    habit = get_habit(session, habit_id)
    return list(reversed(habit.versions))


def configuration_on(session: Session, habit_id: int, on: date) -> HabitVersion:
    """The configuration that applied on a calendar date.

    Raises :class:`HabitConfigurationNotFoundError` for dates before the habit's
    first version — the habit did not exist yet, which is different from
    "unconfigured".
    """
    habit = get_habit(session, habit_id)
    version = effective_version(habit.versions, on)
    if version is None:
        raise HabitConfigurationNotFoundError(
            details={"habit_id": habit.id, "on": on.isoformat()}
        )
    return version


def _ensure_area_usable(session: Session, area_id: int) -> Area:
    """Habits belong to exactly one area, and that area must be active."""
    area = get_area(session, area_id)
    if area.is_archived:
        raise AreaArchivedError(details={"area_id": area_id})
    return area


def _reload(session: Session, habit: Habit) -> Habit:
    """Invalidate a habit so reads reflect what was just persisted.

    Sessions use ``expire_on_commit=False`` so reads stay cheap; a habit that was
    just written therefore has to be expired explicitly before it is read back,
    otherwise ``current_version`` could still show the previous configuration.
    """
    session.expire(habit)
    return habit
