"""Product examples and temporal boundaries, independent of ORM and HTTP."""

from datetime import date, timedelta

import pytest

from app.domain.progress import HabitHistory, Version, current_streak, daily_runs, daily_streak_milestones, day_progress, streak_summary, week_bounds, week_habit_progress, week_progress
from app.domain.schedule import Schedule

MON = date(2026, 9, 7)
DAILY = Schedule.create("daily")
WEEKDAYS = Schedule.create("weekdays", weekdays=[0, 2, 4])
WEEKLY = Schedule.create("times_per_week", times_per_week=3)


def history(schedule=DAILY, weight=1, done=(), statuses=None, versions=None, start=MON, archived=None, habit_id=1):
    entries = {MON + timedelta(days=d): "done" for d in done}
    entries.update({MON + timedelta(days=d): s for d, s in (statuses or {}).items()})
    return HabitHistory(habit_id, tuple(versions or [Version(start, "Чтение", weight, schedule)]), entries, archived)


@pytest.mark.parametrize("offset", range(7))
def test_calendar_week(offset):
    assert week_bounds(MON + timedelta(days=offset)) == (MON, MON + timedelta(days=6))
    assert week_bounds(MON + timedelta(days=7))[0] == MON + timedelta(days=7)


@pytest.mark.parametrize("status", [None, "missed", "skipped"])
def test_daily_closed_failure_and_open_today(status):
    h = history(done=[0, 1], statuses={} if status is None else {2: status})
    assert current_streak(h, MON + timedelta(days=2)).current_streak == 2
    assert day_progress((h,), MON + timedelta(days=2)).score == 0
    assert current_streak(h, MON + timedelta(days=3)).current_streak == 0
    assert h.entries.get(MON + timedelta(days=2)) == status


def test_daily_done_extends_streak_and_history_gap_breaks():
    assert current_streak(history(done=[0, 1, 2]), MON + timedelta(days=2)).current_streak == 3
    assert current_streak(history(done=[0, 2, 3]), MON + timedelta(days=3)).current_streak == 2


@pytest.mark.parametrize("schedule", [WEEKDAYS, WEEKLY])
@pytest.mark.parametrize("done", [[0, 2, 4], [1, 3, 5], [0, 1, 2, 3, 4]])
def test_flexible_completion_and_cap(schedule, done):
    h = history(schedule, weight=3, done=done, statuses={6: "skipped"})
    p = week_habit_progress(h, MON, MON + timedelta(days=7))
    assert (p.quota, p.completed_count) == (3, len(done))
    assert (p.completed_weight, p.required_weight, p.score, p.status) == (9, 9, 100, "satisfied")
    assert current_streak(h, MON + timedelta(days=7)).current_streak == 1
    assert p.preferred_weekdays == schedule.weekdays
    assert day_progress((h,), MON).score is None


@pytest.mark.parametrize("schedule", [WEEKDAYS, WEEKLY])
def test_open_week_preserves_streak_then_sunday_monday_breaks(schedule):
    h = history(schedule, done=[0, 1, 2, 7, 8])
    assert current_streak(h, MON + timedelta(days=9)).current_streak == 1
    assert week_habit_progress(h, MON + timedelta(days=9), MON + timedelta(days=9)).status == "pending"
    assert current_streak(h, MON + timedelta(days=13)).current_streak == 1
    assert current_streak(h, MON + timedelta(days=14)).current_streak == 0
    assert week_habit_progress(h, MON + timedelta(days=7), MON + timedelta(days=14)).status == "failed"
    completed = history(schedule, done=[0, 1, 2, 7, 8, 9])
    assert current_streak(completed, MON + timedelta(days=9)).current_streak == 2


def test_no_transfer_across_weeks_or_rolling_window():
    h = history(WEEKLY, done=[4, 5, 6, 7, 8])
    p = week_habit_progress(h, MON + timedelta(days=8), MON + timedelta(days=14))
    assert (p.completed_count, p.status) == (2, "failed")
    assert current_streak(h, MON + timedelta(days=14)).current_streak == 0


def test_exact_daily_weights_and_skip_denominator():
    histories = (history(weight=1, done=[0]), history(weight=3, statuses={0: "missed"}, habit_id=2), history(weight=1, done=[0], habit_id=3))
    p = day_progress(histories, MON)
    assert (p.completed_weight, p.required_weight, p.score) == (2, 5, 40)
    skipped = day_progress((history(weight=3, statuses={0: "skipped"}),), MON)
    assert (skipped.completed_weight, skipped.required_weight, skipped.score) == (0, 3, 0)
    assert skipped.obligations[0].entry_status == "skipped"


def test_mixed_week_exact_weighted_formula():
    histories = (history(weight=1, done=[0, 1]), history(WEEKDAYS, weight=2, done=[1, 3, 5, 6], habit_id=2), history(Schedule.create("times_per_week", times_per_week=4), weight=3, done=[0, 1], habit_id=3))
    p = week_progress(histories, MON, MON + timedelta(days=7))
    assert (p.completed_weight, p.required_weight) == (14, 25)
    assert p.score == pytest.approx(56)


def test_empty_and_before_creation():
    assert day_progress((), MON).score is None
    assert week_progress((), MON, MON).score is None
    h = history(start=MON + timedelta(days=7))
    assert week_progress((h,), MON, MON).score is None
    assert current_streak(h, MON).current_streak == 0


def test_live_week_includes_future_daily_obligations():
    p = week_habit_progress(history(done=[0, 1]), MON, MON + timedelta(days=1))
    assert (p.completed_weight, p.required_weight, p.status) == (2, 7, "pending")


def test_daily_historical_weight_changes_each_day():
    h = history(done=range(7), versions=[Version(MON, "Чтение", 1, DAILY), Version(MON + timedelta(days=2), "Чтение", 3, DAILY)])
    assert day_progress((h,), MON).required_weight == 1
    assert day_progress((h,), MON + timedelta(days=2)).required_weight == 3
    assert week_habit_progress(h, MON, MON + timedelta(days=7)).required_weight == 17


def test_weekly_anchor_preserves_weight_quota_and_preferred_days():
    h = history(done=[1, 3, 5], versions=[Version(MON, "Спорт", 1, WEEKDAYS), Version(MON + timedelta(days=2), "Спорт", 3, Schedule.create("times_per_week", times_per_week=5))])
    p = week_habit_progress(h, MON, MON + timedelta(days=7))
    assert (p.quota, p.required_weight, p.completed_weight, p.preferred_weekdays) == (3, 3, 3, (0, 2, 4))
    following = week_habit_progress(h, MON + timedelta(days=7), MON + timedelta(days=7))
    assert (following.quota, following.required_weight) == (5, 15)


@pytest.mark.parametrize("first,second,daily_days,weekly_days,required", [(DAILY, WEEKLY, 2, 5, 11), (WEEKLY, DAILY, 5, 2, 18)])
def test_schedule_switch_no_double_count(first, second, daily_days, weekly_days, required):
    h = history(done=range(7), versions=[Version(MON, "Спорт", 1, first), Version(MON + timedelta(days=2), "Спорт", 3, second)])
    p = week_habit_progress(h, MON, MON + timedelta(days=7))
    # Reverse switch has 5 daily days at weight 3 plus old weekly quota at 1.
    assert p.required_weight == required
    assert (p.daily_required_count, p.weekly_completed_count, p.completed_count) == (daily_days, weekly_days, 7)
    assert p.completed_weight <= p.required_weight
    assert day_progress((h,), MON + timedelta(days=2)).required_weight == (0 if second == WEEKLY else 3)


def test_creation_midweek_full_quota_no_pre_creation_credit():
    h = history(WEEKLY, done=[0, 1, 5], start=MON + timedelta(days=5))
    p = week_habit_progress(h, MON, MON + timedelta(days=7))
    assert (p.quota, p.completed_count, p.status) == (3, 1, "failed")
    daily = history(start=MON + timedelta(days=5))
    assert week_habit_progress(daily, MON, MON).quota == 2


def test_archive_freezes_daily_history_and_stops_new_obligations():
    h = history(done=[0, 1, 2], archived=MON + timedelta(days=3))
    assert day_progress((h,), MON).score == 100
    assert day_progress((h,), MON + timedelta(days=3)).score is None
    assert week_habit_progress(h, MON, MON + timedelta(days=7)).quota == 3
    assert week_habit_progress(h, MON + timedelta(days=7), MON + timedelta(days=7)) is None
    assert current_streak(h, MON + timedelta(days=40)).current_streak == 3


def test_archive_does_not_forgive_last_failed_day_or_started_week():
    h = history(done=[0], archived=MON + timedelta(days=2))
    assert current_streak(h, MON + timedelta(days=40)).current_streak == 0
    weekly = history(WEEKLY, done=[0, 1], archived=MON + timedelta(days=3))
    assert week_habit_progress(weekly, MON, MON + timedelta(days=7)).status == "failed"
    assert current_streak(weekly, MON + timedelta(days=40)).current_streak == 0


def test_schedule_unit_change_restarts_daily_streak():
    h = history(done=range(10), versions=[Version(MON, "Спорт", 1, WEEKLY), Version(MON + timedelta(days=7), "Спорт", 1, DAILY)])
    streak = current_streak(h, MON + timedelta(days=9))
    assert (streak.current_streak, streak.unit) == (3, "days")


def test_extreme_supported_dates_do_not_overflow():
    h = history(start=date.min)
    assert current_streak(h, date.min).current_streak == 0
    assert week_bounds(date.max)[1] == date.max


def test_year_boundary_and_future_planned_skip():
    assert week_bounds(date(2027, 1, 1)) == (date(2026, 12, 28), date(2027, 1, 3))
    h = history(WEEKLY, done=[0, 1, 2], statuses={7: "skipped"})
    p = week_habit_progress(h, MON + timedelta(days=7), MON + timedelta(days=4))
    assert (p.status, p.required_weight, p.completed_weight) == ("pending", 3, 0)
    assert current_streak(h, MON + timedelta(days=4)).current_streak == 1


def test_multiple_same_week_schedule_changes_keep_one_weekly_component():
    h = history(done=range(7), versions=[
        Version(MON, "Спорт", 1, WEEKLY),
        Version(MON + timedelta(days=2), "Спорт", 3, DAILY),
        Version(MON + timedelta(days=5), "Спорт", 2, WEEKDAYS),
    ])
    p = week_habit_progress(h, MON, MON + timedelta(days=6))
    assert (p.weekly_quota, p.weekly_completed_count, p.daily_completed_count) == (3, 4, 3)
    assert (p.required_weight, p.completed_weight, p.score) == (12, 12, 100)


def test_weekly_excess_cannot_cover_missing_daily_part():
    h = history(done=[0, 1, 2, 3, 4], versions=[
        Version(MON, "Спорт", 1, WEEKLY),
        Version(MON + timedelta(days=5), "Спорт", 1, DAILY),
    ])
    p = week_habit_progress(h, MON, MON + timedelta(days=7))
    assert (p.completed_count, p.quota) == (5, 5)
    assert (p.completed_weight, p.required_weight, p.status) == (3, 5, "failed")


# --- Stage 11: canonical run spans and milestone dating ---------------------


def test_daily_runs_expose_closed_runs_then_the_open_one():
    h = history(done=[0, 1, 2, 5, 6])
    runs = daily_runs(h, MON + timedelta(days=6))
    assert [(r.start, r.end, r.length, r.open) for r in runs] == [
        (MON, MON + timedelta(days=2), 3, False),
        (MON + timedelta(days=5), MON + timedelta(days=6), 2, True),
    ]
    # Today's unrecorded day neither adds nor breaks: a two-day run stays open
    # when evaluated during an unrecorded third day.
    open_run = daily_runs(history(done=[0, 1]), MON + timedelta(days=2))
    assert [(r.start, r.end, r.length, r.open) for r in open_run] == [
        (MON, MON + timedelta(days=1), 2, True)
    ]


def test_daily_runs_absent_for_inactive_or_non_daily_habits():
    assert daily_runs(history(schedule=WEEKLY, done=[0, 1]), MON + timedelta(days=1)) == ()
    archived = history(done=[0, 1], archived=MON + timedelta(days=3))
    runs = daily_runs(archived, MON + timedelta(days=10))
    assert [(r.length, r.end) for r in runs] == [(2, MON + timedelta(days=1))]


def test_streak_milestones_date_the_day_each_target_was_reached():
    h = history(done=range(10))
    milestones = daily_streak_milestones(h, [3, 7, 30], MON + timedelta(days=9))
    assert milestones == {
        3: MON + timedelta(days=2),
        7: MON + timedelta(days=6),
    }


def test_streak_milestones_prefer_the_first_reachable_run():
    h = history(done=[0, 1, 2, 3, 4, 5, 6, 8, 9, 10])
    milestones = daily_streak_milestones(h, [4], MON + timedelta(days=10))
    # The first run reached 4 on day 3, even though a later run also passes it.
    assert milestones[4] == MON + timedelta(days=3)


def test_streak_milestones_agree_with_the_streak_summary():
    h = history(done=[0, 1, 2, 3, 5, 6, 7, 8])
    today = MON + timedelta(days=8)
    milestones = daily_streak_milestones(h, [1, 2, 3, 4, 5], today)
    summary = streak_summary(h, today)
    assert max(milestones) == 4
    # The best closed run is a prefix of the longest run ever reached.
    assert summary.current_streak == 4
    assert summary.previous_best_streak == 4
