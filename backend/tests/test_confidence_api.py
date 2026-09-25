"""7A loading, query count, read purity, lag extension and the confidence HTTP contract."""

from dataclasses import fields
from datetime import date, timedelta
import json

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Area
from app.domain.analytics.builder import dates
from app.domain.analytics.relationship_types import POLICY, Relationship
from app.domain.daily_state import StateValues
from app.schemas.confidence import ConfidenceAnalyticsRead
from app.services import analytics, daily, daily_state, habits
from app.services.confidence import get_confidence
from app.services.relationships import get_relationships
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make


TODAY = MON + timedelta(days=100)
KEYS = ("state.sleep_minutes", "state.computer_minutes")


def get(session, keys=KEYS, *, start=MON, end=None, lag=0, today=TODAY):
    return get_confidence(session, start, end or MON + timedelta(days=89), *keys,
                          lag=lag, today=today)


def save_entry(session, habit_id, offset, status="done", **values):
    daily.save_entry(session, habit_id, MON + timedelta(days=offset), status=status,
                     today=TODAY, **values)


def seed_states(session, start, end):
    for index, on in enumerate(dates(start, end)):
        daily_state.save_state(session, on, StateValues(
            sleep_minutes=600 + index % 30 * 4, computer_minutes=650 + index % 30 * 4,
            mood=index % 5 + 1, alcohol=bool(index % 2)), today=TODAY)


def test_service_reports_three_segments_over_the_requested_period(session):
    seed_states(session, MON, MON + timedelta(days=89))
    result = get(session)
    assert result.contract_version == "7E.1" and result.status == "evaluated"
    assert result.confidence == "well_supported" and result.lag == 0
    assert [segment.name for segment in result.segments] == ["early", "middle", "recent"]
    assert all(segment.period.start >= MON and segment.period.end <= MON + timedelta(days=89)
               for segment in result.segments)
    assert sum(segment.relationship.n for segment in result.segments) == 90
    assert result.evidence.sample.n == 90 and result.evidence.coverage.pair_coverage == 1


@pytest.mark.parametrize("lag", [7, -7, 1])
def test_lag_source_range_extends_without_losing_x(session, lag):
    seed_states(session, MON - timedelta(days=8), MON + timedelta(days=97))
    result = get(session, lag=lag)
    assert result.lag == lag and result.lag_unit == "day"
    first = result.segments[0]
    assert first.period.start == MON
    assert first.relationship.x_period.start == MON - timedelta(days=lag)
    assert first.relationship.x_period.end == first.period.end - timedelta(days=lag)
    for segment in result.segments:
        assert segment.relationship.n == segment.relationship.coverage.requested_count
        assert segment.relationship.coverage.losses["missing"] == 0
    assert result.source_range.start == MON - timedelta(days=max(lag, 0))
    assert result.source_range.end == MON + timedelta(days=89 - min(lag, 0))


def test_default_lag_is_same_period_and_equals_stage_7c(session):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=95))
    expected = get_relationships(session, MON, MON + timedelta(days=89), KEYS,
                                today=TODAY, pair=True).relationships[0]
    result = get(session)
    assert result.lag == 0
    assert {field.name: getattr(result.relationship, field.name) for field in fields(Relationship)} == {
        field.name: getattr(expected, field.name) for field in fields(Relationship)}


def test_dynamic_habit_identity_and_historical_units(session, health_area):
    habit = make(session, health_area["id"], tracking_mode="binary_quantity", quantity_unit="км")
    for offset in range(90):
        save_entry(session, habit.id, offset, quantity_value=offset % 7 + 1)
        daily_state.save_state(session, MON + timedelta(days=offset),
                               StateValues(sleep_minutes=600 + offset % 30 * 4), today=TODAY)
    quantity = f"habit.{habit.id}.daily.quantity"
    before = get(session, (quantity, KEYS[0]))
    assert before.status == "evaluated" and before.relationship.units_x == ("км",)
    assert before.confidence in ("stable", "well_supported")
    habits.update_habit(session, habit.id, config(health_area["id"], name="Переименовано",
                                                 tracking_mode="binary_quantity",
                                                 quantity_unit="м", weight=3),
                        effective_date=MON + timedelta(days=45))
    after = get(session, (quantity, KEYS[0]))
    assert after.status == "not_evaluable" and after.confidence is None
    assert after.reason == "incompatible_units"
    assert "incompatible_units" in [caveat.code for caveat in after.caveats]
    assert after.relationship.units_x == ("км", "м")


def test_api_contract_round_trip_caveats_and_read_only(database, session, client, app):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=95))
    app.state.clock = FrozenClock(MON + timedelta(days=95))
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    params = {"start": str(MON), "end": str(MON + timedelta(days=89)),
              "x": KEYS[0], "y": KEYS[1]}
    for selection, lag in (({}, 0), ({"lag": 5}, 5), ({"lag": -5}, -5)):
        response = client.get("/api/analytics/confidence", params={**params, **selection})
        assert response.status_code == 200, response.text
        parsed = ConfidenceAnalyticsRead.model_validate_json(response.text).root
        assert parsed.contract_version == "7E.1" and parsed.today == app.state.clock.today()
        assert parsed.confidence_policy_version == parsed.policy.version == "1"
        assert parsed.policy.stable_minimum_n == 20
        assert parsed.lag == lag and len(parsed.segments) == 3
        assert parsed.evidence.sample.n == 90
        assert "association_not_causation" in [caveat.code for caveat in parsed.caveats]
        assert all(caveat.label and caveat.message for caveat in parsed.caveats)
        assert client.get("/api/analytics/confidence", params={**params, **selection}).text == response.text
        json.dumps(response.json(), allow_nan=False)
    assert client.post("/api/analytics/confidence", params=params).status_code == 405
    assert "/api/analytics/confidence" in client.get("/api/openapi.json").json()["paths"]
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before


def test_api_short_period_has_fewer_segments_and_is_not_well_supported(client, session):
    seed_states(session, MON, MON + timedelta(days=9))
    response = client.get("/api/analytics/confidence", params={
        "start": str(MON), "end": str(MON + timedelta(days=9)), "x": KEYS[0], "y": KEYS[1]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["segments"]) == 3 and data["confidence"] == "preliminary"
    entry = client.get("/api/analytics/confidence", params={
        "start": str(MON), "end": str(MON), "x": KEYS[0], "y": KEYS[1]}).json()
    assert len(entry["segments"]) == 1 and entry["status"] == "not_evaluable"
    assert entry["confidence"] is None and entry["reason"] == "insufficient_data"


def test_api_grain_mismatch_is_typed(client):
    response = client.get("/api/analytics/confidence", params={
        "start": str(MON), "end": str(MON + timedelta(days=20)),
        "x": "state.mood", "y": "weekly.state.mood.mean"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_evaluable"
    assert response.json()["reason"] == "grain_mismatch"


@pytest.mark.parametrize("params", [
    {"x": ""}, {"x": " "}, {"x": "x" * 161}, {"y": "state.sleep_minutes"},
    {"x": "unknown"}, {"x": "habit.999.daily.quantity"}, {"x": "habit.no.daily.quantity"},
    {"lag": 8}, {"lag": -8}, {"lag": "1.5"}, {"lag": "bad"},
    {"start": "bad"}, {"end": "2026-01-01"}, {"start": "2000-01-01"},
    {"start": "0001-01-01", "end": "0001-01-02", "lag": 1},
    {"start": "9999-12-30", "end": "9999-12-31", "lag": -1},
])
def test_api_validation_is_bounded_and_localized(client, params):
    response = client.get("/api/analytics/confidence", params={
        "start": str(MON), "end": str(MON + timedelta(days=6)), "x": KEYS[0], "y": KEYS[1], **params})
    assert response.status_code == 422, response.text
    assert any("А" <= letter <= "я" for letter in response.json()["error"]["message"])


@pytest.mark.parametrize("missing", ["start", "end", "x", "y"])
def test_required_parameters(client, missing):
    params = {"start": str(MON), "end": str(MON + timedelta(days=6)), "x": KEYS[0], "y": KEYS[1]}
    del params[missing]
    assert client.get("/api/analytics/confidence", params=params).status_code == 422


def test_invalid_requests_rejected_before_loading(session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid request must not load data")
    monkeypatch.setattr(analytics, "get_dataset", forbidden)
    for kwargs in ({"lag": 8}, {"end": MON + timedelta(days=POLICY.max_period_days)},
                   {"start": MON + timedelta(days=1), "end": MON},
                   {"keys": ("unknown", KEYS[1])},
                   {"start": date.min, "end": date.min, "lag": 1}):
        with pytest.raises(ValueError):
            get(session, **kwargs)


@pytest.mark.parametrize("keys", [KEYS, ("weekly.state.sleep_minutes.mean",
                                        "weekly.state.computer_minutes.mean")])
@pytest.mark.parametrize("lag", [0, 7])
def test_one_build_four_selects_for_the_full_period_and_segments(
        database, session, health_area, monkeypatch, keys, lag):
    for _ in range(12):
        make(session, health_area["id"], start=date(2023, 1, 1))
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    builds, loads, statements = [], [], []
    original, builder = analytics.get_dataset, analytics.build_dataset

    def counted(*args, **kwargs):
        loads.append((args[1], args[2]))
        return original(*args, **kwargs)

    def counted_builder(*args, **kwargs):
        builds.append((args[1], args[2]))
        return builder(*args, **kwargs)

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    monkeypatch.setattr(analytics, "get_dataset", counted)
    monkeypatch.setattr(analytics, "build_dataset", counted_builder)
    event.listen(database.engine, "before_cursor_execute", record)
    try:
        with Session(database.engine, autoflush=True) as reading:
            pending = Area(name="Не сохранять", color="#ffffff")
            reading.add(pending)
            with reading.no_autoflush:
                dirty = reading.get(Area, health_area["id"])
            dirty.name = "Не сохранять изменение"
            statements.clear()
            loads.clear()
            builds.clear()
            result = get(reading, keys, start=date(2024, 1, 1), end=date(2024, 3, 31), lag=lag)
            assert len(result.segments) == 3
            assert len(loads) == len(builds) == 1 and loads == builds
            assert loads[0] == (result.source_range.start, result.source_range.end)
            assert len(statements) == 4
            assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
            assert pending in reading.new and pending.id is None
            assert dirty in reading.dirty and not reading.deleted
            statements.clear()
            ConfidenceAnalyticsRead(result).model_dump_json()
            assert statements == []
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before
