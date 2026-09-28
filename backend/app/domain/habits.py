"""Habit configuration value object.

A :class:`HabitConfig` is the complete, immutable description of how a habit is
configured: its name, description, area, weight, tracking mode, quantity unit,
schedule, and — for a habit that is answered with a value — its scale, labels
and direction. Configuration edits create a new :class:`HabitConfig`; they never
mutate an existing one, which is what makes historical configuration
recoverable (see :mod:`app.domain.history`).

Weight keeps the historical score coefficient (1 normal, 2 important, 3 key).
Importance is independent versioned metadata (low/normal/high), default normal.
Direction describes which end of a value scale is good.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import (
    IncompatibleTrackingError,
    InvalidHabitNameError,
    InvalidImportanceError,
    InvalidTrackingModeError,
    InvalidWeightError,
)
from app.domain.schedule import Schedule
from app.domain.tracking import (
    Direction,
    TrackingMode,
    ValueType,
    coerce_direction,
    coerce_value_type,
    normalise_quantity_unit,
    normalise_value_labels,
    resolve_allows_decimal,
)

NAME_MAX_LENGTH = 120

WEIGHT_NORMAL = 1
WEIGHT_IMPORTANT = 2
WEIGHT_KEY = 3
MIN_WEIGHT = WEIGHT_NORMAL
MAX_WEIGHT = WEIGHT_KEY


class Importance(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


DEFAULT_IMPORTANCE = Importance.NORMAL


def validate_weight(weight: object) -> int:
    if type(weight) is not int or not MIN_WEIGHT <= weight <= MAX_WEIGHT:
        raise InvalidWeightError()
    return weight


def coerce_importance(value: object) -> Importance:
    try:
        return Importance(value)
    except (ValueError, TypeError) as exc:
        raise InvalidImportanceError(details={"importance": str(value)}) from exc


def normalise_habit_name(name: str) -> str:
    """Trim and validate a habit name."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise InvalidHabitNameError("Enter a habit name.")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise InvalidHabitNameError(
            f"A habit name can be at most {NAME_MAX_LENGTH} characters."
        )
    return cleaned


def normalise_description(description: str | None) -> str | None:
    """Descriptions are optional; blank input becomes ``None``."""
    if description is None:
        return None
    cleaned = description.strip()
    return cleaned or None


@dataclass(frozen=True, slots=True)
class HabitConfig:
    """A validated, immutable habit configuration.

    ``value_type`` is the one field that decides how a day is answered: ``None``
    means completion (done / missed / skipped, exactly as before), while
    ``binary`` or ``ordinal_4`` means the habit is answered with a value on that
    scale, using ``value_labels`` and read through ``direction``.
    """

    name: str
    description: str | None
    area_id: int
    #: Historical score coefficient; independent of importance.
    weight: int
    tracking_mode: TrackingMode
    quantity_unit: str | None
    quantity_allows_decimal: bool
    schedule: Schedule
    #: ``None`` — completion; otherwise the scale the habit is answered on.
    importance: Importance = DEFAULT_IMPORTANCE
    value_type: ValueType | None = None
    #: One label per value of :attr:`value_type`, in the user's own words.
    value_labels: tuple[str, ...] | None = None
    #: Which end of the value scale is good. ``None`` = not stated.
    direction: Direction | None = None

    @property
    def tracks_value(self) -> bool:
        """Whether a day is answered with a value instead of a completion."""
        return self.value_type is not None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        area_id: int,
        tracking_mode: TrackingMode | str,
        weight: int | None = None,
        importance: Importance | str | None = None,
        schedule: Schedule,
        description: str | None = None,
        quantity_unit: str | None = None,
        quantity_allows_decimal: bool = False,
        value_type: ValueType | str | None = None,
        value_labels: tuple[str, ...] | list[str] | None = None,
        direction: Direction | str | None = None,
    ) -> HabitConfig:
        """Build a configuration, applying every cross-field product rule."""
        try:
            mode = TrackingMode(tracking_mode)
        except ValueError as exc:
            raise InvalidTrackingModeError(
                details={"tracking_mode": str(tracking_mode)}
            ) from exc

        resolved_value_type = (
            None if value_type is None else coerce_value_type(value_type)
        )

        # A quantity and a value scale answer different questions (how much did
        # I read vs. what was my mood), so asking for both is a contradiction
        # rather than extra information.
        if resolved_value_type is not None and mode is TrackingMode.BINARY_QUANTITY:
            raise IncompatibleTrackingError(
                details={"tracking_mode": mode.value, "value_type": resolved_value_type.value}
            )

        # A value habit with no stated direction is neutral, never silently
        # "positive": a guess here would quietly bias a future score.
        resolved_direction = (
            None
            if direction is None and resolved_value_type is None
            else (
                Direction.NEUTRAL
                if direction is None
                else coerce_direction(direction)
            )
        )

        return cls(
            name=normalise_habit_name(name),
            description=normalise_description(description),
            area_id=area_id,
            weight=validate_weight(WEIGHT_NORMAL if weight is None else weight),
            importance=coerce_importance(DEFAULT_IMPORTANCE if importance is None else importance),
            tracking_mode=mode,
            quantity_unit=normalise_quantity_unit(
                quantity_unit, required=mode is TrackingMode.BINARY_QUANTITY
            ),
            quantity_allows_decimal=resolve_allows_decimal(
                tracking_mode=mode, allows_decimal=quantity_allows_decimal
            ),
            schedule=schedule,
            value_type=resolved_value_type,
            value_labels=(
                None
                if resolved_value_type is None
                else normalise_value_labels(resolved_value_type, value_labels)
            ),
            direction=resolved_direction if resolved_value_type is not None else None,
        )
