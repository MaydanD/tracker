"""Habit configuration rules: weights, names and quantity configuration."""

from __future__ import annotations

import pytest

from app.domain.errors import (
    InvalidHabitNameError,
    InvalidQuantityUnitError,
    InvalidTrackingModeError,
    InvalidWeightError,
)
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode


def config(**overrides: object) -> HabitConfig:
    """A minimal valid configuration; override as needed."""
    values: dict[str, object] = {
        "name": "Reading",
        "area_id": 1,
        "weight": 1,
        "tracking_mode": TrackingMode.BINARY,
        "schedule": Schedule.create("daily"),
    }
    values.update(overrides)
    return HabitConfig.create(**values)  # type: ignore[arg-type]


class TestWeight:
    @pytest.mark.parametrize("weight", [1, 2, 3])
    def test_supported_weights(self, weight: int) -> None:
        assert config(weight=weight).weight == weight

    @pytest.mark.parametrize("weight", [0, 4, -1, 10])
    def test_out_of_range_weights_are_rejected(self, weight: int) -> None:
        with pytest.raises(InvalidWeightError):
            config(weight=weight)

    def test_non_integer_weights_are_rejected(self) -> None:
        with pytest.raises(InvalidWeightError):
            config(weight="2")

    def test_boolean_is_not_a_weight(self) -> None:
        with pytest.raises(InvalidWeightError):
            config(weight=True)


class TestNameAndDescription:
    def test_name_is_trimmed(self) -> None:
        assert config(name="  Deep   work  ").name == "Deep work"

    def test_empty_name_is_rejected(self) -> None:
        with pytest.raises(InvalidHabitNameError):
            config(name="   ")

    def test_overlong_name_is_rejected(self) -> None:
        with pytest.raises(InvalidHabitNameError):
            config(name="x" * 121)

    def test_blank_description_becomes_none(self) -> None:
        assert config(description="   ").description is None


class TestTrackingMode:
    def test_binary_habits_have_no_unit(self) -> None:
        habit = config(tracking_mode="binary", quantity_unit="pages")

        assert habit.tracking_mode is TrackingMode.BINARY
        assert habit.quantity_unit is None
        assert habit.quantity_allows_decimal is False

    def test_quantity_habits_require_a_unit(self) -> None:
        with pytest.raises(InvalidQuantityUnitError):
            config(tracking_mode="binary_quantity")

    def test_blank_unit_is_rejected(self) -> None:
        with pytest.raises(InvalidQuantityUnitError):
            config(tracking_mode="binary_quantity", quantity_unit="   ")

    def test_unit_is_trimmed_and_whitespace_collapsed(self) -> None:
        habit = config(
            tracking_mode="binary_quantity", quantity_unit="  km   per  day "
        )

        assert habit.quantity_unit == "km per day"

    def test_overlong_unit_is_rejected(self) -> None:
        with pytest.raises(InvalidQuantityUnitError):
            config(tracking_mode="binary_quantity", quantity_unit="x" * 33)

    def test_decimal_support_is_kept_for_quantity_habits(self) -> None:
        habit = config(
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )

        assert habit.quantity_allows_decimal is True

    def test_decimal_support_is_meaningless_without_a_quantity(self) -> None:
        habit = config(tracking_mode="binary", quantity_allows_decimal=True)

        assert habit.quantity_allows_decimal is False

    def test_unknown_tracking_mode_is_rejected(self) -> None:
        with pytest.raises(InvalidTrackingModeError):
            config(tracking_mode="counter")


class TestEquality:
    def test_identical_configurations_are_equal(self) -> None:
        """Equality is what makes 'no-op save' detection possible."""
        assert config(weight=2) == config(weight=2)

    def test_changed_configurations_are_not_equal(self) -> None:
        assert config(weight=2) != config(weight=3)
        assert config(schedule=Schedule.create("daily")) != config(
            schedule=Schedule.create("times_per_week", times_per_week=3)
        )
