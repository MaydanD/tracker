"""Tracking modes and quantity configuration rules.

Quantity is *structured* data, never free text: a habit declares whether it
tracks a quantity and, if so, the unit those numbers are recorded in. Stage 2
stores that configuration; Stage 3 stores the actual per-day values.

Units are free text on purpose (pages, minutes, km, reps, glasses, chapters,
anything the user needs). There is deliberately no unit conversion system and no
fixed unit enum, because converting km to metres or minutes to hours would
invent meaning the user never expressed.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.errors import InvalidQuantityUnitError

QUANTITY_UNIT_MAX_LENGTH = 32


class TrackingMode(StrEnum):
    """How a habit is recorded."""

    BINARY = "binary"
    BINARY_QUANTITY = "binary_quantity"


def normalise_quantity_unit(unit: str | None, *, required: bool) -> str | None:
    """Trim and validate a quantity unit.

    Returns ``None`` when quantity tracking is disabled (any submitted unit is
    discarded, so a binary habit can never keep stale configuration).
    """
    if not required:
        return None

    cleaned = " ".join((unit or "").split())
    if not cleaned:
        raise InvalidQuantityUnitError(
            "Enter a unit (for example pages, minutes, km or reps)."
        )
    if len(cleaned) > QUANTITY_UNIT_MAX_LENGTH:
        raise InvalidQuantityUnitError(
            f"A unit can be at most {QUANTITY_UNIT_MAX_LENGTH} characters."
        )
    return cleaned


def resolve_allows_decimal(*, tracking_mode: TrackingMode, allows_decimal: bool) -> bool:
    """Decimal support only has meaning when a quantity is recorded."""
    if tracking_mode is TrackingMode.BINARY:
        return False
    return bool(allows_decimal)
