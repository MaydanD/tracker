"""Schedule configuration rules, tested without a database or HTTP layer."""

from __future__ import annotations

import pytest

from app.domain.errors import InvalidScheduleError
from app.domain.schedule import Schedule, ScheduleType


class TestDaily:
    def test_every_day_expects_seven_completions(self) -> None:
        schedule = Schedule.create(ScheduleType.DAILY)

        assert schedule.type is ScheduleType.DAILY
        assert schedule.weekdays == ()
        assert schedule.times_per_week is None
        assert schedule.weekly_required_count == 7
        assert schedule.summary == "Every day"
        assert schedule.stored_weekdays is None
        assert schedule.stored_times_per_week is None

    def test_rejects_weekdays(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("daily", weekdays=[0, 2])

    def test_rejects_an_independent_weekly_quota(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("daily", times_per_week=3)


class TestWeekdays:
    def test_preferred_days_are_ordered_and_drive_the_quota(self) -> None:
        schedule = Schedule.create("weekdays", weekdays=[4, 0, 2])

        assert schedule.weekdays == (0, 2, 4)
        assert schedule.weekly_required_count == 3
        assert schedule.summary == "Mon, Wed, Fri (3 per week)"
        assert schedule.stored_weekdays == [0, 2, 4]
        assert schedule.stored_times_per_week is None

    def test_a_single_weekday_is_a_quota_of_one(self) -> None:
        schedule = Schedule.create("weekdays", weekdays=[6])

        assert schedule.weekly_required_count == 1
        assert schedule.summary == "Sun (1 per week)"

    def test_empty_selection_is_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays", weekdays=[])

    def test_missing_selection_is_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays")

    def test_duplicate_weekdays_are_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays", weekdays=[1, 1])

    @pytest.mark.parametrize("weekday", [-1, 7, 99])
    def test_out_of_range_weekdays_are_rejected(self, weekday: int) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays", weekdays=[weekday])

    def test_an_independent_quota_is_rejected(self) -> None:
        """Mon/Wed/Fri with a quota of 2 would be two sources of truth."""
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays", weekdays=[0, 2, 4], times_per_week=2)

    def test_non_numeric_weekdays_are_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("weekdays", weekdays=["monday"])


class TestTimesPerWeek:
    @pytest.mark.parametrize("times", [1, 3, 7])
    def test_valid_quotas(self, times: int) -> None:
        schedule = Schedule.create("times_per_week", times_per_week=times)

        assert schedule.times_per_week == times
        assert schedule.weekly_required_count == times
        assert schedule.stored_weekdays is None
        assert schedule.stored_times_per_week == times

    def test_summary(self) -> None:
        assert Schedule.create("times_per_week", times_per_week=3).summary == (
            "3 per week"
        )

    @pytest.mark.parametrize("times", [0, -1, 8, 14])
    def test_out_of_range_quotas_are_rejected(self, times: int) -> None:
        """A habit completes at most once per day, so 7 is the ceiling."""
        with pytest.raises(InvalidScheduleError):
            Schedule.create("times_per_week", times_per_week=times)

    def test_missing_quota_is_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("times_per_week")

    def test_preferred_weekdays_are_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("times_per_week", weekdays=[0, 2], times_per_week=3)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "schedule",
        [
            Schedule.create("daily"),
            Schedule.create("weekdays", weekdays=[0, 3, 6]),
            Schedule.create("times_per_week", times_per_week=4),
        ],
    )
    def test_stored_columns_rebuild_the_same_schedule(self, schedule: Schedule) -> None:
        """What is written to the database reproduces the same schedule."""
        rebuilt = Schedule.create(
            schedule.type,
            weekdays=schedule.stored_weekdays,
            times_per_week=schedule.stored_times_per_week,
        )

        assert rebuilt == schedule

    def test_unknown_schedule_type_is_rejected(self) -> None:
        with pytest.raises(InvalidScheduleError):
            Schedule.create("monthly", times_per_week=2)
