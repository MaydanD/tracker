"""Stage 9 Owl HTTP contract: dashboard + insights wiring, schema and wording."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.schemas.dashboard import DashboardRead
from app.schemas.insights import InsightAnalyticsRead
from app.services import daily, habits
from tests.helpers import FrozenClock
from tests.test_insights_api import TODAY as INSIGHTS_TODAY
from tests.test_insights_api import WINDOW, seed
from tests.test_progress_api import config

DAY = date(2026, 9, 25)


class EveningClock:
    """A clock at or after 18:00, so the Owl's evening rule can be exercised."""

    def __init__(self, current: date, hour: int = 19) -> None:
        self.current = current
        self.hour = hour

    def today(self) -> date:
        return self.current

    def now(self) -> datetime:
        return datetime.combine(self.current, time(hour=self.hour))


def make_habit(session, area_id, *, weight=1, name="Чтение"):
    return habits.create_habit(
        session, config(area_id, name=name, weight=weight),
        effective_date=DAY - timedelta(days=5))


def dashboard_payload(client) -> dict:
    response = client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


def test_dashboard_owl_all_completed(client, app, session, health_area):
    app.state.clock = FrozenClock(DAY)
    habit = make_habit(session, health_area["id"])
    daily.save_entry(session, habit.id, DAY, status="done", today=DAY)

    data = dashboard_payload(client)
    DashboardRead.model_validate(data)
    owl = data["owl"]
    assert owl is not None
    assert owl["owl_id"] == "all_completed"
    assert owl["asset_key"] == "owl_all_done"
    assert owl["tone"] == "celebratory"
    assert owl["dismissible"] is True
    assert "100%" in owl["caption_line2"]
    assert owl["context"] == "dashboard"
    assert owl["fingerprint"]


def test_dashboard_owl_is_null_without_anything_to_say(client, app):
    app.state.clock = FrozenClock(DAY)
    data = dashboard_payload(client)
    DashboardRead.model_validate(data)
    assert data["owl"] is None


def test_dashboard_pending_hidden_before_evening(client, app, session, health_area):
    app.state.clock = FrozenClock(DAY)
    make_habit(session, health_area["id"])
    assert dashboard_payload(client)["owl"] is None


def test_dashboard_pending_after_evening_shows_real_counter(client, app, session, health_area):
    app.state.clock = EveningClock(DAY)
    make_habit(session, health_area["id"])
    data = dashboard_payload(client)
    owl = data["owl"]
    assert owl is not None
    assert owl["owl_id"] == "pending"
    assert owl["asset_key"] == "owl_pending"
    assert owl["tone"] == "cautionary"
    assert owl["caption_line2"] == "Осталось неотмеченными: 1 из 1."


def test_failed_is_sarcastic_and_mood_suppresses_it(client, app, session, health_area):
    app.state.clock = FrozenClock(DAY)
    habit = make_habit(session, health_area["id"], weight=2, name="Спорт")
    daily.save_entry(session, habit.id, DAY, status="missed", today=DAY)

    owl = dashboard_payload(client)["owl"]
    assert owl is not None
    assert owl["owl_id"] == "failed"
    assert owl["asset_key"] == "owl_failed"
    assert owl["tone"] == "sarcastic"
    assert owl["dismissible"] is False
    assert "Спорт" in owl["caption_line2"]

    response = client.put(f"/api/days/{DAY}/state", json={"mood": 1})
    assert response.status_code == 200, response.text
    owl = dashboard_payload(client)["owl"]
    assert owl is not None
    assert owl["owl_id"] == "failed"
    assert owl["tone"] == "cautionary"


def test_insights_owl_reflects_a_real_finding(client, app, session, health_area):
    app.state.clock = FrozenClock(INSIGHTS_TODAY)
    seed(session, health_area["id"])

    response = client.get("/api/analytics/insights", params=WINDOW)
    assert response.status_code == 200, response.text
    payload = response.json()
    InsightAnalyticsRead.model_validate(payload)
    owl = payload["owl"]
    assert owl is not None
    assert owl["asset_key"] == "owl_insight"
    assert owl["tone"] == "neutral"
    assert owl["context"] == "insights"
    # The caption must be Russian and must never leak a raw enum or variable key.
    for line in (owl["caption_line1"], owl["caption_line2"]):
        assert line
        assert "_" not in line
    assert owl["owl_id"] in ("stable_insight", "lag_insight", "guardrails_blocked",
                             "preliminary_only")


def test_insights_no_data_is_not_a_failure(client, app):
    app.state.clock = FrozenClock(INSIGHTS_TODAY)
    response = client.get("/api/analytics/insights", params=WINDOW)
    assert response.status_code == 200, response.text
    payload = response.json()
    InsightAnalyticsRead.model_validate(payload)
    owl = payload["owl"]
    assert owl is not None
    assert owl["owl_id"] == "no_data"
    assert owl["asset_key"] == "owl_insight"
    assert owl["tone"] == "neutral"
    assert "данных" in owl["caption_line2"]
