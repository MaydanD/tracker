"""Database/API integration: historical lookup, read purity, injected clock."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import DailyHabitEntry
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.services import daily, habits
from app.services.progress import load_histories
from tests.helpers import FrozenClock

MON = date(2026, 9, 7)


def config(area_id, **overrides):
    return HabitConfig.create(**{
        "name": "Чтение", "area_id": area_id, "weight": 1,
        "tracking_mode": "binary", "schedule": Schedule.create("daily"), **overrides,
    })


def make(session, area_id, start=MON, **overrides):
    return habits.create_habit(session, config(area_id, **overrides), effective_date=start)


def save(session, habit_id, offset, status="done", **values):
    daily.save_entry(session, habit_id, MON + timedelta(days=offset), status=status,
                     today=MON + timedelta(days=30), **values)


def test_api_daily_score_streak_and_no_implicit_rows(client, app, session, health_area):
    app.state.clock = FrozenClock(MON + timedelta(days=2))
    a = make(session, health_area["id"])
    b = make(session, health_area["id"], weight=3)
    c = make(session, health_area["id"])
    for day in [0, 1, 2]:
        save(session, a.id, day)
    save(session, b.id, 2, "skipped", skip_reason="Болел")
    save(session, c.id, 2)
    before = session.scalar(select(func.count()).select_from(DailyHabitEntry))
    for _ in range(2):
        response = client.get("/api/progress/days/2026-09-09")
        assert response.status_code == 200, response.text
        data = response.json()
        assert (data["day"]["score"], data["day"]["completed_weight"], data["day"]["required_weight"]) == (40, 2, 5)
        assert data["week"]["week_start"] == "2026-09-07"
        assert data["week"]["week_end"] == "2026-09-13"
        assert data["streaks"][0]["current_streak"] == 3
        assert data["day"]["obligations"][1]["entry_status"] == "skipped"
        empty = client.get("/api/progress/days/2026-09-10").json()["day"]
        assert empty["score"] == 0
        assert all(o["entry_status"] is None for o in empty["obligations"])
        assert client.get(f"/api/habits/{a.id}/progress").json()["streak"]["unit"] == "days"
        assert client.get("/api/progress/weeks/2026-09-13").status_code == 200
    assert session.scalar(select(func.count()).select_from(DailyHabitEntry)) == before
    assert client.get(f"/api/habits/{b.id}/entries/2026-09-09").json()["skip_reason"] == "Болел"


def test_api_quantity_is_one_completion_and_score_capped(client, app, session, health_area):
    app.state.clock = FrozenClock(MON + timedelta(days=6))
    h = make(session, health_area["id"], weight=2, tracking_mode="binary_quantity", quantity_unit="км",
             schedule=Schedule.create("weekdays", weekdays=[0, 2, 4]))
    for day in [0, 1, 3, 4, 5]:
        save(session, h.id, day, quantity_value=20)
    data = client.get("/api/progress/weeks/2026-09-13").json()
    assert (data["score"], data["completed_weight"], data["required_weight"]) == (100, 6, 6)
    assert data["habits"][0]["completed_count"] == 5
    assert data["habits"][0]["preferred_weekdays"] == [0, 2, 4]
    progress = client.get(f"/api/habits/{h.id}/progress").json()
    assert (progress["streak"]["unit"], progress["streak"]["current_streak"]) == ("weeks", 1)


def test_api_clock_sunday_monday_and_edit_recompute(client, app, session, health_area):
    h = make(session, health_area["id"], schedule=Schedule.create("times_per_week", times_per_week=3))
    for d in [0, 1, 2, 7, 8]:
        save(session, h.id, d)
    app.state.clock = FrozenClock(MON + timedelta(days=13))
    assert client.get(f"/api/habits/{h.id}/progress").json()["streak"]["current_streak"] == 1
    app.state.clock = FrozenClock(MON + timedelta(days=14))
    assert client.get(f"/api/habits/{h.id}/progress").json()["streak"]["current_streak"] == 0
    assert client.put(f"/api/habits/{h.id}/entries/2026-09-20", json={"status": "done"}).status_code == 200
    assert client.get(f"/api/habits/{h.id}/progress").json()["streak"]["current_streak"] == 2
    assert client.delete(f"/api/habits/{h.id}/entries/2026-09-20").status_code == 204
    assert client.get(f"/api/habits/{h.id}/progress").json()["streak"]["current_streak"] == 0


def test_service_versions_same_day_collapse_and_api_boundaries(client, app, session, health_area):
    app.state.clock = FrozenClock(MON + timedelta(days=9))
    area = health_area["id"]
    h = make(session, area, schedule=Schedule.create("times_per_week", times_per_week=3))
    save(session, h.id, 0)
    habits.update_habit(session, h.id, config(area, weight=3, schedule=Schedule.create("weekdays", weekdays=[1, 3])), effective_date=MON + timedelta(days=2))
    old = client.get("/api/progress/weeks/2026-09-07").json()
    assert (old["required_weight"], old["completed_weight"]) == (3, 1)
    new = client.get("/api/progress/weeks/2026-09-14").json()
    assert new["required_weight"] == 6
    habits.update_habit(session, h.id, config(area, weight=2), effective_date=MON + timedelta(days=2))
    assert len(load_histories(session, h.id)[0].versions) == 2
    mixed = client.get("/api/progress/weeks/2026-09-07").json()
    assert mixed["required_weight"] == 13  # old full quota 3 + five daily days at 2
    assert client.get("/api/progress/days/2026-09-08").json()["day"]["score"] is None
    assert client.get("/api/progress/days/2026-09-09").json()["day"]["required_weight"] == 2


def test_archive_retains_history_and_excludes_current_future(client, app, session, health_area):
    app.state.clock = FrozenClock(MON + timedelta(days=14))
    h = make(session, health_area["id"])
    save(session, h.id, 0)
    save(session, h.id, 1)
    before = client.get("/api/progress/days/2026-09-07").json()["day"]
    h.is_archived = True
    # Local midnight is converted to UTC just as persisted production timestamps.
    h.archived_at = datetime(2026, 9, 9).astimezone(UTC)
    session.commit()
    assert load_histories(session, h.id)[0].archived_on == MON + timedelta(days=2)
    assert client.get("/api/progress/days/2026-09-07").json()["day"] == before
    data = client.get(f"/api/habits/{h.id}/progress").json()
    assert data["current_progress"] is None
    assert data["streak"]["current_streak"] == 2
    assert client.get("/api/progress/days/2026-09-09").json()["day"]["score"] is None
    assert client.get("/api/days/2026-09-07").json()["items"][0]["entry"]["status"] == "done"
    assert client.get("/api/progress/weeks/2026-09-21").json()["score"] is None


def test_unknown_archive_date_is_not_guessed(session, health_area):
    h = make(session, health_area["id"])
    h.is_archived = True
    h.archived_at = None
    session.commit()
    assert load_histories(session, h.id)[0].archived_on == date.min


@pytest.mark.parametrize("path,status", [("/api/progress/days/no-date", 422), ("/api/progress/weeks/no-date", 422), ("/api/habits/999/progress", 404)])
def test_progress_errors(client, path, status):
    response = client.get(path)
    assert response.status_code == status
    assert "error" in response.json()


def test_no_habits_null_score(client):
    data = client.get("/api/progress/days/2026-09-09").json()
    assert data["day"]["score"] is None
    assert data["week"]["score"] is None
    assert data["streaks"] == []
