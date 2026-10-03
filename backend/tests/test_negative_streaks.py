from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.domain.progress import (
    HabitHistory, Version, current_streak, daily_streak_milestones,
    day_progress, streak_summary, week_habit_progress,
)
from app.domain.records import compute_records
from app.domain.schedule import Schedule


MON = date(2026, 9, 7)


def negative_history(values, *, schedule=None, kind='ordinal_4'):
    return HabitHistory(
        habit_id=1,
        versions=(Version(
            MON, 'Алкоголь', 1, schedule or Schedule.create('daily'),
            tracks_value=True, value_type=kind, direction='negative',
        ),),
        entries={MON + timedelta(days=i): 'done' for i, value in enumerate(values) if value is not None},
        values={MON + timedelta(days=i): value for i, value in enumerate(values) if value is not None},
    )


@pytest.mark.parametrize('kind,value', [('binary', 1), ('ordinal_4', 1), ('ordinal_4', 2), ('ordinal_4', 3)])
def test_negative_nonzero_breaks_today_but_is_still_a_filled_answer(kind, value):
    habit = negative_history([0, 0, value], kind=kind)
    today = MON + timedelta(days=2)
    summary = streak_summary(habit, today)
    assert summary.current_streak == 0
    assert summary.previous_best_streak == 2
    assert day_progress((habit,), today).filled_count == 1
    assert day_progress((habit,), today).score == pytest.approx((1 - value / (1 if kind == 'binary' else 3)) * 100)


def test_zero_extends_missing_today_preserves_and_historical_gap_breaks():
    habit = negative_history([0, 0, None, 0])
    assert current_streak(habit, MON + timedelta(days=1)).current_streak == 2
    assert current_streak(habit, MON + timedelta(days=2)).current_streak == 2
    assert current_streak(habit, MON + timedelta(days=3)).current_streak == 1
    cleared = replace(habit, entries={MON: 'done'}, values={MON: 0})
    assert current_streak(cleared, MON + timedelta(days=2)).current_streak == 0


def test_negative_records_and_milestones_follow_zero_runs():
    habit = negative_history([0, 0, 0, 2, 0, 0])
    today = MON + timedelta(days=5)
    assert current_streak(habit, today).current_streak == 2
    assert daily_streak_milestones(habit, [3, 4], today) == {3: MON + timedelta(days=2)}
    record = compute_records((habit,), today=today).longest_streak
    assert record is not None
    assert (record.current_streak, record.best_streak) == (2, 3)


def test_direction_changes_use_each_dates_configuration():
    habit = negative_history([2, 1, 0, 1, 0])
    habit = replace(habit, versions=(
        replace(habit.versions[0], direction='positive'),
        replace(habit.versions[0], effective_from=MON + timedelta(days=2)),
    ))
    assert current_streak(habit, MON + timedelta(days=2)).current_streak == 3
    assert current_streak(habit, MON + timedelta(days=3)).current_streak == 0
    assert current_streak(habit, MON + timedelta(days=4)).current_streak == 1


@pytest.mark.parametrize('schedule', [
    Schedule.create('times_per_week', times_per_week=3),
    Schedule.create('weekdays', weekdays=[0, 2, 4]),
])
def test_weekly_streak_uses_zero_quota_without_changing_recorded_counts_or_score(schedule):
    habit = negative_history([0, 0, 1, 0, None, None, None, 0, 1, 1], schedule=schedule)
    assert current_streak(habit, MON + timedelta(days=2)).current_streak == 0
    assert current_streak(habit, MON + timedelta(days=3)).current_streak == 1
    assert current_streak(habit, MON + timedelta(days=9)).current_streak == 1
    assert current_streak(habit, MON + timedelta(days=14)).current_streak == 0
    progress = week_habit_progress(habit, MON + timedelta(days=7), MON + timedelta(days=14))
    assert progress.weekly_completed_count == 3
    assert progress.weekly_streak_count == 1
    assert progress.score == pytest.approx((1 + 2/3 + 2/3) / 3 * 100)
