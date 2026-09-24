"""Daily State contract, domain, SQLite backstops and habit isolation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import DailyState
from app.domain.daily_state import InvalidDailyStateError, StateValues, validate_state
from app.services.daily_state import get_state, save_state
from tests.helpers import FrozenClock, habit_payload

TODAY = date(2026, 9, 24)


@pytest.fixture
def endpoint(app):
    app.state.clock = FrozenClock(TODAY)
    return f"/api/days/{TODAY}/state"


def test_crud_replacement_idempotency_and_history(client, endpoint, session):
    assert client.get(endpoint).json() == {"state_date": str(TODAY), "today": str(TODAY), "state": None}
    first = client.put(endpoint, json={"mood": 4, "alcohol": False}).json()
    second = client.put(endpoint, json={"mood": 4, "alcohol": False}).json()
    assert first["id"] == second["id"]
    assert first["created_at"] == second["created_at"]
    assert session.scalar(select(func.count()).select_from(DailyState)) == 1
    result = client.put(endpoint, json={"note": "  Странный день\n  "})
    assert result.status_code == 200
    saved = client.get(endpoint).json()["state"]
    assert saved["note"] == "Странный день"
    assert saved["mood"] is None and saved["alcohol"] is None
    past = "/api/days/2000-01-01/state"
    assert client.put(past, json={"energy": 1}).status_code == 200
    assert client.put(past, json={"energy": 5}).json()["energy"] == 5
    for path in [endpoint, past]:
        assert client.delete(path).status_code == 204
        assert client.delete(path).status_code == 204
        assert client.get(path).json()["state"] is None


def test_future_uses_injected_clock_for_all_writes(client, endpoint, app):
    future = f"/api/days/{TODAY + timedelta(days=1)}/state"
    assert client.get(future).json()["state"] is None
    for response in [client.put(future, json={"mood": 3}), client.delete(future)]:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "future_daily_state"
    app.state.clock = FrozenClock(TODAY + timedelta(days=1))
    assert client.put(future, json={"mood": 3}).status_code == 200


VALID = [
    *({field: value} for field in ("mood", "energy", "wellbeing") for value in (1, 5)),
    *({"sleep_status": status} for status in ("underslept", "normal", "overslept")),
    *({field: value} for field in ("sleep_minutes", "computer_minutes") for value in (0, 1440)),
    {"alcohol": True}, {"alcohol": False}, {"alcohol": True, "alcohol_detail": "  2 пива  "},
    {"alcohol": False, "alcohol_detail": " \n\t "},
    {"gaming": True}, {"gaming": False}, {"gaming": False, "gaming_minutes": 0},
    *({"gaming": True, "gaming_minutes": value} for value in (0, 1440)),
    *({"computer_overuse": flag, "computer_minutes": 180} for flag in (None, False, True)),
    {"note": "День"}, {"mood": 2, "note": " \t\n "},
]
INVALID = [
    {}, {"note": " \n\t "}, {"alcohol_detail": " "},
    *({field: value} for field in ("mood", "energy", "wellbeing") for value in (0, 6, 1.5, True, "3")),
    *({field: value, "gaming": True} for field in ("sleep_minutes", "gaming_minutes", "computer_minutes") for value in (-1, 1441, 1.5, False, "60")),
    {"sleep_status": "unknown"}, {"alcohol": False, "alcohol_detail": "вино"},
    {"alcohol_detail": "вино"}, {"gaming": False, "gaming_minutes": 180},
    {"gaming_minutes": 0}, {"gaming_minutes": 180}, {"note": "x" * 501},
    {"alcohol": True, "alcohol_detail": "x" * 201},
    *({field: value} for field in ("alcohol", "gaming", "computer_overuse") for value in (0, 1, "false")),
]


@pytest.mark.parametrize("payload", VALID)
def test_valid_partial_values_in_domain_and_api(client, endpoint, payload):
    values = validate_state(StateValues(**payload), state_date=TODAY, today=TODAY)
    response = client.put(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert {key: response.json()[key] for key in asdict(values)} == asdict(values)
    assert client.get(endpoint).json()["state"] == response.json()


@pytest.mark.parametrize("payload", INVALID)
def test_invalid_values_in_domain_and_api(client, endpoint, payload):
    with pytest.raises(InvalidDailyStateError):
        validate_state(StateValues(**payload), state_date=TODAY, today=TODAY)
    response = client.put(endpoint, json=payload)
    assert response.status_code == 422, response.text
    assert "error" in response.json()
    assert client.get(endpoint).json()["state"] is None


@pytest.mark.parametrize("field", ["alcohol", "gaming", "computer_overuse"])
def test_tristate_roundtrips_as_null_false_true(client, endpoint, session, field):
    for value in (None, False, True, None):
        response = client.put(endpoint, json={"mood": 3, field: value})
        assert response.status_code == 200
        assert response.json()[field] is value
        assert client.get(endpoint).json()["state"][field] is value
        raw = session.execute(text(f"SELECT {field} FROM daily_states")).scalar_one()
        assert raw == (None if value is None else int(value))


@pytest.mark.parametrize("payload", [
    {}, {"mood": 0}, {"mood": 6}, {"energy": 6}, {"wellbeing": 0},
    {"mood": 1.5}, {"sleep_status": "bad"}, {"sleep_minutes": -1},
    {"sleep_minutes": 1441}, {"gaming": 1, "gaming_minutes": 1441},
    {"computer_minutes": 1441}, {"computer_minutes": 1.5},
    {"alcohol": 2}, {"gaming": 2}, {"computer_overuse": 2},
    {"alcohol_detail": "вино"}, {"alcohol": 0, "alcohol_detail": "вино"},
    {"gaming_minutes": 0}, {"gaming": 0, "gaming_minutes": 1},
    {"note": "   "}, {"note": "x" * 501},
])
def test_db_constraints_without_domain(session, payload):
    columns = ", ".join(payload)
    params = ", ".join(f":{key}" for key in payload)
    with pytest.raises(IntegrityError):
        session.execute(text(
            "INSERT INTO daily_states (state_date, created_at, updated_at"
            + (", " + columns if columns else "") + ") VALUES "
            "('2026-09-24', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
            + (", " + params if params else "") + ")"
        ), payload)
        session.commit()
    session.rollback()


def test_db_unique_date(session):
    save_state(session, TODAY, StateValues(mood=1), today=TODAY)
    session.add(DailyState(state_date=TODAY, mood=5))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_concurrent_first_saves_are_atomic(database):
    barrier = Barrier(2)

    def write(mood):
        with database.session() as session:
            barrier.wait(timeout=10)
            state = save_state(session, TODAY, StateValues(mood=mood), today=TODAY)
            return state.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(write, [1, 5]))
    assert ids[0] == ids[1]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(DailyState)) == 1
        assert get_state(session, TODAY).mood in (1, 5)


def test_daily_state_never_changes_habits_entries_scores_or_streaks(client, endpoint, health_area):
    ids = [client.post("/api/habits", json=habit_payload(area_id=health_area["id"], name=str(i))).json()["id"] for i in range(4)]
    for habit_id, status in zip(ids, ("done", "missed", "skipped")):
        payload = {"status": status, "note": "Заметка привычки"}
        if status == "skipped":
            payload["skip_reason"] = "Отдых"
        assert client.put(f"/api/habits/{habit_id}/entries/{TODAY}", json=payload).status_code == 200
    paths = [f"/api/days/{TODAY}", f"/api/progress/days/{TODAY}", f"/api/progress/weeks/{TODAY}"]
    paths += [f"/api/habits/{habit_id}/progress" for habit_id in ids]
    before = [client.get(path).json() for path in paths]
    assert before[1]["day"]["score"] == 25
    for payload in [{"mood": 1, "note": "Заметка дня", "alcohol": True}, {"mood": 5, "gaming": False}]:
        assert client.put(endpoint, json=payload).status_code == 200
        assert [client.get(path).json() for path in paths] == before
    assert client.delete(endpoint).status_code == 204
    assert [client.get(path).json() for path in paths] == before
    tomorrow = TODAY + timedelta(days=1)
    assert client.put(f"/api/habits/{ids[0]}/entries/{tomorrow}", json={"status": "skipped", "skip_reason": "Поездка"}).status_code == 200
    assert client.put(f"/api/days/{tomorrow}/state", json={"mood": 5}).status_code == 422
