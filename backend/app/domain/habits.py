"""Habit configuration value object.

A :class:`HabitConfig` is the complete, immutable description of how a habit is
configured: its name, description, area, weight, tracking mode, quantity unit
and schedule. Configuration edits create a new :class:`HabitConfig`; they never
mutate an existing one, which is what makes historical configuration
recoverable (see :mod:`app.domain.history`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import (
    InvalidHabitNameError,
    InvalidTrackingModeError,
    InvalidWeightError,
)
from app.domain.schedule import Schedule
from app.domain.tracking import (
    TrackingMode,
    normalise_quantity_unit,
    resolve_allows_decimal,
)

NAME_MAX_LENGTH = 120

WEIGHT_NORMAL = 1
WEIGHT_IMPORTANT = 2
WEIGHT_KEY = 3
MIN_WEIGHT = WEIGHT_NORMAL
MAX_WEIGHT = WEIGHT_KEY


def validate_weight(weight: object) -> int:
    """Weights are intentionally coarse: 1 = normal, 2 = important, 3 = key."""
    if isinstance(weight, bool) or not isinstance(weight, int):
        raise InvalidWeightError()
    if not MIN_WEIGHT <= weight <= MAX_WEIGHT:
        raise InvalidWeightError(details={"weight": weight})
    return weight


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
    """A validated, immutable habit configuration."""

    name: str
    description: str | None
    area_id: int
    weight: int
    tracking_mode: TrackingMode
    quantity_unit: str | None
    quantity_allows_decimal: bool
    schedule: Schedule

    @classmethod
    def create(
        cls,
        *,
        name: str,
        area_id: int,
        weight: int,
        tracking_mode: TrackingMode | str,
        schedule: Schedule,
        description: str | None = None,
        quantity_unit: str | None = None,
        quantity_allows_decimal: bool = False,
    ) -> HabitConfig:
        """Build a configuration, applying every cross-field product rule."""
        try:
            mode = TrackingMode(tracking_mode)
        except ValueError as exc:
            raise InvalidTrackingModeError(
                details={"tracking_mode": str(tracking_mode)}
            ) from exc

        return cls(
            name=normalise_habit_name(name),
            description=normalise_description(description),
            area_id=area_id,
            weight=validate_weight(weight),
            tracking_mode=mode,
            quantity_unit=normalise_quantity_unit(
                quantity_unit, required=mode is TrackingMode.BINARY_QUANTITY
            ),
            quantity_allows_decimal=resolve_allows_decimal(
                tracking_mode=mode, allows_decimal=quantity_allows_decimal
            ),
            schedule=schedule,
        )
