"""Frozen v1 wire contract. Never derive an old backup schema from live ORM columns."""

from datetime import date, datetime
import re
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID = Annotated[int, Field(gt=0, le=9223372036854775807)]
Nonnegative = Annotated[int, Field(ge=0, le=9223372036854775807)]
Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def timestamp_precision(cls, value, info):
        annotation = cls.model_fields[info.field_name].annotation
        types = (annotation, *get_args(annotation))
        if datetime in types and isinstance(value, str):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)?", value):
                raise ValueError("expected ISO UTC datetime with at most six decimal places")
            return datetime.fromisoformat(value)
        if date in types and isinstance(value, str):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("expected ISO date")
            return date.fromisoformat(value)
        return value

    @field_validator("*", mode="after")
    @classmethod
    def exact_datetime(cls, value):
        # SQLite stores naive UTC; accepting offsets would silently drop them.
        if isinstance(value, datetime) and value.tzinfo is not None:
            if value.utcoffset().total_seconds() != 0:
                raise ValueError("datetime must use UTC")
            return value.replace(tzinfo=None)
        return value


class Row(StrictModel):
    id: ID
    created_at: datetime


class UpdatedRow(Row):
    updated_at: datetime


class Lifecycle(UpdatedRow):
    is_archived: bool
    archived_at: datetime | None


class AreaRow(Lifecycle):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class HabitRow(Lifecycle):
    pass


class VersionRow(Row):
    habit_id: ID
    version_number: ID
    effective_from: date
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: str | None
    area_id: ID
    weight: Annotated[int, Field(ge=1, le=3)]
    tracking_mode: Literal["binary", "binary_quantity"]
    quantity_unit: Annotated[str, Field(min_length=1, max_length=32)] | None
    quantity_allows_decimal: bool
    schedule_type: Literal["daily", "weekdays", "times_per_week"]
    schedule_weekdays: list[Annotated[int, Field(ge=0, le=6)]] | None
    schedule_times_per_week: Annotated[int, Field(ge=1, le=7)] | None


class EntryRow(UpdatedRow):
    habit_id: ID
    entry_date: date
    status: Literal["done", "missed", "skipped"]
    quantity_value_micro: Annotated[int, Field(ge=0, le=1000000000000)] | None
    skip_reason: Annotated[str, Field(min_length=1, max_length=200)] | None
    note: Annotated[str, Field(min_length=1, max_length=500)] | None


class StateRow(UpdatedRow):
    state_date: date
    mood: Annotated[int, Field(ge=1, le=5)] | None
    energy: Annotated[int, Field(ge=1, le=5)] | None
    wellbeing: Annotated[int, Field(ge=1, le=5)] | None
    sleep_status: Literal["underslept", "normal", "overslept"] | None
    sleep_minutes: Annotated[int, Field(ge=0, le=1440)] | None
    alcohol: bool | None
    alcohol_detail: Annotated[str, Field(min_length=1, max_length=200)] | None
    gaming: bool | None
    gaming_minutes: Annotated[int, Field(ge=0, le=1440)] | None
    computer_overuse: bool | None
    computer_minutes: Annotated[int, Field(ge=0, le=1440)] | None
    note: Annotated[str, Field(min_length=1, max_length=500)] | None


class ExperimentRow(UpdatedRow):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    hypothesis: Annotated[str, Field(min_length=1, max_length=2000)]
    protocol: Annotated[str, Field(min_length=1, max_length=2000)]
    start_date: date
    end_date: date
    cancelled_on: date | None


class SnapshotRow(UpdatedRow):
    fingerprint: Annotated[str, Field(min_length=1, max_length=64)]
    evaluated_on: date
    period_start: date
    period_end: date
    x_key: Annotated[str, Field(min_length=1, max_length=160)]
    y_key: Annotated[str, Field(min_length=1, max_length=160)]
    x_label: Annotated[str, Field(min_length=1, max_length=160)]
    y_label: Annotated[str, Field(min_length=1, max_length=160)]
    grain: Literal["daily", "weekly"]
    lag: Annotated[int, Field(ge=-365, le=365)]
    lag_unit: Literal["day", "week"] | None
    orientation: Literal["same_period", "x_earlier", "x_later"]
    relationship_method: Literal["pearson", "spearman", "point_biserial", "phi"] | None
    coefficient: Annotated[float, Field(ge=-1, le=1)] | None
    n: Nonnegative
    pair_coverage: Annotated[float, Field(ge=0, le=1)] | None
    confidence: Literal["preliminary", "stable", "well_supported"] | None
    guardrail_verdict: Literal["pass", "pass_with_warnings", "blocked", "not_evaluable"]
    presentation_status: Literal["preliminary", "stable", "well_supported", "warning", "hidden", "not_evaluable"]
    blocking_reasons: list[str]
    warnings: list[str]
    statement: str
    insight_policy_version: Text
    guardrail_policy_version: Text
    confidence_policy_version: Text
    template_version: Text


class BackupDataV1(StrictModel):
    areas: list[AreaRow]
    habits: list[HabitRow]
    habit_versions: list[VersionRow]
    habit_entries: list[EntryRow]
    daily_states: list[StateRow]
    experiments: list[ExperimentRow]
    insight_snapshots: list[SnapshotRow]


class ManifestV1(StrictModel):
    format: Literal["tracker-backup"]
    version: Literal[1]
    created_at: datetime
    alembic_revision: str
    application_backup_version: Literal[1]
    counts: dict[str, Nonnegative]


class BackupPreview(StrictModel):
    manifest: ManifestV1
    validation_token: str
    expires_in_seconds: int
