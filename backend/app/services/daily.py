"""Daily habit entry use cases.

The service owns the *sequencing* of daily tracking: find the habit, resolve the
configuration that applied on that date, apply the pure rules from
:mod:`app.domain.daily`, then write exactly one row for ``habit_id + entry_date``.
Everything that decides whether a day is valid lives in the domain layer; this
module only decides *which* configuration to validate against and how to persist
the result.

Historical configuration is resolved through the existing effective-dated lookup
(:func:`app.services.habits.configuration_on`), never through a copy stored on the
entry. Editing 5 September therefore validates a quantity against the unit and
decimal rule that were in force on 5 September, even if the habit has been
reconfigured since.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import DailyHabitEntry, Habit, HabitVersion
from app.db.queries import effective_version, load_habits
from app.domain.daily import EntryStatus, EntryValues, validate_entry
from app.domain.errors import HabitNotFoundError
from app.services import habits as habit_service


@dataclass(frozen=True, slots=True)
class EntryView:
    """An entry together with the configuration that applied on its date.

    The pair travels together because every representation of an entry (the API,
    the day screen) needs the historical unit next to the value.
    """

    entry: DailyHabitEntry
    version: HabitVersion


@dataclass(frozen=True, slots=True)
class DayItem:
    """One habit as it appears on a chosen calendar date.

    ``entry`` is ``None`` when nothing has been recorded yet — that is the
    ``no entry`` state, and it is *not* the same as ``missed``.
    """

    habit: Habit
    version: HabitVersion
    entry: DailyHabitEntry | None


def get_entry(
    session: Session, habit_id: int, entry_date: date
) -> EntryView | None:
    """The entry for one habit and date, or ``None`` when nothing is recorded."""
    entry = _find(session, habit_id, entry_date)
    if entry is None:
        return None

    # A habit always has a configuration version by the time an entry exists, so
    # the lookup cannot fail here; it is the same rule that guarded the write.
    version = habit_service.configuration_on(session, habit_id, entry_date)
    return EntryView(entry=entry, version=version)


def save_entry(
    session: Session,
    habit_id: int,
    entry_date: date,
    *,
    status: EntryStatus | str,
    today: date,
    quantity_value: object | None = None,
    skip_reason: str | None = None,
    note: str | None = None,
) -> EntryView:
    """Create or replace the entry for one habit and date (idempotent).

    Saving twice for the same day edits the existing row, so a day can never be
    recorded twice and the unique constraint is never something a caller has to
    work around.

    Raises domain errors for every rejected case: an unknown habit, a date before
    the habit existed, a status that a future date does not accept, a missing or
    misplaced skip reason, and a quantity the historical configuration does not
    allow.
    """
    # Resolves the habit *and* the configuration effective on that date, raising
    # habit_not_found / configuration_not_found as appropriate.
    version = habit_service.configuration_on(session, habit_id, entry_date)

    values = validate_entry(
        configuration=version.configuration,
        status=status,
        entry_date=entry_date,
        today=today,
        quantity_value=quantity_value,
        skip_reason=skip_reason,
        note=note,
    )

    try:
        entry = _write(
            session,
            habit_id,
            entry_date,
            values,
            existing=_find(session, habit_id, entry_date),
        )
    except IntegrityError:
        # Two saves of the same day can interleave between the lookup above and the
        # insert (a double-clicked save, or two clients). The unique constraint
        # catches the loser, and the correct behaviour is the same as any other
        # repeat save: update the row that now exists. Only that specific case is
        # recovered — if no row is there, the integrity error is a real one (a
        # constraint backstop firing) and is re-raised.
        session.rollback()
        existing = _find(session, habit_id, entry_date)
        if existing is None:
            raise
        entry = _write(session, habit_id, entry_date, values, existing=existing)

    session.refresh(entry)
    return EntryView(entry=entry, version=version)


def _find(
    session: Session, habit_id: int, entry_date: date
) -> DailyHabitEntry | None:
    """The stored entry for a habit and date, if any."""
    return session.scalar(
        select(DailyHabitEntry).where(
            DailyHabitEntry.habit_id == habit_id,
            DailyHabitEntry.entry_date == entry_date,
        )
    )


def _write(
    session: Session,
    habit_id: int,
    entry_date: date,
    values: EntryValues,
    *,
    existing: DailyHabitEntry | None,
) -> DailyHabitEntry:
    """Insert or update the single row for a habit and date, then commit."""
    entry = existing
    if entry is None:
        entry = DailyHabitEntry(habit_id=habit_id, entry_date=entry_date)
        session.add(entry)

    entry.status = values.status.value
    entry.quantity_value_micro = (
        values.quantity.scaled if values.quantity is not None else None
    )
    entry.skip_reason = values.skip_reason
    entry.note = values.note

    session.commit()
    return entry


def delete_entry(session: Session, habit_id: int, entry_date: date) -> bool:
    """Remove an entry, returning the day to the ``no entry`` state.

    Deleting never substitutes ``missed``: the day simply becomes unrecorded,
    because the user has expressed nothing about it.

    Returns whether a row was removed. Removing a day that has nothing recorded is
    a no-op rather than an error, so clearing a day twice behaves the same way.

    An unknown habit is still rejected: a typo must not look like a successful
    clear.
    """
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HabitNotFoundError(details={"habit_id": habit_id})

    entry = _find(session, habit_id, entry_date)
    if entry is None:
        return False

    session.delete(entry)
    session.commit()
    return True


def day_overview(session: Session, day: date) -> list[DayItem]:
    """Every habit worth showing on a calendar date, with its recorded state.

    A habit appears when it existed on that date, which is exactly when it has a
    configuration version effective on or before it. The schedule is *not*
    consulted: assigning habits to days, and deciding that an unrecorded day was
    missed, belongs to the schedule engine in a later stage. Nothing here
    synthesises entries.

    Archived habits appear only when that date already holds a record of them, so
    archiving never hides (and never deletes) recorded history while still keeping
    the screen focused on current habits.
    """
    entries = _entries_on(session, day)

    items: list[DayItem] = []
    for habit in load_habits(session, include_archived=True):
        version = effective_version(habit.versions, day)
        if version is None:
            # The habit did not exist yet on this date.
            continue

        entry = entries.get(habit.id)
        if habit.is_archived and entry is None:
            continue

        items.append(DayItem(habit=habit, version=version, entry=entry))

    # Same ordering as the habit list (area, then name), so the day screen does
    # not reshuffle when the user changes the date.
    return sorted(
        items,
        key=lambda item: (
            item.version.area.name.casefold(),
            item.version.name.casefold(),
        ),
    )


def _entries_on(session: Session, day: date) -> dict[int, DailyHabitEntry]:
    """Entries recorded on a date, keyed by habit."""
    entries = session.scalars(
        select(DailyHabitEntry).where(DailyHabitEntry.entry_date == day)
    )
    return {entry.habit_id: entry for entry in entries}
