"""Stage 9 Owl domain selector: determinism, scenarios, tone and suppression.

The selector is pure, so every scenario is exercised by constructing an explicit
context: no database, no wall clock, no randomness.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.owl import (
    ASSET_ALL_DONE,
    ASSET_FAILED,
    ASSET_INSIGHT,
    ASSET_MANY_MISSES,
    ASSET_PENDING,
    ASSET_RECORD,
    DashboardContext,
    ExperimentOwlContext,
    InsightFact,
    InsightsContext,
    StreakFact,
    select_dashboard,
    select_experiments,
    select_insights,
)

TODAY = date(2026, 9, 25)


def dashboard(**overrides: object) -> DashboardContext:
    base = dict(
        today=TODAY,
        after_hours=False,
        required_weight=0,
        completed_weight=0,
        unmarked_obligations=0,
        obligation_count=0,
        failed_important=(),
        mood=None,
        wellbeing=None,
        misses_last_window=0,
        coverage_last_window=None,
        streaks=(),
        last_week_score=None,
        last_week_days=0,
        last_week_coverage=None,
        previous_week_score=None,
        previous_week_days=0,
        previous_week_coverage=None,
    )
    base.update(overrides)
    return DashboardContext(**base)  # type: ignore[arg-type]


def insights(**overrides: object) -> InsightsContext:
    base = dict(
        availability="ok",
        availability_message="Найдены наблюдения, которые прошли статистические проверки.",
        hypothesis_count=225,
        max_sample_n=90,
        preliminary_count=0,
        blocked_reason=None,
        stable=None,
    )
    base.update(overrides)
    return InsightsContext(**base)  # type: ignore[arg-type]


def fact(**overrides: object) -> InsightFact:
    base = dict(
        x_label="Энергия",
        y_label="Настроение",
        statement="Эта связь устойчиво повторяется в вашей истории: чем выше был показатель «Энергия».",
        timing="Через три дня",
        lag=3,
    )
    base.update(overrides)
    return InsightFact(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #


def test_all_completed_when_every_obligation_is_done() -> None:
    state = select_dashboard(dashboard(required_weight=3, completed_weight=3))
    assert state is not None
    assert state.owl_id == "all_completed"
    assert state.asset_key == ASSET_ALL_DONE
    assert state.tone == "celebratory"
    assert "100%" in state.caption_line2


def test_pending_is_hidden_before_evening() -> None:
    state = select_dashboard(
        dashboard(unmarked_obligations=2, obligation_count=4, after_hours=False))
    assert state is None


def test_pending_shows_the_real_counter_after_evening() -> None:
    state = select_dashboard(
        dashboard(unmarked_obligations=3, obligation_count=5, after_hours=True))
    assert state is not None
    assert state.owl_id == "pending"
    assert state.asset_key == ASSET_PENDING
    assert state.tone == "cautionary"
    assert state.caption_line2 == "Осталось неотмеченными: 3 из 5."


def test_unmarked_is_never_treated_as_failed() -> None:
    # An unmarked habit is not a failure: no failure scenario fires without a
    # recorded `missed` entry, even late in the day.
    state = select_dashboard(
        dashboard(unmarked_obligations=4, obligation_count=4, after_hours=True))
    assert state is not None and state.owl_id == "pending"
    assert state.asset_key != ASSET_FAILED


def test_explicit_failed_is_sarcastic_and_not_dismissible() -> None:
    state = select_dashboard(dashboard(failed_important=("Спорт",)))
    assert state is not None
    assert state.owl_id == "failed"
    assert state.asset_key == ASSET_FAILED
    assert state.tone == "sarcastic"
    assert "Спорт" in state.caption_line2
    assert state.dismissible is False
    assert state.fallback_line1 is not None


def test_low_mood_suppresses_sarcasm() -> None:
    state = select_dashboard(dashboard(failed_important=("Спорт",), mood=1))
    assert state is not None
    assert state.tone == "cautionary"
    assert state.fallback_line1 is None


def test_low_wellbeing_suppresses_sarcasm() -> None:
    state = select_dashboard(dashboard(failed_important=("Спорт",), wellbeing=2))
    assert state is not None
    assert state.tone == "cautionary"


def test_missing_mood_does_not_suppress_sarcasm() -> None:
    state = select_dashboard(dashboard(failed_important=("Спорт",), mood=None))
    assert state is not None
    assert state.tone == "sarcastic"


def test_many_misses_requires_real_misses_and_coverage() -> None:
    state = select_dashboard(dashboard(misses_last_window=3, coverage_last_window=0.75))
    assert state is not None
    assert state.owl_id == "many_misses"
    assert state.asset_key == ASSET_MANY_MISSES
    assert state.tone == "sarcastic"


def test_low_coverage_suppresses_many_misses() -> None:
    state = select_dashboard(dashboard(misses_last_window=3, coverage_last_window=0.3))
    assert state is None


def test_many_misses_sarcasm_suppressed_by_mood() -> None:
    state = select_dashboard(
        dashboard(misses_last_window=4, coverage_last_window=0.8, mood=2))
    assert state is not None
    assert state.owl_id == "many_misses"
    assert state.tone == "cautionary"


def test_new_record_needs_a_real_record() -> None:
    streak = StreakFact(1, "Чтение", 6, 3, TODAY - timedelta(days=20), "days", True)
    state = select_dashboard(dashboard(streaks=(streak,)))
    assert state is not None
    assert state.owl_id == "new_record"
    assert state.asset_key == ASSET_RECORD
    assert "Чтение" in state.caption_line2
    assert "6" in state.caption_line2


def test_micro_streak_is_not_a_record() -> None:
    streak = StreakFact(1, "Чтение", 3, 2, TODAY - timedelta(days=10), "days", True)
    assert select_dashboard(dashboard(streaks=(streak,))) is None


def test_broken_long_streak_is_cautionary_not_sarcastic() -> None:
    streak = StreakFact(1, "Чтение", 0, 9, TODAY - timedelta(days=2), "days", True)
    state = select_dashboard(dashboard(streaks=(streak,)))
    assert state is not None
    assert state.owl_id == "streak_broken"
    assert state.tone == "cautionary"
    assert state.asset_key == ASSET_FAILED


def test_stale_broken_streak_is_ignored() -> None:
    streak = StreakFact(1, "Чтение", 0, 9, TODAY - timedelta(days=60), "days", True)
    assert select_dashboard(dashboard(streaks=(streak,))) is None


def test_weekly_drawdown_requires_two_comparable_weeks() -> None:
    state = select_dashboard(dashboard(
        last_week_score=50.0, last_week_days=7, last_week_coverage=0.9,
        previous_week_score=80.0, previous_week_days=7, previous_week_coverage=0.9))
    assert state is not None
    assert state.owl_id == "weekly_drawdown"
    assert state.tone == "cautionary"
    assert state.asset_key == ASSET_MANY_MISSES


def test_incomplete_week_suppresses_drawdown() -> None:
    state = select_dashboard(dashboard(
        last_week_score=50.0, last_week_days=3, last_week_coverage=0.9,
        previous_week_score=80.0, previous_week_days=7, previous_week_coverage=0.9))
    assert state is None


def test_low_coverage_suppresses_drawdown() -> None:
    state = select_dashboard(dashboard(
        last_week_score=50.0, last_week_days=7, last_week_coverage=0.4,
        previous_week_score=80.0, previous_week_days=7, previous_week_coverage=0.9))
    assert state is None


def test_weekly_positive_needs_enough_days() -> None:
    state = select_dashboard(dashboard(
        last_week_score=90.0, last_week_days=6, last_week_coverage=0.8))
    assert state is not None
    assert state.owl_id == "weekly_positive"
    assert state.tone == "celebratory"
    assert state.asset_key == ASSET_ALL_DONE


def test_weekly_positive_on_one_or_two_days_is_not_shown() -> None:
    assert select_dashboard(dashboard(
        last_week_score=100.0, last_week_days=2, last_week_coverage=1.0)) is None


def test_priority_picks_exactly_one_winner() -> None:
    # A failure, many misses and a completed day are all true; the failure wins,
    # and only one state is returned.
    state = select_dashboard(dashboard(
        failed_important=("Спорт",), required_weight=2, completed_weight=2,
        misses_last_window=5, coverage_last_window=0.9))
    assert state is not None
    assert state.owl_id == "failed"


def test_pending_outranks_many_misses() -> None:
    state = select_dashboard(dashboard(
        unmarked_obligations=1, obligation_count=3, after_hours=True,
        misses_last_window=4, coverage_last_window=0.9))
    assert state is not None
    assert state.owl_id == "pending"


def test_fingerprint_is_stable_and_data_sensitive() -> None:
    first = select_dashboard(dashboard(misses_last_window=3, coverage_last_window=0.9))
    same = select_dashboard(dashboard(misses_last_window=3, coverage_last_window=0.9))
    changed = select_dashboard(dashboard(misses_last_window=4, coverage_last_window=0.9))
    assert first is not None and same is not None and changed is not None
    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != changed.fingerprint


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #


def test_no_data_is_neutral_and_not_a_failure() -> None:
    state = select_insights(insights(
        availability="no_data",
        availability_message="За выбранный период данных для аналитики нет."))
    assert state is not None
    assert state.owl_id == "no_data"
    assert state.asset_key == ASSET_INSIGHT
    assert state.tone == "neutral"
    assert "данных для аналитики нет" in state.caption_line2


def test_insufficient_data_is_supportive_and_shows_the_sample() -> None:
    state = select_insights(insights(
        availability="insufficient_data",
        availability_message="Пока недостаточно совместных наблюдений для устойчивых выводов.",
        max_sample_n=4))
    assert state is not None
    assert state.owl_id == "insufficient_data"
    assert state.tone == "supportive"
    assert "4" in state.caption_line2


def test_blocked_guardrail_uses_the_real_reason() -> None:
    state = select_insights(insights(
        availability="no_guardrails_passed",
        blocked_reason="После контроля дня недели вариация связи исчезает: это недельный паттерн.",
    ))
    assert state is not None
    assert state.owl_id == "guardrails_blocked"
    assert state.tone == "neutral"
    assert "контроля дня недели" in state.caption_line2


def test_preliminary_only() -> None:
    state = select_insights(insights(availability="preliminary_only", preliminary_count=2))
    assert state is not None
    assert state.owl_id == "preliminary_only"
    assert state.tone == "neutral"


def test_stable_insight_reuses_the_engine_wording() -> None:
    item = fact(lag=0, statement="В вашей истории наблюдается связь «Энергия» и «Настроение».")
    state = select_insights(insights(stable=item))
    assert state is not None
    assert state.owl_id == "stable_insight"
    assert state.caption_line2 == item.statement


def test_lag_insight_uses_correlation_wording_not_causation() -> None:
    state = select_insights(insights(stable=fact(lag=2, timing="Через два дня")))
    assert state is not None
    assert state.owl_id == "lag_insight"
    assert "через два дня" in state.caption_line2
    for forbidden in ("вызывает", "приводит", "улучшает", "ухудшает"):
        assert forbidden not in state.caption_line2


def test_insights_quality_states_outrank_a_finding() -> None:
    state = select_insights(insights(
        availability="insufficient_data",
        availability_message="Пока недостаточно совместных наблюдений.",
        stable=fact()))
    assert state is not None
    assert state.owl_id == "insufficient_data"


# --------------------------------------------------------------------------- #
# Experiments (Stage 10 reuse of the same asset)
# --------------------------------------------------------------------------- #


def test_active_experiment_is_supportive_and_uses_insight_asset() -> None:
    state = select_experiments(ExperimentOwlContext(
        active_title="Без алкоголя", active_day=6, active_total=14))
    assert state is not None
    assert state.owl_id == "experiment_active"
    assert state.asset_key == ASSET_INSIGHT
    assert state.context == "experiments"
    assert "6 из 14" in state.caption_line2
    assert state.tone == "supportive"


def test_completed_experiment_invites_a_look() -> None:
    state = select_experiments(ExperimentOwlContext(
        completed_title="Без алкоголя", completed_sufficient=True))
    assert state is not None
    assert state.owl_id == "experiment_completed"
    assert "сравнивать" in state.caption_line1


def test_completed_experiment_with_thin_data_is_neutral() -> None:
    state = select_experiments(ExperimentOwlContext(
        completed_title="Без алкоголя", completed_sufficient=False))
    assert state is not None
    assert state.owl_id == "experiment_no_data"
    assert state.tone == "neutral"
    assert "мало" in state.caption_line2


def test_experiments_owl_is_none_without_experiments() -> None:
    assert select_experiments(ExperimentOwlContext()) is None
