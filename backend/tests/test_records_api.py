"""Stage 11 records & achievements over HTTP, with a fully hand-checked seed.

One daily habit from 2026-09-07: a 7-day run, a missed day, then a 3-day run,
plus 30 Daily State days, one completed and one cancelled experiment, and two
Stage 8 insight snapshots. Every aggregate below is computed by hand in the
docstrings so a regression shows up as a wrong number, not a vague failure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.db.models import InsightSnapshot
from app.domain.daily_state import StateValues
from app.schemas.dashboard import DashboardRead
from app.schemas.records import RecordsRead
from app.services import daily, daily_state, experiments, habits
from tests.helpers import FrozenClock
from tests.test_progress_api import config

MON = date(2026, 9, 7)
TODAY = MON + timedelta(days=35)  # 2026-10-12


def _days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=index) for index in range(count)]


def _snapshot(session, *, fingerprint: str, evaluated_on: date, confidence: str) -> None:
    session.add(InsightSnapshot(
        fingerprint=fingerprint, evaluated_on=evaluated_on,
        period_start=evaluated_on - timedelta(days=30), period_end=evaluated_on,
        x_key="state.energy", y_key="state.mood", x_label="Энергия", y_label="Настроение",
        grain="daily", lag=0, lag_unit=None, orientation="same_period",
        relationship_method="pearson", coefficient=0.4, n=40, pair_coverage=0.9,
        confidence=confidence, guardrail_verdict="pass", presentation_status=confidence,
        blocking_reasons=[], warnings=[], statement="Наблюдалась связь.",
        insight_policy_version="1", guardrail_policy_version="1",
        confidence_policy_version="1", template_version="1",
    ))
    session.commit()


def seed(session, area_id: int) -> dict[str, int]:
    """The deterministic dataset described in the module docstring."""

    habit = habits.create_habit(
        session, config(area_id, name="Чтение"), effective_date=MON)
    for offset in [0, 1, 2, 3, 4, 5, 6, 8, 9, 10]:
        daily.save_entry(session, habit.id, MON + timedelta(days=offset),
                         status="done", today=TODAY)
    daily.save_entry(session, habit.id, MON + timedelta(days=7),
                     status="missed", today=TODAY)
    for day in _days(MON, 30):
        daily_state.save_state(session, day, StateValues(mood=3), today=TODAY)

    completed = experiments.create_experiment(
        session, title="Без алкоголя", hypothesis="Проверить энергию.",
        protocol="Не пить две недели.",
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 14),
    )
    cancelled = experiments.create_experiment(
        session, title="Ранние подъёмы", hypothesis="Проверить утро.",
        protocol="Вставать в 6:00.",
        start_date=date(2026, 8, 20), end_date=date(2026, 9, 2),
    )
    experiments.cancel_experiment(session, cancelled.id, today=date(2026, 8, 25))

    _snapshot(session, fingerprint="a" * 16, evaluated_on=MON + timedelta(days=2),
              confidence="stable")
    _snapshot(session, fingerprint="b" * 16, evaluated_on=MON + timedelta(days=4),
              confidence="well_supported")
    return {"habit_id": habit.id, "completed_id": completed.id}


def records(client) -> dict:
    response = client.get("/api/records")
    assert response.status_code == 200, response.text
    return response.json()


def achievement(payload: dict, key: str) -> dict:
    return next(item for item in payload["achievements"] if item["key"] == key)


def test_records_contract_and_hand_checked_values(client, app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    seed(session, health_area["id"])

    response = client.get("/api/records")
    assert response.status_code == 200, response.text
    payload = RecordsRead.model_validate(response.json()).model_dump(mode="json")

    summary = payload["summary"]
    # 11 entry days (0..10) and 30 state days (0..29) overlap into 30 tracked days.
    assert summary["tracked_days"] == 30
    assert summary["first_tracked_day"] == MON.isoformat()
    assert summary["habit_completions"] == 10
    assert summary["experiments_created"] == 2
    # The cancelled window is not a completed experiment.
    assert summary["completed_experiments"] == 1
    assert summary["stable_insight_on"] == (MON + timedelta(days=2)).isoformat()
    assert summary["well_supported_insight_on"] == (MON + timedelta(days=4)).isoformat()

    streak = payload["records"]["longest_streak"]
    assert streak["name"] == "Чтение"
    assert streak["unit"] == "days"
    assert streak["best_streak"] == 7
    assert streak["best_start"] == MON.isoformat()
    assert streak["best_end"] == (MON + timedelta(days=6)).isoformat()
    assert streak["current_streak"] == 0
    assert streak["archived"] is False

    best_day = payload["records"]["best_day"]
    assert best_day["day"] == MON.isoformat()
    assert best_day["score"] == 100
    # Ten 100% days: the seven-day run and the three-day run.
    assert best_day["ties"] == 10

    best_week = payload["records"]["best_week"]
    assert best_week["week_start"] == MON.isoformat()
    assert best_week["week_end"] == (MON + timedelta(days=6)).isoformat()
    assert best_week["score"] == 100
    assert best_week["observed_days"] == 7

    assert payload["records"]["most_completed"]["completed_count"] == 1

    consistency = payload["records"]["consistency"]
    assert len(consistency) == 1
    assert consistency[0]["period_start"] == "2026-09-01"
    assert consistency[0]["period_end"] == "2026-09-30"
    assert consistency[0]["done_days"] == 10
    assert consistency[0]["obligation_days"] == 24


def test_achievements_have_real_dates_progress_and_russian_wording(client, app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    seed(session, health_area["id"])
    payload = records(client)

    streak = achievement(payload, "streak_7")
    assert streak["achieved"] is True
    assert streak["achieved_on"] == (MON + timedelta(days=6)).isoformat()
    assert streak["category"] == "streak"
    assert streak["title"] == "Серия 7 дней"
    assert streak["description"] == "Одна привычка держалась 7 дней подряд."
    assert streak["progress"] == {"current": 7, "target": 7}

    first = achievement(payload, "first_habit_completion")
    assert first["achieved_on"] == MON.isoformat()

    # A milestone reached on the 30th tracked / state day.
    assert achievement(payload, "tracked_30_days")["achieved_on"] == (
        MON + timedelta(days=29)
    ).isoformat()
    assert achievement(payload, "daily_state_30")["achieved_on"] == (
        MON + timedelta(days=29)
    ).isoformat()

    # Experiments: created and completed are separate milestones.
    assert achievement(payload, "first_experiment")["achieved"] is True
    assert achievement(payload, "first_completed_experiment")["achieved_on"] == "2026-08-14"
    assert achievement(payload, "experiments_5")["achieved"] is False

    # Insights use the snapshot history, not the current feed.
    assert achievement(payload, "first_stable_insight")["achieved_on"] == (
        MON + timedelta(days=2)
    ).isoformat()
    assert achievement(payload, "first_well_supported_insight")["achieved_on"] == (
        MON + timedelta(days=4)
    ).isoformat()

    locked = achievement(payload, "habit_100_completions")
    assert locked["achieved"] is False
    assert locked["achieved_on"] is None
    assert locked["progress"] == {"current": 10, "target": 100}

    assert payload["achieved_count"] == sum(
        1 for item in payload["achievements"] if item["achieved"]
    )
    assert payload["total_count"] == len(payload["achievements"])
    assert payload["total_count"] >= 15


def test_achievement_order_and_recent_list_are_stable(client, app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    seed(session, health_area["id"])

    first = [item["key"] for item in records(client)["achievements"]]
    second = [item["key"] for item in records(client)["achievements"]]
    assert first == second

    payload = records(client)
    recent_keys = [item["key"] for item in payload["recent_achievements"]]
    # tracked_30_days and daily_state_30 were reached on MON+29, within 7 days of today.
    assert "tracked_30_days" in recent_keys
    assert "daily_state_30" in recent_keys
    assert all(item["achieved"] is True for item in payload["recent_achievements"])


def test_archived_habit_keeps_its_record(client, app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    ids = seed(session, health_area["id"])
    habit = habits.get_habit(session, ids["habit_id"])
    habit.is_archived = True
    habit.archived_at = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    session.commit()

    streak = records(client)["records"]["longest_streak"]
    assert streak["archived"] is True
    # The frozen run up to the day before archiving is preserved, not erased.
    assert streak["best_streak"] == 7
    assert streak["best_start"] == MON.isoformat()


def test_empty_account_is_not_a_failure(client, app):
    app.state.clock = FrozenClock(TODAY)
    payload = records(client)

    assert payload["summary"]["tracked_days"] == 0
    assert payload["summary"]["first_tracked_day"] is None
    assert payload["summary"]["habit_completions"] == 0
    assert payload["records"]["longest_streak"] is None
    assert payload["records"]["best_day"] is None
    assert payload["records"]["best_week"] is None
    assert payload["records"]["consistency"] == []
    assert payload["achieved_count"] == 0
    assert payload["recent_achievements"] == []
    assert all(item["achieved"] is False for item in payload["achievements"])


def test_dashboard_carries_the_compact_records_preview(client, app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    seed(session, health_area["id"])

    response = client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    data = DashboardRead.model_validate(response.json()).model_dump(mode="json")

    preview = data["records"]
    assert preview is not None
    assert preview["longest_streak"]["name"] == "Чтение"
    assert preview["longest_streak"]["best_streak"] == 7
    assert preview["latest_achievement"] is not None
    assert preview["achieved_count"] > 0
    assert preview["total_count"] == preview["achieved_count"] + (
        len([item for item in records(client)["achievements"] if not item["achieved"]])
    )
