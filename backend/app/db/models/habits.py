"""Habit ORM models.

A ``Habit`` row is identity and lifecycle only. Its *configuration* lives in
immutable, effective-dated ``HabitVersion`` rows, so historical records always
stay tied to the settings that were valid when they were recorded.

Why the configuration is not duplicated onto ``habits``: one source of truth
makes drift impossible. "Current configuration" is simply the latest version,
and Stage 4 can answer "what weight applied on date X?" by reading
``habit_versions`` alone.

The only configuration-shaped column on ``habits`` is ``key``: a stable machine
identifier (``body.walk``) carried by the habits Tracker creates for the user on
first start. It exists purely so that reconciliation can recognise its own
records and never duplicate them; a habit created through the UI has no key and
is otherwise exactly the same kind of row.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.areas import Area
from app.domain.habits import HabitConfig, Importance
from app.domain.schedule import Schedule
from app.domain.tracking import Direction, TrackingMode, ValueType


class Habit(Base):
    """A habit the user intends to perform.

    Configuration lives in :attr:`versions`; this row carries identity,
    timestamps and archive state.
    """

    __tablename__ = "habits"
    __table_args__ = (
        # A unique *index*, for the same reason as on ``areas``: SQLite adds an
        # index to a populated table in place, while a UNIQUE constraint would
        # rebuild the table and detach the versions and entries that reference
        # it. NULL (a hand-made habit) is allowed as often as needed.
        Index("uq_habits_key", "key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable machine identifier of a habit Tracker created itself. Never shown,
    # never renamed, and NULL for every habit the user created by hand.
    key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 0 means "no position of its own": ordered by name after the shipped habits
    # of the same area.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # Ordered by effective date, so the last entry is the current configuration.
    # Eager-loaded because every habit response and the habit list need it; the
    # dataset is one user's habits (tens of rows), so a second small query is
    # cheaper than the join gymnastics of projecting "current version" in SQL.
    versions: Mapped[list[HabitVersion]] = relationship(
        back_populates="habit",
        order_by="HabitVersion.effective_from",
        lazy="selectin",
    )

    @property
    def current_version(self) -> HabitVersion:
        """The configuration currently in effect.

        Every habit is created with an initial version, so this is never empty.
        """
        if not self.versions:  # pragma: no cover - guarded by the service layer
            raise LookupError(f"Habit {self.id} has no configuration version.")
        return self.versions[-1]


class HabitVersion(Base):
    """An immutable snapshot of a habit's configuration.

    ``effective_from`` is a *calendar date* (not a UTC timestamp): it decides
    which configuration applied on which day, which is what historical analytics
    need. ``created_at`` records when the change was made in UTC.

    Exactly one version exists per habit per calendar day; same-day edits update
    that day's version (see :mod:`app.domain.history`).
    """

    __tablename__ = "habit_versions"
    __table_args__ = (
        UniqueConstraint("habit_id", "effective_from", name="habit_effective_date"),
        CheckConstraint("weight IN (1, 2, 3)", name="weight_range"),
        CheckConstraint("importance IN ('low', 'normal', 'high')", name="importance_values"),
        CheckConstraint(
            "tracking_mode IN ('binary', 'binary_quantity')",
            name="tracking_mode_values",
        ),
        CheckConstraint(
            "(tracking_mode = 'binary' AND quantity_unit IS NULL) OR "
            "(tracking_mode = 'binary_quantity' AND quantity_unit IS NOT NULL)",
            name="quantity_unit_matches_mode",
        ),
        # A habit either tracks completion (no scale at all) or is answered on a
        # value scale, in which case the scale, its labels and a direction are
        # all present. Half-configured scales cannot be stored.
        CheckConstraint(
            "(value_type IS NULL AND value_labels IS NULL AND direction IS NULL) OR "
            "(value_type IN ('binary', 'ordinal_4') "
            "AND value_labels IS NOT NULL AND direction IS NOT NULL)",
            name="value_scale_shape",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('positive', 'negative', 'neutral')",
            name="direction_values",
        ),
        CheckConstraint(
            "(schedule_type = 'daily' AND schedule_weekdays IS NULL "
            "AND schedule_times_per_week IS NULL) OR "
            "(schedule_type = 'weekdays' AND schedule_weekdays IS NOT NULL "
            "AND schedule_times_per_week IS NULL) OR "
            "(schedule_type = 'times_per_week' AND schedule_weekdays IS NULL "
            "AND schedule_times_per_week BETWEEN 1 AND 7)",
            name="schedule_shape",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    # --- configuration snapshot ---
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_id: Mapped[int] = mapped_column(
        ForeignKey("areas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="normal", server_default="normal")
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity_allows_decimal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # --- value scale (None = the habit is tracked as completion) -----------
    value_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # ``none_as_null=True``: without it SQLAlchemy would persist Python ``None``
    # as the JSON string "null", which would defeat the shape constraint above.
    value_labels: Mapped[list[str] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    schedule_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # ``none_as_null=True`` is required: without it SQLAlchemy persists Python
    # None as the JSON string "null", which would defeat the SQL NULL checks in
    # the schedule-shape constraint above.
    schedule_weekdays: Mapped[list[int] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    schedule_times_per_week: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    habit: Mapped[Habit] = relationship(back_populates="versions")
    # Loaded eagerly: every habit response shows the area name and colour.
    area: Mapped[Area] = relationship(lazy="joined")

    # -- domain conversion --------------------------------------------------

    @property
    def schedule(self) -> Schedule:
        """The stored schedule as a validated domain object."""
        return Schedule.create(
            self.schedule_type,
            weekdays=self.schedule_weekdays,
            times_per_week=self.schedule_times_per_week,
        )

    @property
    def configuration(self) -> HabitConfig:
        """The stored snapshot as a validated domain object."""
        return HabitConfig.create(
            name=self.name,
            description=self.description,
            area_id=self.area_id,
            weight=self.weight,
            importance=self.importance,
            tracking_mode=TrackingMode(self.tracking_mode),
            quantity_unit=self.quantity_unit,
            quantity_allows_decimal=self.quantity_allows_decimal,
            schedule=self.schedule,
            value_type=self.value_type,
            value_labels=self.value_labels,
            direction=self.direction,
        )

    @property
    def value_type_enum(self) -> ValueType | None:
        """The value scale in force, or ``None`` for a completion habit."""
        return None if self.value_type is None else ValueType(self.value_type)
    @property
    def direction_enum(self) -> Direction | None:
        """The stored direction, or ``None`` when none is stated."""
        return None if self.direction is None else Direction(self.direction)

    @property
    def importance_enum(self) -> Importance:
        """Independent metadata stored on this version."""
        return Importance(self.importance)

    @property
    def tracks_value(self) -> bool:
        """Whether this version answers a day with a value, not a completion."""
        return self.value_type is not None

    @classmethod
    def from_config(
        cls,
        *,
        habit_id: int,
        version_number: int,
        effective_from: date,
        config: HabitConfig,
    ) -> HabitVersion:
        """Build a version row from a validated configuration."""
        return cls(
            habit_id=habit_id,
            version_number=version_number,
            effective_from=effective_from,
            name=config.name,
            description=config.description,
            area_id=config.area_id,
            weight=config.weight,
            importance=config.importance.value,
            tracking_mode=config.tracking_mode.value,
            quantity_unit=config.quantity_unit,
            quantity_allows_decimal=config.quantity_allows_decimal,
            value_type=None if config.value_type is None else config.value_type.value,
            value_labels=(
                None if config.value_labels is None else list(config.value_labels)
            ),
            direction=None if config.direction is None else config.direction.value,
            schedule_type=config.schedule.type.value,
            schedule_weekdays=config.schedule.stored_weekdays,
            schedule_times_per_week=config.schedule.stored_times_per_week,
        )

    def apply_config(self, config: HabitConfig) -> None:
        """Overwrite this version's snapshot (same-day edit only).

        Used exclusively for the ``REPLACE_CURRENT`` history action, where the
        version has not yet become historical.
        """
        replacement = HabitVersion.from_config(
            habit_id=self.habit_id,
            version_number=self.version_number,
            effective_from=self.effective_from,
            config=config,
        )
        for field in (
            "name",
            "description",
            "area_id",
            "weight",
            "importance",
            "tracking_mode",
            "quantity_unit",
            "quantity_allows_decimal",
            "value_type",
            "value_labels",
            "direction",
            "schedule_type",
            "schedule_weekdays",
            "schedule_times_per_week",
        ):
            setattr(self, field, getattr(replacement, field))

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return (
            f"<HabitVersion habit={self.habit_id} v{self.version_number} "
            f"from={self.effective_from}>"
        )
