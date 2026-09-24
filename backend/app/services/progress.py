"""Bulk-load authoritative data, then delegate all calculations to the domain."""

from datetime import UTC, date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyHabitEntry
from app.db.queries import load_habits
from app.domain.progress import HabitHistory, Version
from app.services.habits import get_habit


def load_histories(
    session: Session, habit_id: int | None = None,
) -> tuple[HabitHistory, ...]:
    habits = (
        [get_habit(session, habit_id)] if habit_id is not None
        else load_habits(session, include_archived=True)
    )
    statement = select(DailyHabitEntry)
    if habit_id is not None:
        statement = statement.where(DailyHabitEntry.habit_id == habit_id)
    entries: dict[int, dict[date, str]] = {}
    for entry in session.scalars(statement):
        entries.setdefault(entry.habit_id, {})[entry.entry_date] = entry.status
    histories: list[HabitHistory] = []
    for habit in habits:
        archived_on = None
        if habit.is_archived:
            if habit.archived_at is not None:
                # SQLite strips offsets: stored naive timestamps are UTC, never local.
                timestamp = habit.archived_at
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                archived_on = timestamp.astimezone().date()
            else:
                # Legacy inconsistent row: no guessed updated_at archive date.
                # Recorded dates stay readable in Stage 3; no obligations inferred.
                archived_on = date.min
        histories.append(HabitHistory(
            habit_id=habit.id,
            versions=tuple(
                Version(v.effective_from, v.name, v.weight, v.schedule)
                for v in habit.versions
            ),
            entries=entries.get(habit.id, {}), archived_on=archived_on,
        ))
    return tuple(histories)
