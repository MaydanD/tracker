"""Stage 10 experiments: lifecycle, comparison, coverage and cancellation over HTTP.

The seed is small and explicit: one daily habit active across the whole window,
with controlled recorded/missed/no-entry days and a constant energy per phase, so
every aggregate in the response can be checked against a hand-computed number.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.domain.daily_state import StateValues
from app.schemas.experiments import ExperimentDetailRead, ExperimentListRead
from app.services import daily, daily_state, habits
from tests.helpers import FrozenClock
from tests.test_progress_api import config

BEFORE_START = date(2026, 8, 18)
D0 = date(2026, 9, 1)
END = date(2026, 9, 14)
AFTER_END = date(2026, 9, 28)
SEED_TODAY = AFTER_END

WINDOW = {"title": "Без алкоголя", "hypothesis": "Проверить энергию.",
          "protocol": "Не пить 14 дней.", "start_date": D0.isoformat(),
          "end_date": END.isoformat()}


def _days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=index) for index in range(count)]


def seed(session, area_id: int) -> int:
    """One daily habit; deterministic recorded / missed / no-entry pattern.

    before: 6 done, 5 missed, 3 no-entry (11 observed of 14)
    during: 11 done, 1 missed, 2 no-entry (12 observed of 14)
    after:  8 done, 2 missed, 4 no-entry (10 observed of 14)
    Energy is present exactly on the recorded days: 3 / 4 / 3.
    """
    habit = habits.create_habit(
        session, config(area_id, name="Чтение"), effective_date=BEFORE_START)

    def record(day: date, status: str | None, energy: int | None) -> None:
        if status is not None:
            daily.save_entry(session, habit.id, day, status=status, today=SEED_TODAY)
        if energy is not None:
            daily_state.save_state(session, day, StateValues(energy=energy), today=SEED_TODAY)

    for index, day in enumerate(_days(BEFORE_START, 14)):
        if index <= 10:
            record(day, "done" if index % 2 == 0 else "missed", 3)
        else:
            record(day, None, None)
    for index, day in enumerate(_days(D0, 14)):
        if index <= 10:
            record(day, "done", 4)
        elif index == 11:
            record(day, "missed", 4)
        else:
            record(day, None, None)
    for index, day in enumerate(_days(END + timedelta(days=1), 14)):
        if index <= 7:
            record(day, "done", 3)
        elif index <= 9:
            record(day, "missed", 3)
        else:
            record(day, None, None)
    return habit.id


def create(client, **overrides) -> dict:
    payload = {**WINDOW, **overrides}
    response = client.post("/api/experiments", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def detail(client, experiment_id: int) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.json()


def approx(a: float | None, b: float, tol: float = 0.05) -> None:
    assert a is not None and abs(a - b) <= tol, (a, b)


# --- lifecycle and CRUD ---------------------------------------------------------


def test_create_and_list_scheduled_experiment(client, app):
    app.state.clock = FrozenClock(date(2026, 8, 25))
    created = create(client)
    assert created["status"] == "scheduled"
    assert created["cancelled_on"] is None
    assert created["phase"]["stage"] == "before"
    assert created["phase"]["days_until_start"] == 7

    listing = client.get("/api/experiments").json()
    ExperimentListRead.model_validate(listing)
    assert [item["id"] for item in listing["experiments"]] == [created["id"]]


def test_create_is_rejected_for_invalid_windows(client, app):
    app.state.clock = FrozenClock(D0)
    bad_order = client.post("/api/experiments", json={**WINDOW, "start_date": END.isoformat(),
                                                       "end_date": D0.isoformat()})
    assert bad_order.status_code == 422
    blank = client.post("/api/experiments", json={**WINDOW, "title": "   "})
    assert blank.status_code == 422
    too_long = client.post("/api/experiments", json={
        **WINDOW, "end_date": (D0 + timedelta(days=400)).isoformat()})
    assert too_long.status_code == 422


def test_unknown_experiment_is_404(client, app):
    app.state.clock = FrozenClock(D0)
    assert client.get("/api/experiments/999999").status_code == 404


# --- comparison -----------------------------------------------------------------


def test_detail_describes_before_during_after(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(AFTER_END)
    experiment = create(client)
    payload = detail(client, experiment["id"])
    ExperimentDetailRead.model_validate(payload)

    analysis = payload["analysis"]
    assert [analysis["windows"][key]["start"] for key in ("before", "during", "after")] == [
        BEFORE_START.isoformat(), D0.isoformat(), (END + timedelta(days=1)).isoformat()]
    assert all(analysis["windows"][key]["end"] for key in ("before", "during", "after"))
    assert payload["experiment"]["status"] == "completed"

    before = analysis["overall"]["before"]
    during = analysis["overall"]["during"]
    after = analysis["overall"]["after"]
    approx(before["mean_score"], 6 / 14 * 100)
    approx(during["mean_score"], 11 / 14 * 100)
    approx(after["mean_score"], 8 / 14 * 100)
    assert (before["coverage"]["observed_days"], during["coverage"]["observed_days"],
            after["coverage"]["observed_days"]) == (11, 12, 10)
    approx(analysis["overall"]["delta_before_during"], 35.71)

    habit = analysis["habits"][0]
    assert habit["name"] == "Чтение"
    assert (habit["before"]["done_days"], habit["before"]["missed_days"]) == (6, 5)
    approx(habit["delta_during_vs_before"], 35.71)

    energy = next(item for item in analysis["state"] if item["key"] == "state.energy")
    assert energy["kind"] == "ordinal"
    approx(energy["before"]["value"], 3.0)
    approx(energy["during"]["value"], 4.0)
    approx(energy["delta_during_vs_before"], 1.0)

    # Raw daily history spans the three phases; unobserved days keep score=None.
    series = analysis["series"]
    assert len(series) == 42
    assert {point["phase"] for point in series} == {"before", "during", "after"}
    # Energy is only present on recorded days; silent days stay None, never 0.
    assert any(point["energy"] is None for point in series)
    assert all(point["score"] in (None, 0.0, 100.0) for point in series)


def test_missing_days_are_not_counted_as_missed(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(AFTER_END)
    habit_comparison = detail(client, create(client)["id"])["analysis"]["habits"][0]
    before = habit_comparison["before"]
    # 14 obligations: 6 done + 5 missed = 11 observed; the 3 silent days are
    # neither done nor missed.
    assert before["obligation_days"] == 14
    assert before["observed_days"] == 11
    assert before["done_days"] + before["missed_days"] == 11
    assert before["missed_days"] == 5


def test_partial_after_is_reported_honestly(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(END + timedelta(days=5))
    experiment = create(client)
    payload = detail(client, experiment["id"])
    assert payload["experiment"]["status"] == "completed"
    assert payload["experiment"]["phase"]["after_collected_days"] == 5
    after = payload["analysis"]["overall"]["after"]
    assert after["coverage"]["calendar_days"] == 14
    assert after["coverage"]["observed_days"] == 5
    assert after["coverage"]["observed_days"] < after["coverage"]["calendar_days"]
    assert "из 14 дней" in payload["analysis"]["summary"]


def test_no_data_window_is_not_a_failure(client, app):
    app.state.clock = FrozenClock(date(2026, 8, 1))
    experiment = create(client, start_date="2026-07-01", end_date="2026-07-14")
    payload = detail(client, experiment["id"])
    analysis = payload["analysis"]
    assert analysis["sufficient"] is False
    assert analysis["overall"]["before"]["mean_score"] is None
    assert analysis["overall"]["during"]["mean_score"] is None
    assert "недостаточно данных" in analysis["summary"]
    assert analysis["habits"] == []
    assert analysis["state"] == []


def test_active_experiment_phase(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(D0 + timedelta(days=5))
    experiment = create(client)
    payload = detail(client, experiment["id"])
    assert payload["experiment"]["status"] == "active"
    assert payload["experiment"]["phase"]["stage"] == "during"
    assert payload["experiment"]["phase"]["day_index"] == 6
    assert payload["experiment"]["phase"]["days_total"] == 14


# --- cancellation ---------------------------------------------------------------


def test_cancellation_shortens_during(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(D0 + timedelta(days=4))
    experiment = create(client)
    cancelled = client.post(f"/api/experiments/{experiment['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_on"] == (D0 + timedelta(days=4)).isoformat()

    payload = detail(client, experiment["id"])
    analysis = payload["analysis"]
    assert analysis["windows"]["during"]["start"] == D0.isoformat()
    assert analysis["windows"]["during"]["end"] == (D0 + timedelta(days=4)).isoformat()
    assert analysis["windows"]["after"]["start"] == (D0 + timedelta(days=5)).isoformat()
    assert analysis["windows"]["before"]["start"] == (D0 - timedelta(days=5)).isoformat()


def test_cancel_rules(client, app):
    app.state.clock = FrozenClock(D0 + timedelta(days=2))
    experiment = create(client)
    assert client.post(f"/api/experiments/{experiment['id']}/cancel").status_code == 200
    assert client.post(f"/api/experiments/{experiment['id']}/cancel").status_code == 409

    app.state.clock = FrozenClock(AFTER_END)
    completed = create(client, title="Другой", start_date=D0.isoformat(), end_date=END.isoformat())
    completed = client.get(f"/api/experiments/{completed['id']}").json()["experiment"]
    assert completed["status"] == "completed"
    assert client.post(f"/api/experiments/{completed['id']}/cancel").status_code == 409


# --- editing policy -------------------------------------------------------------


def test_completed_dates_are_immutable_but_text_is_editable(client, app):
    app.state.clock = FrozenClock(AFTER_END)
    experiment = create(client)
    frozen = client.patch(f"/api/experiments/{experiment['id']}",
                          json={"end_date": (END + timedelta(days=3)).isoformat()})
    assert frozen.status_code == 409
    edited = client.patch(f"/api/experiments/{experiment['id']}",
                          json={"title": "Уточнённое название"})
    assert edited.status_code == 200
    assert edited.json()["title"] == "Уточнённое название"


def test_active_dates_can_change(client, app):
    app.state.clock = FrozenClock(D0 + timedelta(days=2))
    experiment = create(client)
    response = client.patch(f"/api/experiments/{experiment['id']}",
                            json={"end_date": (END + timedelta(days=7)).isoformat()})
    assert response.status_code == 200
    assert response.json()["end_date"] == (END + timedelta(days=7)).isoformat()


# --- overlap --------------------------------------------------------------------


def test_overlapping_experiment_is_reported(client, app):
    app.state.clock = FrozenClock(D0 + timedelta(days=3))
    first = create(client)
    second = create(client, title="Второй", start_date=(D0 + timedelta(days=5)).isoformat(),
                    end_date=(END + timedelta(days=10)).isoformat())
    payload = detail(client, first["id"])
    assert [item["id"] for item in payload["overlaps"]] == [second["id"]]
    assert payload["overlaps"][0]["title"] == "Второй"
    # The other direction also sees the intersection.
    reverse = detail(client, second["id"])
    assert [item["id"] for item in reverse["overlaps"]] == [first["id"]]


# --- owl ------------------------------------------------------------------------


def test_list_owl_reuses_experiment_states(client, app, session, health_area):
    seed(session, health_area["id"])
    assert client.get("/api/experiments").json()["owl"] is None

    app.state.clock = FrozenClock(D0 + timedelta(days=3))
    create(client)
    owl = client.get("/api/experiments").json()["owl"]
    assert owl["owl_id"] == "experiment_active"
    assert owl["asset_key"] == "owl_insight"
    assert owl["context"] == "experiments"
    assert "Ну что, проверим" in owl["caption_line1"]
    assert "Без алкоголя" in owl["caption_line2"]

    app.state.clock = FrozenClock(AFTER_END)
    owl = client.get("/api/experiments").json()["owl"]
    assert owl["owl_id"] == "experiment_completed"


# --- contract -------------------------------------------------------------------


def test_payload_is_russian_and_free_of_causal_wording(client, app, session, health_area):
    seed(session, health_area["id"])
    app.state.clock = FrozenClock(AFTER_END)
    payload = detail(client, create(client)["id"])
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    summary = payload["analysis"]["summary"]
    for forbidden in ("вызывает", "приводит", "улучшил", "ухудшил", "доказывает"):
        assert forbidden not in summary
    assert payload["experiment"]["status"] in {"scheduled", "active", "completed", "cancelled"}
