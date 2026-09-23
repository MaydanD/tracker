"""Habit configuration history rule.

Habit settings change over time (weight, schedule, unit, area, name). Rewriting a
single habit row would destroy the meaning of historical records, so Tracker
stores an immutable configuration version per change, effective-dated by calendar
day.

This module holds the decision rule as a pure function so it can be tested
without a database. Only the *latest* version matters, because a new version is
always effective no later than any existing one.

The resulting invariants:

* one version per habit per calendar day (edits on the same day update that
  day's version rather than stacking duplicates);
* a change effective *after* the current version appends a new version;
* a change effective *before* the current version is rejected instead of
  silently rewriting history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.errors import ConfigurationHistoryError
from app.domain.habits import HabitConfig


class VersionAction(StrEnum):
    """What to do with the history when a habit configuration is saved."""

    NO_CHANGE = "no_change"
    """The submitted configuration is identical to the effective one."""

    REPLACE_CURRENT = "replace_current"
    """Update the version already effective on that date."""

    CREATE_NEW = "create_new"
    """Append a new version with a later effective date."""


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    """The configuration that is currently effective for a habit."""

    version_number: int
    effective_from: date
    config: HabitConfig


def plan_version_change(
    *,
    current: EffectiveConfiguration | None,
    new_config: HabitConfig,
    effective_date: date,
) -> VersionAction:
    """Decide how a configuration change should be recorded."""
    if current is None:
        return VersionAction.CREATE_NEW

    if effective_date < current.effective_from:
        raise ConfigurationHistoryError(
            "A configuration change cannot take effect before the current version.",
            details={
                "effective_date": effective_date.isoformat(),
                "current_effective_from": current.effective_from.isoformat(),
            },
        )

    if current.config == new_config:
        return VersionAction.NO_CHANGE

    if effective_date == current.effective_from:
        return VersionAction.REPLACE_CURRENT

    return VersionAction.CREATE_NEW
