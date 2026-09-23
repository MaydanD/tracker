"""Reusable queries over the habit configuration model.

These helpers exist so the "current configuration" rule is expressed once.
Configuration versions are ordered by ``effective_from``, so the latest version
is the current one and the last version not after a date is the effective one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Habit, HabitVersion


def load_habits(session: Session, *, include_archived: bool = False) -> list[Habit]:
    """Load habits, newest configuration versions included.

    Configuration versions arrive through the model's ``selectin`` strategy, so
    this is one query plus one query for the versions — not a query per habit.
    """
    statement = select(Habit)
    if not include_archived:
        statement = statement.where(Habit.is_archived.is_(False))
    return list(session.scalars(statement).unique())


def active_habits_in_area(session: Session, area_id: int) -> list[Habit]:
    """Non-archived habits whose *current* configuration is in ``area_id``."""
    return [
        habit
        for habit in load_habits(session)
        if habit.current_version.area_id == area_id
    ]


def effective_version(
    versions: Sequence[HabitVersion], on: date
) -> HabitVersion | None:
    """The version effective on ``on``, or ``None`` if the habit did not exist yet.

    ``versions`` must be in ascending ``effective_from`` order (as loaded by the
    ``Habit.versions`` relationship).
    """
    effective = [version for version in versions if version.effective_from <= on]
    return effective[-1] if effective else None
