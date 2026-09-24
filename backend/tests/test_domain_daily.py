"""Daily entry rules, tested without a database.

These are the rules that decide what the user may record for a habit on a day.
They are pure functions, so the whole truth table can be checked here rather than
through the API.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.daily import (
    MAX_QUANTITY,
    MAX_SCALED_QUANTITY,
    QUANTITY_DECIMAL_PLACES,
    QUANTITY_SCALE,
    Quantity,
    coerce_status,
    validate_entry,
)
from app.domain.errors import (
    FutureEntryError,
    InvalidEntryStatusError,
    InvalidNoteError,
    InvalidQuantityValueError,
    InvalidSkipReasonError,
    QuantityDecimalNotAllowedError,
    QuantityNotAllowedError,
    SkipReasonNotAllowedError,
    SkipReasonRequiredError,
)
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode

TODAY = date(2026, 9, 24)


def binary_config(**overrides: object) -> HabitConfig:
    values: dict[str, object] = {
        "name": "Meditate",
        "area_id": 1,
        "weight": 1,
        "tracking_mode": TrackingMode.BINARY,
        "schedule": Schedule.create("daily"),
    }
    values.update(overrides)
    return HabitConfig.create(**values)  # type: ignore[arg-type]


def quantity_config(*, allows_decimal: bool) -> HabitConfig:
    return binary_config(
        name="Reading",
        tracking_mode=TrackingMode.BINARY_QUANTITY,
        quantity_unit="pages",
        quantity_allows_decimal=allows_decimal,
    )


def entry(**overrides: object):
    values: dict[str, object] = {
        "configuration": binary_config(),
        "status": "done",
        "entry_date": TODAY,
        "today": TODAY,
    }
    values.update(overrides)
    return validate_entry(**values)  # type: ignore[arg-type]


class TestQuantityStorage:
    """Quantity is exact: it never goes through a binary float."""

    def test_a_decimal_value_survives_a_round_trip(self) -> None:
        assert Quantity.parse(6.4).value == Decimal("6.4")
        assert repr(Quantity.parse(6.4).value) == "Decimal('6.4')"

    def test_whole_numbers_have_no_trailing_zeros(self) -> None:
        assert repr(Quantity.parse(35).value) == "Decimal('35')"
        assert repr(Quantity.parse(35.0).value) == "Decimal('35')"

    def test_the_stored_form_is_an_integer_number_of_millionths(self) -> None:
        assert Quantity.parse(6.4).scaled == 6_400_000
        assert Quantity.parse(35).scaled == 35_000_000

    def test_a_whole_value_is_recognised_as_whole(self) -> None:
        assert Quantity.parse(35).is_whole is True
        assert Quantity.parse(6.4).is_whole is False

    def test_precision_within_the_scale_is_preserved(self) -> None:
        assert Quantity.parse("0.000001").value == Decimal("0.000001")
        assert Quantity.parse(0.125).value == Decimal("0.125")
        # The stored integer is exact for every place the scale allows, and
        # reading it back gives the same decimal the user typed.
        for text in ("6.4", "42.195", "0.000001", "999999.999999", "1.234567"):
            quantity = Quantity.parse(text)
            assert quantity.value == Decimal(text)
            assert Quantity(quantity.scaled).value == Decimal(text)

    def test_the_scaled_form_stays_inside_the_column_range(self) -> None:
        """The upper bound must not overflow a signed 64-bit integer column."""
        assert MAX_SCALED_QUANTITY == int(MAX_QUANTITY * QUANTITY_SCALE)
        assert MAX_SCALED_QUANTITY < 2**63
        assert Quantity.parse(MAX_QUANTITY).scaled == MAX_SCALED_QUANTITY

    def test_zero_is_a_recorded_value(self) -> None:
        assert Quantity.parse(0).value == Decimal("0")


class TestQuantityRejection:
    @pytest.mark.parametrize("value", [-1, -0.5, "-3"])
    def test_negative_values_are_rejected(self, value: object) -> None:
        with pytest.raises(InvalidQuantityValueError):
            Quantity.parse(value)

    def test_more_precision_than_the_scale_is_rejected_not_rounded(self) -> None:
        with pytest.raises(InvalidQuantityValueError):
            Quantity.parse("1.2345678")

    @pytest.mark.parametrize("value", ["abc", "", None, True, [], {}, float("nan")])
    def test_non_numeric_input_is_rejected(self, value: object) -> None:
        with pytest.raises(InvalidQuantityValueError):
            Quantity.parse(value)

    def test_an_absurd_value_is_rejected(self) -> None:
        with pytest.raises(InvalidQuantityValueError):
            Quantity.parse(MAX_QUANTITY + 1)

    def test_the_scale_is_documented_by_a_constant(self) -> None:
        assert QUANTITY_DECIMAL_PLACES == 6
        assert QUANTITY_SCALE == 10**6


class TestQuantityAgainstTrackingMode:
    def test_a_binary_habit_rejects_a_quantity(self) -> None:
        with pytest.raises(QuantityNotAllowedError):
            entry(configuration=binary_config(), quantity_value=5)

    def test_a_quantity_habit_accepts_a_quantity(self) -> None:
        values = entry(configuration=quantity_config(allows_decimal=False), quantity_value=35)

        assert values.quantity is not None
        assert values.quantity.value == Decimal("35")

    def test_a_quantity_habit_accepts_no_quantity(self) -> None:
        values = entry(configuration=quantity_config(allows_decimal=True), quantity_value=None)

        assert values.quantity is None

    def test_a_fraction_is_rejected_when_decimals_are_not_allowed(self) -> None:
        with pytest.raises(QuantityDecimalNotAllowedError):
            entry(configuration=quantity_config(allows_decimal=False), quantity_value=6.4)

    def test_a_fraction_is_accepted_when_decimals_are_allowed(self) -> None:
        values = entry(configuration=quantity_config(allows_decimal=True), quantity_value=6.4)

        assert values.quantity is not None
        assert values.quantity.value == Decimal("6.4")

    def test_a_whole_value_is_accepted_even_without_decimal_support(self) -> None:
        values = entry(configuration=quantity_config(allows_decimal=False), quantity_value=35.0)

        assert values.quantity is not None
        assert values.quantity.value == Decimal("35")


class TestStatuses:
    @pytest.mark.parametrize("status", ["done", "missed", "skipped"])
    def test_every_status_is_known(self, status: str) -> None:
        assert coerce_status(status).value == status

    def test_an_unknown_status_is_rejected(self) -> None:
        with pytest.raises(InvalidEntryStatusError):
            coerce_status("maybe")

    @pytest.mark.parametrize("status", ["done", "missed", "skipped"])
    def test_today_accepts_every_status(self, status: str) -> None:
        values = entry(
            status=status,
            entry_date=TODAY,
            skip_reason="Поездка" if status == "skipped" else None,
        )

        assert values.status.value == status

    @pytest.mark.parametrize("status", ["done", "missed"])
    def test_the_past_accepts_done_and_missed(self, status: str) -> None:
        values = entry(status=status, entry_date=TODAY - timedelta(days=30))

        assert values.status.value == status


class TestFutureRules:
    @pytest.mark.parametrize("status", ["done", "missed"])
    def test_a_future_date_rejects_done_and_missed(self, status: str) -> None:
        with pytest.raises(FutureEntryError):
            entry(status=status, entry_date=TODAY + timedelta(days=1))

    def test_a_future_date_accepts_a_planned_skip(self) -> None:
        values = entry(
            status="skipped",
            entry_date=TODAY + timedelta(days=3),
            skip_reason="Отпуск",
        )

        assert values.status.value == "skipped"
        assert values.skip_reason == "Отпуск"

    def test_the_rule_compares_calendar_dates_not_timestamps(self) -> None:
        """A skip tomorrow is fine; a done today is fine; the boundary is exact."""
        entry(status="done", entry_date=TODAY)
        entry(status="skipped", entry_date=TODAY + timedelta(days=1), skip_reason="Отпуск")
        with pytest.raises(FutureEntryError):
            entry(status="done", entry_date=TODAY + timedelta(days=1))


class TestSkipReason:
    def test_a_skipped_entry_requires_a_reason(self) -> None:
        with pytest.raises(SkipReasonRequiredError):
            entry(status="skipped")

    def test_a_whitespace_only_reason_is_not_a_reason(self) -> None:
        with pytest.raises(SkipReasonRequiredError):
            entry(status="skipped", skip_reason="   ")

    @pytest.mark.parametrize("status", ["done", "missed"])
    def test_a_reason_is_rejected_for_non_skipped_statuses(self, status: str) -> None:
        with pytest.raises(SkipReasonNotAllowedError):
            entry(status=status, skip_reason="Болезнь")

    def test_a_reason_is_trimmed_and_kept_only_for_skipped(self) -> None:
        values = entry(status="skipped", skip_reason="  поездка  ")

        assert values.skip_reason == "поездка"

    def test_an_over_long_reason_is_rejected(self) -> None:
        with pytest.raises(InvalidSkipReasonError):
            entry(status="skipped", skip_reason="x" * 201)

    def test_a_done_entry_has_no_reason_even_when_blank_text_is_sent(self) -> None:
        assert entry(status="done", skip_reason="   ").skip_reason is None


class TestNotes:
    def test_a_note_is_kept_separately_from_the_status(self) -> None:
        values = entry(note="  тяжело пошло  ")

        assert values.note == "тяжело пошло"
        assert values.skip_reason is None

    def test_a_blank_note_becomes_none(self) -> None:
        assert entry(note="   ").note is None

    def test_a_note_and_a_skip_reason_coexist(self) -> None:
        values = entry(status="skipped", skip_reason="Болезнь", note="Простуда")

        assert values.skip_reason == "Болезнь"
        assert values.note == "Простуда"

    def test_an_over_long_note_is_rejected(self) -> None:
        with pytest.raises(InvalidNoteError):
            entry(note="x" * 501)
