"""Habit schemas.

Habit responses flatten the *current* configuration (the latest version) next to
the habit's identity, so clients never have to stitch versions together
themselves. Schedule summaries and weekly quotas are computed server-side, which
keeps schedule rules out of the UI.

Semantic validation — weight range, quantity unit rules, schedule shape — lives
in ``app.domain`` and is reported as a 422 with a specific error code. These
schemas describe shape only, so the rules exist in exactly one place.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.db.models import Habit, HabitVersion
from app.domain.habits import NAME_MAX_LENGTH, HabitConfig
from app.domain.schedule import Schedule, ScheduleType
from app.domain.tracking import QUANTITY_UNIT_MAX_LENGTH, TrackingMode
from app.schemas.areas import AreaSummary


class ScheduleInput(BaseModel):
    """Schedule configuration as submitted by a client.

    Which fields are required depends on ``type``:

    * ``daily`` — neither ``weekdays`` nor ``times_per_week``;
    * ``weekdays`` — ``weekdays`` with at least one day (0 = Monday … 6 = Sunday).
      The weekly quota is derived from the selection;
    * ``times_per_week`` — ``times_per_week`` between 1 and 7.
    """

    type: ScheduleType
    weekdays: list[int] | None = None
    times_per_week: int | None = None

    def to_domain(self) -> Schedule:
        return Schedule.create(
            self.type,
            weekdays=self.weekdays,
            times_per_week=self.times_per_week,
        )


class ScheduleRead(BaseModel):
    """Stored schedule plus the values the UI would otherwise recompute."""

    type: ScheduleType
    weekdays: list[int]
    times_per_week: int | None
    weekly_required_count: int = Field(
        description="Completions the canonical Monday–Sunday week expects."
    )
    summary: str

    @classmethod
    def from_domain(cls, schedule: Schedule) -> ScheduleRead:
        return cls(
            type=schedule.type,
            weekdays=list(schedule.weekdays),
            times_per_week=schedule.times_per_week,
            weekly_required_count=schedule.weekly_required_count,
            summary=schedule.summary,
        )


class VersionSummary(BaseModel):
    """Identifies the configuration version currently in effect."""

    version_number: int
    effective_from: date
    created_at: datetime

    @classmethod
    def from_model(cls, version: HabitVersion) -> VersionSummary:
        return cls(
            version_number=version.version_number,
            effective_from=version.effective_from,
            created_at=version.created_at,
        )


def config_fields(version: HabitVersion) -> dict[str, object]:
    """Shared configuration fields for habit and version responses."""
    return {
        "name": version.name,
        "description": version.description,
        "area_id": version.area_id,
        "area": AreaSummary.from_model(version.area),
        "weight": version.weight,
        "tracking_mode": TrackingMode(version.tracking_mode),
        "quantity_unit": version.quantity_unit,
        "quantity_allows_decimal": version.quantity_allows_decimal,
        "schedule": ScheduleRead.from_domain(version.schedule),
    }


class HabitConfigInput(BaseModel):
    """Full habit configuration, used for both create and update."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = None
    area_id: int = Field(gt=0)
    weight: int = Field(description="1 = normal, 2 = important, 3 = key.")
    tracking_mode: TrackingMode
    quantity_unit: str | None = Field(
        default=None,
        max_length=QUANTITY_UNIT_MAX_LENGTH,
        description="Required when tracking_mode is binary_quantity.",
    )
    quantity_allows_decimal: bool = False
    schedule: ScheduleInput

    def to_domain(self) -> HabitConfig:
        return HabitConfig.create(
            name=self.name,
            description=self.description,
            area_id=self.area_id,
            weight=self.weight,
            tracking_mode=self.tracking_mode,
            quantity_unit=self.quantity_unit,
            quantity_allows_decimal=self.quantity_allows_decimal,
            schedule=self.schedule.to_domain(),
        )


class HabitCreate(HabitConfigInput):
    """Payload for creating a habit."""


class HabitUpdate(HabitConfigInput):
    """Payload for replacing a habit's configuration.

    The whole configuration is submitted because a save is recorded as a new
    configuration version; there is no partial-patch semantics in Stage 2.
    """


class HabitConfigRead(BaseModel):
    """A configuration snapshot, as stored in history."""

    name: str
    description: str | None
    area_id: int
    area: AreaSummary
    weight: int
    tracking_mode: TrackingMode
    quantity_unit: str | None
    quantity_allows_decimal: bool
    schedule: ScheduleRead

    @classmethod
    def from_version(cls, version: HabitVersion) -> HabitConfigRead:
        return cls(**config_fields(version))  # type: ignore[arg-type]


class HabitVersionRead(HabitConfigRead):
    """One entry of a habit's configuration history."""

    habit_id: int
    version_number: int
    effective_from: date
    created_at: datetime

    @classmethod
    def from_model(cls, version: HabitVersion) -> HabitVersionRead:
        return cls(
            habit_id=version.habit_id,
            version_number=version.version_number,
            effective_from=version.effective_from,
            created_at=version.created_at,
            **config_fields(version),  # type: ignore[arg-type]
        )


class HabitRead(HabitConfigRead):
    """A habit with its current configuration."""

    id: int
    is_archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_version: VersionSummary

    @classmethod
    def from_model(cls, habit: Habit) -> HabitRead:
        version = habit.current_version
        return cls(
            id=habit.id,
            is_archived=habit.is_archived,
            archived_at=habit.archived_at,
            created_at=habit.created_at,
            updated_at=habit.updated_at,
            current_version=VersionSummary.from_model(version),
            **config_fields(version),  # type: ignore[arg-type]
        )
