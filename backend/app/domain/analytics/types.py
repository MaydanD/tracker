"""Pure, serializable dataset and input types. Dates are local calendar dates."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import isfinite
from typing import Literal

from app.domain.daily_state import StateValues
from app.domain.habits import HabitConfig
from app.domain.progress import HabitHistory


class VariableType(StrEnum):
    NUMERIC = "numeric"
    ORDINAL = "ordinal"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


class Grain(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class Availability(StrEnum):
    PRESENT = "present"
    SOURCE_MISSING = "source_missing"
    FIELD_MISSING = "field_missing"
    NOT_APPLICABLE = "not_applicable"
    FUTURE = "future"
    NO_OBLIGATIONS = "no_obligations"
    NO_OBSERVATIONS = "no_observations"


Scalar = bool | int | float | str


@dataclass(frozen=True)
class Value:
    value: Scalar | None
    availability: Availability = Availability.PRESENT

    def __post_init__(self) -> None:
        if (self.value is None) != (self.availability != Availability.PRESENT):
            raise ValueError("Пустое значение должно содержать причину отсутствия.")
        if self.value is not None and type(self.value) not in (bool, int, float, str):
            raise ValueError("Недопустимый тип значения.")
        if type(self.value) is float and not isfinite(self.value):
            raise ValueError("Число должно быть конечным.")


@dataclass(frozen=True)
class Variable:
    key: str
    label: str
    type: VariableType
    grain: Grain
    source: str
    missing_semantics: str
    categories: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    habit_id: int | None = None


@dataclass(frozen=True)
class DatedConfig:
    effective_from: date
    configuration: HabitConfig


@dataclass(frozen=True)
class EntrySource:
    status: str
    quantity_micro: int | None
    skip_reason: str | None
    note: str | None


@dataclass(frozen=True)
class HabitInput:
    history: HabitHistory
    configurations: tuple[DatedConfig, ...]
    entries: dict[date, EntrySource]


@dataclass(frozen=True)
class DatasetInput:
    habits: tuple[HabitInput, ...]
    states: dict[date, StateValues]


@dataclass(frozen=True)
class HabitContext:
    configuration: DatedConfig | None
    applicable: bool
    # Source-only: includes planned skips and archived records, never imputed.
    entry: EntrySource | None


@dataclass(frozen=True)
class DailyRow:
    date: date
    week_start: date
    values: dict[str, Value]
    habits: dict[int, HabitContext]
    # Text stays in source context, outside the variable registry.
    state_source: StateValues | None


@dataclass(frozen=True)
class WeeklyHabitContext:
    habit_id: int
    name: str
    weekly_effective_from: date | None
    weekly_weight: int | None
    preferred_weekdays: tuple[int, ...]


@dataclass(frozen=True)
class WeeklyRow:
    week_start: date
    week_end: date
    requested_start: date
    requested_end: date
    requested_days: int
    elapsed_requested_days: int
    calendar_elapsed_days: int
    partial_requested_week: bool
    unfinished_week: bool
    progress_scope: Literal["calendar_week"]
    state_scope: Literal["requested_elapsed_dates"]
    # Counts dates with at least one active habit, including weekly schedules.
    active_habit_days: int
    values: dict[str, Value]
    # Canonical full-week quota anchor, preferred days, mixed-schedule counts.
    habits: tuple[WeeklyHabitContext, ...]


@dataclass(frozen=True)
class AnalyticsDataset:
    contract_version: str
    start: date
    end: date
    today: date
    variables: tuple[Variable, ...]
    daily: tuple[DailyRow, ...]
    weekly: tuple[WeeklyRow, ...]
