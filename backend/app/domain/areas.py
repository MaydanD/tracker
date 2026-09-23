"""Area rules.

An Area is a broad, persistent life sphere (Health, Development, Work,
Household). Users are expected to keep 4–6 of them, so names must be unique
among *active* areas and colours must be usable for grouping in the UI.
"""

from __future__ import annotations

import re

from app.domain.errors import InvalidAreaColorError, InvalidAreaNameError

NAME_MAX_LENGTH = 80
COLOR_PATTERN = re.compile(r"^#[0-9a-f]{6}$")

# Offered as the default when a caller does not pick a colour.
DEFAULT_AREA_COLOR = "#4a7cc7"


def normalise_area_name(name: str) -> str:
    """Trim and validate an area name."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise InvalidAreaNameError("Enter an area name.")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise InvalidAreaNameError(
            f"An area name can be at most {NAME_MAX_LENGTH} characters."
        )
    return cleaned


def normalise_area_color(color: str | None) -> str:
    """Validate a ``#rrggbb`` colour and normalise it to lower case."""
    cleaned = (color or "").strip().lower()
    if not cleaned:
        return DEFAULT_AREA_COLOR
    if not COLOR_PATTERN.match(cleaned):
        raise InvalidAreaColorError()
    return cleaned


def area_name_key(name: str) -> str:
    """Comparison key used to keep active area names unique, ignoring case."""
    return normalise_area_name(name).casefold()
