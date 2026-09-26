"""Stage 11 domain: records, history facts and the achievement catalogue.

Pure-data tests: no ORM, no HTTP, no clock. ``today`` is always explicit.
"""

from datetime import date, timedelta

from app.domain.achievements import (
    AchievementMetrics,
    evaluate_achievements,
    recently_achieved,
)
from app.domain.progress import HabitHistory, Version
from app.domain.records import compute_records
from app.domain.schedule import Schedule

MON = date(2026, 9, 7)
DAILY = Schedule.create("daily")
WEEKLY = Schedule.create("times_per_week", times_per_week=3)


def habit(
    *,
    habit_id: int = 1,
    name: str = "Чтение",
    done: tuple[int, ...] | range = (),
    statuses: dict[int, str] | None = None,
    start: date = MON,
    archived: date | None = None,
    schedule: Schedule = DAILY,
    weight: int = 1,
) -> HabitHistory:
    entries = {start + timedelta(days=offset): "done" for offset in done}
    entries.update({
        start + timedelta(days=offset): status for offset, status in (statuses or {}).items()
    })
    return HabitHistory(
        habit_id,
        (Version(start, name, weight, schedule),),
        entries,
        archived,
    )


def metrics(
    *,
    completions: dict[int, tuple[date, ...]] | None = None,
    milestones: dict[int, date] | None = None,
    longest_run: int = 0,
    perfect_day: date | None = None,
    perfect_week: date | None = None,
    tracked: tuple[date, ...] = (),
    states: tuple[date, ...] = (),
    experiments_created: tuple[date, ...] = (),
    experiments_completed: tuple[date, ...] = (),
    stable: date | None = None,
    well_supported: date | None = None,
) -> AchievementMetrics:
    return AchievementMetrics(
        completions_by_habit=completions or {},
        streak_milestones=milestones or {},
        longest_daily_run=longest_run,
        perfect_day_on=perfect_day,
        perfect_week_on=perfect_week,
        tracked_days=tracked,
        state_days=states,
        experiments_created_on=experiments_created,
        experiments_completed_on=experiments_completed,
        stable_insight_on=stable,
        well_supported_insight_on=well_supported,
    )


def by_key(achievements, key: str):
    return next(item for item in achievements if item.key == key)


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def test_no_history_yields_an_empty_bundle():
    bundle = compute_records((), today=MON)
    assert bundle.longest_streak is None
    assert bundle.best_day is None
    assert bundle.best_week is None
    assert bundle.most_completed is None
    assert bundle.consistency == ()
    assert bundle.summary.tracked_days == 0
    assert bundle.summary.first_tracked_day is None
    assert bundle.summary.habit_completions == 0
    assert bundle.facts.tracked_days == ()


def test_best_day_keeps_the_earliest_tie_and_ignores_empty_days():
    histories = (habit(done=[0, 1, 2]),)
    bundle = compute_records(histories, today=MON + timedelta(days=5))
    assert bundle.best_day is not None
    assert bundle.best_day.day == MON
    assert bundle.best_day.score == 100
    assert bundle.best_day.ties == 3
    # A day with no obligations never becomes the "best day".
    assert bundle.best_day.required_weight == 1


def test_most_completed_counts_habits_not_weight():
    histories = (
        habit(habit_id=1, done=[0], weight=3),
        habit(habit_id=2, name="Зарядка", done=[0], weight=1),
        habit(habit_id=3, name="Вода", statuses={0: "missed"}, weight=1),
    )
    bundle = compute_records(histories, today=MON)
    assert bundle.most_completed is not None
    assert bundle.most_completed.day == MON
    assert bundle.most_completed.completed_count == 2
    assert bundle.most_completed.required_count == 3


def test_best_week_excludes_the_current_week_and_needs_coverage():
    # Week Mon..Sun fully completed, evaluated the following Monday.
    histories = (habit(done=range(7)),)
    bundle = compute_records(histories, today=MON + timedelta(days=7))
    assert bundle.best_week is not None
    assert bundle.best_week.week_start == MON
    assert bundle.best_week.week_end == MON + timedelta(days=6)
    assert bundle.best_week.score == 100
    assert bundle.best_week.observed_days == 7

    # The same week, evaluated mid-week, is not yet a comparable record.
    mid_week = compute_records(histories, today=MON + timedelta(days=3))
    assert mid_week.best_week is None


def test_best_week_requires_enough_observed_days():
    # Only two of seven days recorded: the week is too thin to be a record.
    histories = (habit(done=[0, 1]),)
    bundle = compute_records(histories, today=MON + timedelta(days=7))
    assert bundle.best_week is None


def test_longest_streak_survives_archiving():
    archived = habit(done=range(5), archived=MON + timedelta(days=7))
    bundle = compute_records((archived,), today=MON + timedelta(days=20))
    record = bundle.longest_streak
    assert record is not None
    assert (record.best_streak, record.unit) == (5, "days")
    assert record.best_start == MON
    assert record.best_end == MON + timedelta(days=4)
    assert record.archived is True


def test_longest_streak_picks_the_strongest_habit():
    histories = (
        habit(habit_id=1, name="Чтение", done=range(3)),
        habit(habit_id=2, name="Зарядка", done=range(6)),
    )
    bundle = compute_records(histories, today=MON + timedelta(days=5))
    assert bundle.longest_streak is not None
    assert bundle.longest_streak.habit_id == 2
    assert bundle.longest_streak.best_streak == 6


def test_consistency_needs_a_fully_elapsed_month_with_enough_obligations():
    full_month = habit(name="Чтение", done=range(30), start=date(2026, 9, 1))
    bundle = compute_records((full_month,), today=date(2026, 10, 5))
    assert len(bundle.consistency) == 1
    best = bundle.consistency[0]
    assert (best.period_start, best.period_end) == (date(2026, 9, 1), date(2026, 9, 30))
    assert (best.done_days, best.obligation_days) == (30, 30)
    assert best.ratio == 100

    # A habit that started on the 25th only has six obligations: below the floor.
    short = habit(name="Вода", done=range(6), start=date(2026, 9, 25))
    assert compute_records((short,), today=date(2026, 10, 5)).consistency == ()

    # The current, unfinished month is never a record.
    assert compute_records((full_month,), today=date(2026, 9, 30)).consistency == ()


def test_tracked_days_union_entries_and_states_ignores_the_future():
    histories = (habit(done=[0], statuses={1: "skipped", 9: "skipped"}),)
    state_days = (MON + timedelta(days=1), MON + timedelta(days=5))
    bundle = compute_records(histories, today=MON + timedelta(days=5), state_days=state_days)
    assert bundle.summary.tracked_days == 3
    assert bundle.summary.first_tracked_day == MON
    assert bundle.facts.tracked_days == (
        MON, MON + timedelta(days=1), MON + timedelta(days=5)
    )
    # A recorded skip still counts as tracked; it is a real record, not a gap.
    assert bundle.summary.habit_completions == 1


def test_perfect_day_and_week_dates_come_from_the_history():
    histories = (habit(done=range(7)),)
    bundle = compute_records(histories, today=MON + timedelta(days=7))
    assert bundle.facts.perfect_day_on == MON
    assert bundle.facts.perfect_week_on == MON


# --------------------------------------------------------------------------- #
# Achievements
# --------------------------------------------------------------------------- #


def test_no_history_leaves_every_achievement_locked():
    achievements = evaluate_achievements(metrics(), today=MON)
    assert achievements
    assert all(not item.achieved for item in achievements)
    assert all(item.achieved_on is None for item in achievements)


def test_exact_threshold_and_historical_date():
    reached = MON + timedelta(days=6)
    achievements = evaluate_achievements(
        metrics(milestones={7: reached}, longest_run=7), today=MON + timedelta(days=30)
    )
    streak = by_key(achievements, "streak_7")
    assert streak.achieved is True
    assert streak.achieved_on == reached
    assert (streak.current, streak.target) == (7, 7)

    # One day short: still locked, and the progress reflects the real best run.
    short = evaluate_achievements(
        metrics(milestones={}, longest_run=6), today=MON + timedelta(days=30)
    )
    assert by_key(short, "streak_7").achieved is False
    assert by_key(short, "streak_7").current == 6


def test_habit_completion_counts_come_from_the_strongest_habit():
    days = tuple(MON + timedelta(days=offset) for offset in range(50))
    achievements = evaluate_achievements(
        metrics(completions={1: days}), today=MON + timedelta(days=60)
    )
    fifty = by_key(achievements, "habit_50_completions")
    assert fifty.achieved is True
    assert fifty.achieved_on == days[49]
    hundred = by_key(achievements, "habit_100_completions")
    assert hundred.achieved is False
    assert (hundred.current, hundred.target) == (50, 100)


def test_tracked_and_state_milestones_use_the_nth_day():
    tracked = tuple(MON + timedelta(days=offset) for offset in range(30))
    states = tuple(MON + timedelta(days=offset) for offset in range(100))
    achievements = evaluate_achievements(
        metrics(tracked=tracked, states=states), today=MON + timedelta(days=200)
    )
    assert by_key(achievements, "tracked_30_days").achieved_on == tracked[29]
    assert by_key(achievements, "tracked_100_days").achieved is False
    assert by_key(achievements, "daily_state_30").achieved_on == states[29]
    assert by_key(achievements, "daily_state_100").achieved_on == states[99]


def test_experiment_and_insight_milestones():
    first_created = MON
    completed = (MON + timedelta(days=14), MON + timedelta(days=28),
                 MON + timedelta(days=42), MON + timedelta(days=56),
                 MON + timedelta(days=70))
    stable = MON + timedelta(days=3)
    achievements = evaluate_achievements(
        metrics(
            experiments_created=(first_created,),
            experiments_completed=completed,
            stable=stable,
            well_supported=None,
        ),
        today=MON + timedelta(days=80),
    )
    assert by_key(achievements, "first_experiment").achieved_on == first_created
    assert by_key(achievements, "first_completed_experiment").achieved_on == completed[0]
    assert by_key(achievements, "experiments_5").achieved_on == completed[4]
    assert by_key(achievements, "first_stable_insight").achieved_on == stable
    assert by_key(achievements, "first_well_supported_insight").achieved is False


def test_ordering_is_deterministic_achieved_then_closest_locked():
    achievements = evaluate_achievements(
        metrics(
            completions={1: (MON,)},
            experiments_created=(MON + timedelta(days=1),),
            tracked=tuple(MON + timedelta(days=offset) for offset in range(20)),
        ),
        today=MON + timedelta(days=20),
    )
    keys = [item.key for item in achievements]
    assert keys[:2] == ["first_experiment", "first_habit_completion"]
    # Locked ones follow, ordered by how close they are to their target.
    locked = keys[2:]
    assert locked[0] == "tracked_30_days"
    # Re-evaluating must produce the identical order.
    again = evaluate_achievements(
        metrics(
            completions={1: (MON,)},
            experiments_created=(MON + timedelta(days=1),),
            tracked=tuple(MON + timedelta(days=offset) for offset in range(20)),
        ),
        today=MON + timedelta(days=20),
    )
    assert [item.key for item in again] == keys


def test_recently_achieved_uses_the_injected_today():
    achievements = evaluate_achievements(
        metrics(completions={1: (MON,)}, stable=MON + timedelta(days=40)),
        today=MON + timedelta(days=45),
    )
    recent = recently_achieved(achievements, today=MON + timedelta(days=45))
    assert [item.key for item in recent] == ["first_stable_insight"]
    assert recently_achieved(achievements, today=MON + timedelta(days=60)) == ()


def test_achieved_threshold_without_a_historical_date_is_allowed():
    # A weekly-quota streak can be true without a recoverable day-level date.
    achievements = evaluate_achievements(
        metrics(longest_run=10, milestones={}), today=MON
    )
    streak = by_key(achievements, "streak_7")
    assert streak.achieved is True
    assert streak.achieved_on is None
