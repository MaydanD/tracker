"""Cross-row backup invariants. No database writes or clock-dependent rules."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict

from app.core.errors import AppError
from app.domain.areas import area_name_key, normalise_area_name
from app.domain.daily import coerce_status, normalise_skip_reason, normalise_note
from app.domain.daily_state import StateValues, validate_state
from app.domain.experiments import normalise_text, normalise_title, validate_window
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.schemas.backup import BackupDataV1


class BackupError(AppError):
    code = "invalid_backup"
    status_code = 422
    message = "Этот файл нельзя восстановить."


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise BackupError(reason)


def unique(rows, fields, section):
    seen = set()
    for row in rows:
        key = tuple(getattr(row, field) for field in fields)
        require(key not in seen, f"{section}: повторяется ключ ({', '.join(fields)}).")
        seen.add(key)


def validate_relations(data: BackupDataV1) -> None:
    for section in type(data).model_fields:
        unique(getattr(data, section), ("id",), section)
    unique(data.habit_versions, ("habit_id", "effective_from"), "habit_versions")
    unique(data.habit_entries, ("habit_id", "entry_date"), "habit_entries")
    unique(data.daily_states, ("state_date",), "daily_states")
    unique(data.insight_snapshots, ("fingerprint", "evaluated_on"), "insight_snapshots")
    areas = {row.id: row for row in data.areas}
    habits = {row.id: row for row in data.habits}
    versions = defaultdict(list)
    active_names = set()
    for row in [*data.areas, *data.habits]:
        require(row.is_archived == (row.archived_at is not None), "Архивный статус не соответствует дате архивации.")
    for row in data.areas:
        normalise_area_name(row.name)
        if not row.is_archived:
            name = area_name_key(row.name)
            require(name not in active_names, "Повторяется название активной сферы.")
            active_names.add(name)
    for row in data.habit_versions:
        require(row.habit_id in habits and row.area_id in areas, "habit_versions: отсутствует привычка или сфера.")
        schedule = Schedule.create(row.schedule_type, weekdays=row.schedule_weekdays,
                                   times_per_week=row.schedule_times_per_week)
        require(schedule.stored_weekdays == row.schedule_weekdays, "Некорректные дни расписания.")
        HabitConfig.create(name=row.name, description=row.description, area_id=row.area_id,
                           weight=row.weight, tracking_mode=row.tracking_mode,
                           quantity_unit=row.quantity_unit,
                           quantity_allows_decimal=row.quantity_allows_decimal, schedule=schedule)
        require(row.tracking_mode != "binary" or (row.quantity_unit is None and not row.quantity_allows_decimal),
                "У бинарной привычки не должно быть единиц или дробного учёта.")
        versions[row.habit_id].append(row)
    dates = {}
    for habit_id, habit in habits.items():
        history = sorted(versions[habit_id], key=lambda row: row.effective_from)
        require(bool(history), "У привычки отсутствует история настроек.")
        require([row.version_number for row in history] == list(range(1, len(history) + 1)),
                "Нарушен порядок версий настроек привычки.")
        require(habit.is_archived or not areas[history[-1].area_id].is_archived,
                "Активная привычка ссылается на архивную сферу.")
        dates[habit_id] = [row.effective_from for row in history]
    for row in data.habit_entries:
        require(row.habit_id in habits, "habit_entries: отсутствует привычка.")
        require(bisect_right(dates[row.habit_id], row.entry_date) > 0,
                "У записи отсутствуют настройки на её дату.")
        normalise_skip_reason(coerce_status(row.status), row.skip_reason)
        normalise_note(row.note)
        # Same-day config edits can change mode/unit after an observation was
        # saved. Preserve that original observation, never reinterpret quantity.
    for row in data.daily_states:
        values = StateValues(**{key: getattr(row, key) for key in StateValues.__dataclass_fields__})
        checked = validate_state(values, state_date=row.state_date, today=row.state_date)
        require(asdict(checked) == asdict(values), "daily_states: некорректные пустые или ненормализованные значения.")
    for row in data.experiments:
        normalise_title(row.title)
        normalise_text(row.hypothesis, field="hypothesis")
        normalise_text(row.protocol, field="protocol")
        validate_window(row.start_date, row.end_date)
    for row in data.insight_snapshots:
        require(row.period_start <= row.period_end, "insight_snapshots: некорректный период.")
        expected = "same_period" if row.lag == 0 else "x_earlier" if row.lag > 0 else "x_later"
        require(row.orientation == expected, "insight_snapshots: направление не соответствует лагу.")
