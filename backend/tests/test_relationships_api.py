"""Real canonical loading, dynamic habits, HTTP contract, query count and purity."""

from datetime import date, timedelta
import json

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Area
from app.domain.analytics.relationship_types import POLICY
from app.domain.analytics.types import Availability as A
from app.domain.daily_state import StateValues
from app.domain.schedule import Schedule
from app.schemas.relationships import RelationshipAnalyticsRead
from app.services import analytics, daily_state, habits
from app.services.relationships import get_relationships
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make, save


def get(session, keys, *, start=MON, end=None, today=None, pair=True):
    return get_relationships(session, start, end or MON + timedelta(days=6), keys,
                             today=today or MON + timedelta(days=100), pair=pair)


def test_habit_completion_state_habit_and_quantity_stable_after_rename(session, health_area):
    area = health_area["id"]
    h = make(session, area, tracking_mode="binary_quantity", quantity_unit="км")
    other = make(session, area)
    for i in range(6):
        status = "done" if i % 2 else "missed"
        save(session, h.id, i, status, quantity_value=i)
        save(session, other.id, i, status)
        daily_state.save_state(session, MON + timedelta(days=i),
                               StateValues(mood=5 if i % 2 else 1, energy=i % 5 + 1), today=MON + timedelta(days=6))
    completion = f"habit.{h.id}.daily.completion"
    quantity = f"habit.{h.id}.daily.quantity"
    keys = (completion, f"habit.{other.id}.daily.completion")
    before = get(session, keys)
    habits.update_habit(session, h.id, config(area, name="Новое имя", weight=3,
                        tracking_mode="binary_quantity", quantity_unit="км"), effective_date=MON + timedelta(days=3))
    assert get(session, keys) == before
    result = before.relationships[0]
    assert result.method == "phi" and result.coefficient == pytest.approx(1) and result.n == 6
    result = get(session, (completion, "state.mood")).relationships[0]
    assert result.method == "point_biserial" and result.coefficient == pytest.approx(1)
    assert result.boolean_x.true_count == result.boolean_x.false_count == 3
    result = get(session, (quantity, "state.energy")).relationships[0]
    assert result.method == "spearman" and result.n == 6 and result.units_x == ("км",)
    # A unit change is suppressed even when the counterpart has no observation.
    habits.update_habit(session, h.id, config(area, tracking_mode="binary_quantity", quantity_unit="м"),
                        effective_date=MON + timedelta(days=6))
    save(session, h.id, 6, quantity_value=500)
    result = get(session, (quantity, "state.energy")).relationships[0]
    assert result.status == "incompatible_units" and result.n == 6 and result.coefficient is None
    assert result.units_x == ("км", "м")


def test_canonical_completion_extension_keeps_status_missing_and_applicability(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=1))
    save(session, h.id, 2, "skipped", skip_reason="Отдых")
    save(session, h.id, 3, "missed")
    save(session, h.id, 4, "done")
    data = analytics.get_dataset(session, MON, MON + timedelta(days=6), today=MON + timedelta(days=5))
    key = f"habit.{h.id}.daily.completion"
    cells = [row.values[key] for row in data.daily]
    assert [c.value for c in cells] == [None, None, False, False, True, None, None]
    assert [c.availability for c in cells] == [A.NOT_APPLICABLE, A.SOURCE_MISSING, A.PRESENT,
                                              A.PRESENT, A.PRESENT, A.SOURCE_MISSING, A.FUTURE]
    assert data.daily[2].values[f"habit.{h.id}.daily.status"].value == "skipped"
    result = get(session, (key, "daily.score"), today=MON + timedelta(days=5)).relationships[0]
    assert result.n == 3 and result.coverage.missing_count == 2
    assert result.coverage.excluded_count == 2


def test_weekly_partial_habit_activity_uses_descriptive_metadata(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=3),
             schedule=Schedule.create("times_per_week", times_per_week=2))
    save(session, h.id, 3)
    result = get(session, (f"habit.{h.id}.weekly.completed_count", "weekly.score"),
                 end=MON + timedelta(days=41)).relationships[0]
    assert result.n == 5 and result.coverage.losses["incomplete_period"] == 1


def test_api_pair_matrix_clock_roundtrip_read_only(database, session, client, app):
    app.state.clock = FrozenClock(MON + timedelta(days=5))
    for i in range(6):
        daily_state.save_state(session, MON + timedelta(days=i),
                               StateValues(mood=i % 5 + 1, sleep_minutes=100 + i, alcohol=bool(i % 2)),
                               today=MON + timedelta(days=5))
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    params = {"start": MON.isoformat(), "end": (MON + timedelta(days=6)).isoformat(),
              "x": "state.sleep_minutes", "y": "state.mood"}
    response = client.get("/api/analytics/relationships", params=params)
    assert response.status_code == 200, response.text
    parsed = RelationshipAnalyticsRead.model_validate_json(response.text).root
    assert parsed.contract_version == "7C.1" and parsed.today == app.state.clock.today()
    assert parsed.relationships[0].n == 6 and parsed.relationships[0].x.key == params["x"]
    assert parsed.mode == "pair" and parsed.relationships[0].method == "spearman"
    assert client.get("/api/analytics/relationships", params=params).text == response.text
    assert client.post("/api/analytics/relationships", params=params).status_code == 405
    matrix = {"start": params["start"], "end": params["end"],
              "variables": ["state.mood", "state.sleep_minutes", "state.alcohol"]}
    response = client.get("/api/analytics/relationships", params=matrix)
    assert response.status_code == 200 and len(response.json()["relationships"]) == 3
    assert client.get("/api/analytics/relationships", params=matrix).text == response.text
    json.dumps(response.json(), allow_nan=False)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before
    schema = client.get("/api/openapi.json").json()
    assert "/api/analytics/relationships" in schema["paths"]


@pytest.mark.parametrize("params", [
    {}, {"x": "state.mood"}, {"y": "state.mood"},
    {"x": "state.mood", "y": "state.mood"},
    {"x": "state.mood", "y": "unknown"},
    {"variables": ["state.mood"]}, {"variables": ["state.mood"] * 25},
    {"variables": ["state.mood", "state.energy"], "x": "state.mood"},
    {"variables": ["state.mood", "state.energy"], "y": "state.mood"},
    {"x": "", "y": "state.mood"}, {"x": "x" * 161, "y": "state.mood"},
    {"start": "bad", "x": "state.mood", "y": "state.energy"},
    {"start": "2026-10-01", "x": "state.mood", "y": "state.energy"},
    {"start": "2000-01-01", "x": "state.mood", "y": "state.energy"},
])
def test_api_validation_localized(client, params):
    response = client.get("/api/analytics/relationships", params={
        "start": MON.isoformat(), "end": (MON + timedelta(days=6)).isoformat(), **params})
    assert response.status_code == 422, response.text
    assert any("А" <= c <= "я" for c in response.json()["error"]["message"])


def test_missing_required_dates(client):
    assert client.get("/api/analytics/relationships", params={"x": "state.mood", "y": "state.energy"}).status_code == 422


def test_limits_rejected_before_loading(session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid request must be rejected before dataset loading")
    monkeypatch.setattr(analytics, "get_dataset", forbidden)
    with pytest.raises(ValueError):
        get(session, ("x", "y"), end=MON + timedelta(days=POLICY.max_period_days))
    with pytest.raises(ValueError):
        get(session, tuple(str(i) for i in range(POLICY.max_variables + 1)), pair=False)


def test_matrix_one_build_four_selects_and_no_autoflush(database, session, health_area, monkeypatch):
    for _ in range(12):
        make(session, health_area["id"], start=date(2023, 1, 1))
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    original = analytics.get_dataset
    builds, statements, dataset_builds = [], [], []
    original_builder = analytics.build_dataset

    def counted(*args, **kwargs):
        builds.append((args[1], args[2]))
        return original(*args, **kwargs)

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def counted_builder(*args, **kwargs):
        dataset_builds.append((args[1], args[2]))
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(analytics, "get_dataset", counted)
    monkeypatch.setattr(analytics, "build_dataset", counted_builder)
    event.listen(database.engine, "before_cursor_execute", record)
    try:
        for start, end, size in [(MON, MON, 2), (date(2024, 1, 1), date(2024, 12, 31), 24)]:
            with Session(database.engine, autoflush=True) as reading:
                pending = Area(name="Не сохранять", color="#ffffff")
                reading.add(pending)
                with reading.no_autoflush:
                    dirty = reading.get(Area, health_area["id"])
                dirty.name = "Не сохранять изменение"
                keys = tuple(v.key for v in analytics.get_dataset(reading, start, end, today=end).variables[:size])
                builds.clear()
                dataset_builds.clear()
                statements.clear()
                result = get(reading, keys, start=start, end=end, pair=False)
                assert builds == [(start, end)]
                assert dataset_builds == [(start, end)]
                assert len(result.relationships) == size * (size - 1) // 2
                assert len(statements) == 4 and all(s.lstrip().upper().startswith("SELECT") for s in statements)
                assert pending in reading.new and pending.id is None
                assert dirty in reading.dirty and not reading.deleted
                statements.clear()
                RelationshipAnalyticsRead(result).model_dump_json()
                assert statements == []
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before
