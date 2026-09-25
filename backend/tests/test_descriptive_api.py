"""Integration: one 7A build, dynamic history, API bounds, query/read purity."""

from datetime import date, timedelta
import json

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Area
from app.domain.analytics.types import Availability as A
from app.domain.daily_state import StateValues
from app.domain.schedule import Schedule
from app.schemas.descriptive import DescriptiveAnalyticsRead
from app.services import analytics, daily_state, habits
from app.services.descriptive import get_descriptive
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make, save


def get(session, start=MON, end=None, keys=("state.mood",), today=None):
    return get_descriptive(session, start, end or start, keys, today=today or MON + timedelta(days=100))


def test_dynamic_habits_status_quantity_config_and_score_semantics(session, health_area):
    area = health_area["id"]
    h = make(session, area, start=MON + timedelta(days=1), tracking_mode="binary_quantity", quantity_unit="км")
    save(session, h.id, 2, "skipped", skip_reason="Отдых")
    save(session, h.id, 3, "missed", quantity_value=0)
    save(session, h.id, 4, quantity_value=6)
    habits.update_habit(session, h.id, config(area, name="Другое имя", weight=3,
                        tracking_mode="binary_quantity", quantity_unit="м"),
                        effective_date=MON + timedelta(days=5))
    save(session, h.id, 5, quantity_value=500)
    prefix = f"habit.{h.id}.daily"
    result = get(session, end=MON + timedelta(days=6), keys=(f"{prefix}.status", f"{prefix}.quantity", "daily.score"))
    by_key = {a.variable.key: a for a in result.variables}
    status = by_key[f"{prefix}.status"]
    completed = status.summary.statistics.habit_completion
    assert (completed.completed_count, completed.missed_count, completed.skipped_count,
            completed.unmarked_count, completed.applicable_count) == (2, 1, 1, 2, 6)
    assert completed.completion_rate_among_observed == 0.5
    assert status.summary.coverage.counts_by_availability[A.NOT_APPLICABLE] == 1
    assert status.comparison.previous.coverage.eligible_count == 0
    quantity = by_key[f"{prefix}.quantity"]
    assert quantity.summary.units == ("км", "м")
    assert quantity.summary.statistics.status == "incompatible_units"
    assert quantity.summary.statistics.mean is None
    assert quantity.series[3].value == 0 and quantity.series[3].unit == "км"
    assert quantity.series[5].value == 500 and quantity.series[5].unit == "м"
    assert quantity.series[2].availability == A.FIELD_MISSING
    score = by_key["daily.score"]
    assert score.series[0].availability == A.NO_OBLIGATIONS
    assert score.series[1].value == 0 and score.series[1].availability == A.PRESENT
    assert score.series[4].value == 100
    assert all(a.variable.habit_id == h.id for a in (status, quantity))


def test_weekly_habits_canonical_progress_and_partial_activation(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=3),
             schedule=Schedule.create("times_per_week", times_per_week=2))
    save(session, h.id, 3)
    save(session, h.id, 4)
    keys = (f"habit.{h.id}.weekly.completed_count", f"habit.{h.id}.weekly.quota", "weekly.score")
    result = get(session, end=MON + timedelta(days=13), keys=keys)
    dataset = analytics.get_dataset(session, MON, MON + timedelta(days=13), today=result.today)
    for analysis in result.variables:
        assert [p.value for p in analysis.series] == [r.values[analysis.variable.key].value for r in dataset.weekly]
        assert analysis.comparison.status == "incomplete_period"
    completed = result.variables[0]
    assert completed.series[0].week.applicable_habit_days == 4
    assert completed.series[0].value == 2 and completed.series[1].value == 0


def test_independent_daily_state_fields(session):
    for i, values in enumerate([
        dict(gaming=False, gaming_minutes=0, computer_overuse=False, computer_minutes=180, alcohol=True),
        dict(gaming=True, gaming_minutes=None, computer_overuse=None, computer_minutes=0, alcohol=False),
        dict(note="Никаких выводов из заметки"),
    ]):
        daily_state.save_state(session, MON + timedelta(days=i), StateValues(**values), today=MON + timedelta(days=5))
    keys = tuple(f"state.{name}" for name in ("gaming", "gaming_minutes", "computer_overuse", "computer_minutes", "alcohol"))
    by_key = {a.variable.key: a for a in get(session, end=MON + timedelta(days=2), keys=keys).variables}
    assert by_key["state.gaming"].summary.statistics.true_rate == 0.5
    assert by_key["state.gaming_minutes"].summary.statistics.mean == 0
    assert by_key["state.gaming_minutes"].summary.coverage.observed_count == 1
    assert by_key["state.computer_overuse"].summary.statistics.true_rate == 0
    assert by_key["state.computer_overuse"].summary.coverage.observed_count == 1
    assert by_key["state.computer_minutes"].summary.statistics.mean == 90
    assert by_key["state.alcohol"].summary.statistics.true_rate == 0.5


def test_api_response_deterministic_typed_and_clock(client, app, session):
    app.state.clock = FrozenClock(MON)
    daily_state.save_state(session, MON, StateValues(alcohol=False, gaming_minutes=0, gaming=False, mood=2), today=MON)
    params = [("start", MON.isoformat()), ("end", (MON + timedelta(days=1)).isoformat()),
              ("variables", "state.mood"), ("variables", "state.alcohol"), ("variables", "state.gaming_minutes"),
              ("variables", "state.sleep_status")]
    response = client.get("/api/analytics/descriptive", params=params)
    assert response.status_code == 200, response.text
    result = DescriptiveAnalyticsRead.model_validate_json(response.text).root
    assert result.today == MON and result.contract_version == "7B.1"
    assert result.previous_period.start == MON - timedelta(days=2)
    assert [a.variable.key for a in result.variables] == sorted(a.variable.key for a in result.variables)
    assert result.variables[0].series[0].value is False
    assert result.variables[1].series[0].value == 0
    assert type(result.variables[2].series[0].value) is int
    assert all(a.comparison.status == "incomplete_period" for a in result.variables)
    assert client.get("/api/analytics/descriptive", params=params).text == response.text
    assert client.post("/api/analytics/descriptive", params=params).status_code == 405
    json.dumps(response.json(), allow_nan=False)


@pytest.mark.parametrize("params", [
    {}, {"start": "bad", "end": "2026-09-01", "variables": "state.mood"},
    {"start": "2026-09-01", "end": "2026-09-07"},
    {"start": "2026-09-08", "end": "2026-09-01", "variables": "state.mood"},
    {"start": "2000-01-01", "end": "2026-09-01", "variables": "state.mood"},
    {"start": "0001-01-01", "end": "0001-01-01", "variables": "state.mood"},
    {"start": "2026-09-01", "end": "2026-09-07", "variables": ["state.mood"] * 65},
    {"start": "2026-09-01", "end": "2026-09-07", "variables": ["state.mood"] * 2},
    {"start": "2026-09-01", "end": "2026-09-07", "variables": ""},
    {"start": "2026-09-01", "end": "2026-09-07", "variables": "not-a-variable"},
])
def test_invalid_api_input_is_russian(client, params):
    response = client.get("/api/analytics/descriptive", params=params)
    assert response.status_code == 422, response.text
    message = response.json()["error"]["message"]
    assert any("А" <= letter <= "я" for letter in message)


def test_bounds_checked_before_build(session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid range must be rejected before loading")
    monkeypatch.setattr(analytics, "get_dataset", forbidden)
    with pytest.raises(ValueError):
        get(session, end=MON + timedelta(days=1830))
    with pytest.raises(ValueError):
        get(session, keys=())


def test_http_requests_preserve_source_database(database, session, health_area, client):
    h = make(session, health_area["id"])
    save(session, h.id, 0)
    save(session, h.id, 1, "skipped", skip_reason="Отдых")
    daily_state.save_state(session, MON, StateValues(alcohol=False, mood=5), today=MON)
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    for key in (f"habit.{h.id}.daily.status", "state.mood", "state.alcohol", "weekly.score"):
        response = client.get("/api/analytics/descriptive", params={
            "start": MON.isoformat(), "end": (MON + timedelta(days=6)).isoformat(), "variables": key})
        assert response.status_code == 200, response.text
    with database.engine.connect() as connection:
        after = list(connection.connection.driver_connection.iterdump())
    assert after == before


def test_one_build_four_selects_readonly_and_no_autoflush(database, session, health_area, monkeypatch):
    for _ in range(12):
        make(session, health_area["id"], start=date(2023, 1, 1))
    daily_state.save_state(session, MON, StateValues(mood=4), today=MON)
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    builds = []
    original = analytics.get_dataset

    def counted(*args, **kwargs):
        builds.append((args[1], args[2]))
        return original(*args, **kwargs)

    monkeypatch.setattr(analytics, "get_dataset", counted)
    statements = []

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        for start, end in ((MON, MON), (date(2024, 1, 1), date(2024, 12, 31))):
            with Session(database.engine, autoflush=True) as reading:
                pending = Area(name="Не сохранять", color="#ffffff")
                reading.add(pending)
                # Read an existing row without flushing the pending object.
                with reading.no_autoflush:
                    dirty = reading.get(Area, health_area["id"])
                dirty.name = "Не сохранять изменение"
                statements.clear()
                builds.clear()
                result = get(reading, start, end, ("state.mood", "state.alcohol", "weekly.state.mood.mean", "daily.score"))
                assert len(builds) == 1
                assert builds[0] == (start - timedelta(days=(end - start).days + 1), end)
                assert len(statements) == 4
                assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
                assert pending in reading.new and pending.id is None
                assert dirty in reading.dirty and not reading.deleted
                statements.clear()
                DescriptiveAnalyticsRead(result).model_dump_json()
                assert not statements
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        after = list(connection.connection.driver_connection.iterdump())
    assert after == before
