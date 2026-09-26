"""Stage 10 experiments domain: lifecycle, windows and phase are pure and exact."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.errors import InvalidExperimentError
from app.domain.experiments import (
    effective_end,
    length_of,
    normalise_text,
    normalise_title,
    phase_for,
    status_of,
    validate_window,
    windows_for,
)

START = date(2026, 9, 1)


def test_one_day_experiment_windows_are_adjacent_and_equal() -> None:
    windows = windows_for(START, START)
    assert (windows.before.start, windows.before.end) == (date(2026, 8, 31), date(2026, 8, 31))
    assert (windows.during.start, windows.during.end) == (START, START)
    assert (windows.after.start, windows.after.end) == (date(2026, 9, 2), date(2026, 9, 2))
    assert length_of(windows.before) == length_of(windows.during) == length_of(windows.after) == 1


@pytest.mark.parametrize("days", [1, 7, 14, 30])
def test_comparable_windows_equal_the_experiment_length(days: int) -> None:
    end = date.fromordinal(START.toordinal() + days - 1)
    windows = windows_for(START, end)
    assert length_of(windows.during) == days
    assert length_of(windows.before) == days
    assert length_of(windows.after) == days
    # before ends the day before during; after starts the day after during.
    assert windows.before.end == date.fromordinal(START.toordinal() - 1)
    assert windows.after.start == date.fromordinal(end.toordinal() + 1)


def test_scheduled_active_completed_status_is_derived_from_dates() -> None:
    end = date(2026, 9, 14)
    assert status_of(START, end, None, date(2026, 8, 20)) == "scheduled"
    assert status_of(START, end, None, START) == "active"
    assert status_of(START, end, None, end) == "active"
    assert status_of(START, end, None, date(2026, 9, 15)) == "completed"


def test_cancellation_wins_over_dates() -> None:
    end = date(2026, 9, 14)
    assert status_of(START, end, date(2026, 9, 5), date(2026, 9, 20)) == "cancelled"


def test_phase_for_scheduled_counts_days_until_start() -> None:
    phase = phase_for(START, date(2026, 9, 14), None, date(2026, 8, 25))
    assert phase.status == "scheduled"
    assert phase.stage == "before"
    assert phase.days_until_start == 7
    assert phase.days_total == 14


def test_phase_for_active_reports_day_index() -> None:
    phase = phase_for(START, date(2026, 9, 14), None, date(2026, 9, 6))
    assert phase.status == "active"
    assert phase.stage == "during"
    assert (phase.day_index, phase.days_total) == (6, 14)


def test_phase_for_completed_reports_after_collection() -> None:
    end = date(2026, 9, 14)
    phase = phase_for(START, end, None, date(2026, 9, 18))
    assert phase.status == "completed"
    assert phase.stage == "after"
    assert phase.days_since_end == 4
    assert (phase.after_collected_days, phase.after_total_days) == (4, 14)


def test_cancellation_shortens_during_and_starts_after_at_cancellation() -> None:
    end = date(2026, 9, 14)
    cancelled = date(2026, 9, 5)
    assert effective_end(START, end, cancelled) == cancelled
    windows = windows_for(START, end, cancelled_on=cancelled)
    assert length_of(windows.during) == 5  # 1..5 Sep
    assert windows.during.end == cancelled
    assert windows.after.start == date(2026, 9, 6)
    assert length_of(windows.after) == 5
    assert length_of(windows.before) == 5


def test_cancellation_after_the_planned_end_does_not_extend_it() -> None:
    end = date(2026, 9, 14)
    assert effective_end(START, end, date(2026, 10, 1)) == end


def test_cancellation_before_start_yields_empty_windows() -> None:
    end = date(2026, 9, 14)
    windows = windows_for(START, end, cancelled_on=date(2026, 8, 20))
    assert length_of(windows.during) == 0
    phase = phase_for(START, end, date(2026, 8, 20), date(2026, 8, 25))
    assert phase.status == "cancelled"
    assert phase.days_total == 0


def test_duration_and_order_are_validated() -> None:
    with pytest.raises(InvalidExperimentError):
        validate_window(date(2026, 9, 10), date(2026, 9, 1))
    with pytest.raises(InvalidExperimentError):
        validate_window(START, date.fromordinal(START.toordinal() + 366))
    validate_window(START, date.fromordinal(START.toordinal() + 365))


def test_text_normalisation_rejects_blank_and_trims() -> None:
    with pytest.raises(InvalidExperimentError):
        normalise_title("   ")
    with pytest.raises(InvalidExperimentError):
        normalise_text("", field="hypothesis")
    assert normalise_title("  Без алкоголя  ") == "Без алкоголя"
