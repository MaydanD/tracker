"""The public read-only analytics service. One batch per source, no queries in loops."""

from dataclasses import fields
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyHabitEntry
from app.db.models.daily_state import DailyState
from app.db.queries import load_habits
from app.domain.analytics.builder import build_dataset, validate_range
from app.domain.analytics.types import AnalyticsDataset, DatedConfig, DatasetInput, EntrySource, HabitInput
from app.domain.daily_state import StateValues
from app.domain.progress import week_bounds
from app.services.progress import histories_from_loaded


def get_dataset(session: Session, start: date, end: date, *, today: date) -> AnalyticsDataset:
    """Inclusive range, at most 3660 days. Does not flush, commit, or mutate ORM rows.

    All habit histories are loaded once (including archived identities); entries
    are bounded to the enclosing calendar weeks and State to the requested range.
    No ORM objects leave the loading layer.
    """
    validate_range(start, end)
    with session.no_autoflush:
        inputs = _load_dataset(session, start, end, today=today)
    return build_dataset(inputs, start, end, today=today)


def _load_dataset(session: Session, start: date, end: date, *, today: date) -> DatasetInput:
    padded_start, padded_end = week_bounds(start)[0], week_bounds(end)[1]
    habits = sorted(load_habits(session, include_archived=True), key=lambda h: h.id)
    entries = list(session.scalars(select(DailyHabitEntry).where(
        DailyHabitEntry.entry_date.between(padded_start, padded_end))))
    histories = histories_from_loaded(habits, entries)
    entries_by_habit: dict[int, dict[date, EntrySource]] = {}
    for entry in entries:
        entries_by_habit.setdefault(entry.habit_id, {})[entry.entry_date] = EntrySource(
            entry.status, entry.quantity_value_micro, entry.skip_reason, entry.note)
    inputs = []
    for habit, history in zip(habits, histories, strict=True):
        # Include the union of applicable habits and recorded sources across full
        # intersecting weeks. Column sets stay constant even across creation/archive.
        relevant = (history.versions and history.versions[0].effective_from <= padded_end
                    and (history.archived_on is None or history.archived_on > max(
                        padded_start, history.versions[0].effective_from)))
        if relevant or habit.id in entries_by_habit:
            inputs.append(HabitInput(history, tuple(
                DatedConfig(v.effective_from, v.configuration) for v in habit.versions
            ), entries_by_habit.get(habit.id, {})))
    states = {
        s.state_date: StateValues(**{f.name: getattr(s, f.name) for f in fields(StateValues)})
        for s in session.scalars(select(DailyState).where(
            DailyState.state_date.between(start, min(end, today))))
    }
    return DatasetInput(tuple(inputs), states)
