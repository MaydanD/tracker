"""The configuration-history decision rule, tested without a database."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.errors import ConfigurationHistoryError
from app.domain.habits import HabitConfig
from app.domain.history import (
    EffectiveConfiguration,
    VersionAction,
    plan_version_change,
)
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode

JANUARY_1 = date(2026, 1, 1)
JANUARY_2 = date(2026, 1, 2)
DECEMBER_31 = date(2025, 12, 31)


def config(*, name: str = "Reading", weight: int = 1) -> HabitConfig:
    return HabitConfig.create(
        name=name,
        area_id=1,
        weight=weight,
        tracking_mode=TrackingMode.BINARY,
        schedule=Schedule.create("daily"),
    )


def current(*, config_value: HabitConfig, effective_from: date) -> EffectiveConfiguration:
    return EffectiveConfiguration(
        version_number=1, effective_from=effective_from, config=config_value
    )


def test_first_configuration_creates_the_first_version() -> None:
    action = plan_version_change(
        current=None, new_config=config(), effective_date=JANUARY_1
    )

    assert action is VersionAction.CREATE_NEW


def test_identical_configuration_is_a_no_op() -> None:
    action = plan_version_change(
        current=current(config_value=config(), effective_from=JANUARY_1),
        new_config=config(),
        effective_date=JANUARY_2,
    )

    assert action is VersionAction.NO_CHANGE


def test_identical_configuration_on_the_same_day_is_a_no_op() -> None:
    action = plan_version_change(
        current=current(config_value=config(), effective_from=JANUARY_1),
        new_config=config(),
        effective_date=JANUARY_1,
    )

    assert action is VersionAction.NO_CHANGE


def test_change_on_the_same_day_replaces_that_days_version() -> None:
    """One version per habit per calendar day, so same-day edits update it."""
    action = plan_version_change(
        current=current(config_value=config(weight=1), effective_from=JANUARY_1),
        new_config=config(weight=2),
        effective_date=JANUARY_1,
    )

    assert action is VersionAction.REPLACE_CURRENT


def test_change_on_a_later_day_creates_a_new_version() -> None:
    action = plan_version_change(
        current=current(config_value=config(weight=1), effective_from=JANUARY_1),
        new_config=config(weight=2),
        effective_date=JANUARY_2,
    )

    assert action is VersionAction.CREATE_NEW


def test_change_before_the_current_version_is_rejected() -> None:
    """History is append-only: an earlier change would rewrite existing meaning."""
    with pytest.raises(ConfigurationHistoryError):
        plan_version_change(
            current=current(config_value=config(weight=1), effective_from=JANUARY_1),
            new_config=config(weight=2),
            effective_date=DECEMBER_31,
        )
