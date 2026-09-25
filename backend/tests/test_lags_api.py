"""7A loading, history, query count, read purity, and lag HTTP contract."""

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
from app.domain.schedule import Schedule
from app.schemas.lags import LagAnalyticsRead
from app.services import analytics, daily_state, habits
from app.services.lags import get_lags
from app.services.relationships import get_relationships
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make, save


TODAY = MON + timedelta(days=100)
KEYS = ("state.sleep_minutes", "state.computer_minutes")


def get(session, keys=KEYS, lags=(1,), *, start=MON, end=None, today=TODAY):
    return get_lags(session, start, end or MON + timedelta(days=6), *keys, lags, today=today)


def seed_states(session, start, end):
    for i, on in enumerate(dates(start, end)):
        daily_state.save_state(session, on, StateValues(
            sleep_minutes=100 + i, computer_minutes=2 * i, mood=i % 5 + 1, alcohol=bool(i % 2)), today=TODAY)


@pytest.mark.parametrize("lag", [7, -7])
def test_service_fetches_august_and_october_for_september(session, lag):
    seed_states(session, date(2026, 8, 25), date(2026, 10, 7))
    result = get(session, lags=(lag,), start=date(2026, 9, 1), end=date(2026, 9, 30))
    r = result.results[0]
    assert r.n == r.potential_aligned_count == 30 and r.coefficient == pytest.approx(1)
    assert result.source_range.start == (date(2026, 8, 25) if lag > 0 else date(2026, 9, 1))
    assert result.source_range.end == (date(2026, 9, 30) if lag > 0 else date(2026, 10, 7))


def test_habit_completion_rename_and_state_relationships(session, health_area):
    area = health_area["id"]
    h, other = make(session, area), make(session, area)
    for i in range(6):
        status = "done" if i % 2 else "missed"
        save(session, h.id, i, status)
        save(session, other.id, i + 1, status)
        daily_state.save_state(session, MON + timedelta(days=i + 1),
                               StateValues(mood=5 if i % 2 else 1, alcohol=bool(i % 2)), today=TODAY)
    completion = f"habit.{h.id}.daily.completion"
    keys = (completion, f"habit.{other.id}.daily.completion")
    before = get(session, keys, start=MON + timedelta(days=1))
    habits.update_habit(session, h.id, config(area, name="Переименовано", weight=3),
                        effective_date=MON + timedelta(days=3))
    assert get(session, keys, start=MON + timedelta(days=1)) == before
    r = before.results[0]
    assert r.n == 6 and r.method == "phi" and r.coefficient == pytest.approx(1)
    assert r.boolean_x.true_count == r.boolean_x.false_count == 3
    for key, method in (("state.mood", "point_biserial"), ("state.alcohol", "phi")):
        r = get(session, (completion, key), start=MON + timedelta(days=1)).results[0]
        assert r.n == 6 and r.method == method and r.coefficient == pytest.approx(1)


def test_history_uses_each_original_date_and_unit_window_before_pairwise_deletion(session, health_area):
    area = health_area["id"]
    h = make(session, area, tracking_mode="binary_quantity", quantity_unit="км")
    for i in range(7):
        save(session, h.id, i, quantity_value=i + 1)
        daily_state.save_state(session, MON + timedelta(days=i + 1), StateValues(sleep_minutes=(i + 1) * 10), today=TODAY)
    habits.update_habit(session, h.id, config(area, tracking_mode="binary_quantity", quantity_unit="м", weight=3,
                        schedule=Schedule.create("weekdays", weekdays=[0, 2, 4])),
                        effective_date=MON + timedelta(days=6))
    quantity = f"habit.{h.id}.daily.quantity"
    # Y on Sunday must still pair with X Saturday in kilometres, although
    # Sunday's own configuration has already changed to metres.
    r = get(session, (quantity, KEYS[0]), start=MON + timedelta(days=1)).results[0]
    assert r.n == 6 and r.units_x == ("км",) and r.coefficient == pytest.approx(1)
    # On the next Y date, X now has a new unit. Suppress even if Y is missing.
    daily_state.delete_state(session, MON + timedelta(days=7), today=TODAY)
    r = get(session, (quantity, KEYS[0]), start=MON + timedelta(days=1), end=MON + timedelta(days=7)).results[0]
    assert r.n == 6 and r.units_x == ("км", "м")
    assert r.status == "incompatible_units" and r.coefficient is None
    assert all(m.reason == "mixed_quantity_units" for m in r.metrics)
    # A scan's expanded fetch must not contaminate a lag's own unit window.
    scan = get(session, (quantity, KEYS[0]), lags=(-1, 0, 1), start=MON + timedelta(days=1))
    assert scan.results[2].status == "ok" and scan.results[2].units_x == ("км",)
    weight = f"habit.{h.id}.daily.weight"
    r = get(session, (weight, KEYS[0]), start=MON + timedelta(days=1)).results[0]
    assert r.status == "constant_series"  # All X dates still had weight 1.
    required = f"habit.{h.id}.daily.required_weight"
    r = get(session, (required, KEYS[0]), start=MON + timedelta(days=1)).results[0]
    assert r.n == 6  # The changed Sunday schedule cannot erase Saturday's X.


def test_habit_applicability_skipped_missing_and_future_are_preserved(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=1))
    for i, status in ((2, "skipped"), (3, "missed"), (4, "done")):
        save(session, h.id, i, status, **({"skip_reason": "Отдых"} if status == "skipped" else {}))
    seed_states(session, MON, MON + timedelta(days=7))
    r = get(session, (f"habit.{h.id}.daily.completion", KEYS[0]),
            start=MON + timedelta(days=1), end=MON + timedelta(days=7), today=MON + timedelta(days=6)).results[0]
    assert r.n == 3 and r.boolean_x.false_count == 2 and r.boolean_x.true_count == 1
    assert r.coverage.losses["not_eligible"] == 1
    assert r.coverage.losses["missing"] == 2
    assert r.coverage.losses["future"] == 1
    assert r.coverage.eligible_count == 5 and r.coverage.pair_coverage == 3 / 5


def test_weekly_habit_partial_activity_and_historical_quota(session, health_area):
    area = health_area["id"]
    h = make(session, area, start=MON + timedelta(days=3),
             schedule=Schedule.create("times_per_week", times_per_week=2))
    habits.update_habit(session, h.id, config(area, schedule=Schedule.create("times_per_week", times_per_week=4)),
                        effective_date=MON + timedelta(days=14))
    result = get(session, (f"habit.{h.id}.weekly.quota", "weekly.required_weight"),
                 start=MON + timedelta(days=7), end=MON + timedelta(days=48)).results[0]
    assert result.lag_unit == "week" and result.n == 5
    assert result.coverage.losses["incomplete_period"] == 1  # X creation week.
    assert result.potential_aligned_count == 6


def test_habit_only_in_extended_source_range_is_resolved(session, health_area):
    h = make(session, health_area["id"])
    save(session, h.id, 0)
    # A future-created habit isn't present in the target range's 7A registry,
    # but is a valid X identity when a negative lag reaches its lifetime.
    result = get(session, (f"habit.{h.id}.daily.completion", "daily.weekend"), (-7,),
                 start=MON - timedelta(days=7), end=MON - timedelta(days=1)).results[0]
    assert result.n == 1 and result.boolean_x.true_count == 1


@pytest.mark.parametrize("keys", [KEYS, ("weekly.state.sleep_minutes.mean", "weekly.state.mood.mean")])
def test_service_zero_lag_full_equality_in_multilag_scan(session, keys):
    seed_states(session, MON - timedelta(days=49), MON + timedelta(days=70))
    end = MON + timedelta(days=20)
    expected = get_relationships(session, MON, end, keys, today=TODAY, pair=True).relationships[0]
    scan = get(session, keys, (-7, 0, 7), end=end)
    assert {f.name: getattr(scan.results[1], f.name) for f in fields(Relationship)} == {
        f.name: getattr(expected, f.name) for f in fields(Relationship)}


def test_api_contract_modes_clock_roundtrip_and_read_only(database, session, client, app):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=6))
    app.state.clock = FrozenClock(MON + timedelta(days=5))
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    params = {"start": str(MON), "end": str(MON + timedelta(days=6)), "x": KEYS[0], "y": KEYS[1]}
    for selection, expected in (({}, [0]), ({"lag": 1}, [1]),
                                ({"lags": [7, 0, -1, 7]}, [-1, 0, 7]),
                                ({"lag_start": -7, "lag_end": 7}, list(range(-7, 8)))):
        response = client.get("/api/analytics/lags", params={**params, **selection})
        assert response.status_code == 200, response.text
        parsed = LagAnalyticsRead.model_validate_json(response.text).root
        assert parsed.contract_version == "7D.1" and parsed.today == app.state.clock.today()
        assert parsed.target_side == "y" and parsed.sign_convention == "positive_x_earlier"
        assert [r.lag for r in parsed.results] == expected
        assert all(r.x.key == KEYS[0] and r.y.key == KEYS[1] for r in parsed.results)
        assert client.get("/api/analytics/lags", params={**params, **selection}).text == response.text
        json.dumps(response.json(), allow_nan=False)
    assert client.post("/api/analytics/lags", params=params).status_code == 405
    assert "/api/analytics/lags" in client.get("/api/openapi.json").json()["paths"]
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before


@pytest.mark.parametrize("params", [
    {"x": ""}, {"x": " "}, {"x": "x" * 161}, {"y": "state.sleep_minutes"},
    {"x": "unknown"}, {"x": "habit.999.daily.quantity"}, {"x": "habit.no.daily.quantity"},
    {"lag": 8}, {"lag": -8}, {"lag": "1.5"}, {"lag": "bad"},
    {"lags": [0] * 16}, {"lags": [1, 8]}, {"lags": ["bad"]},
    {"lag": 1, "lags": [1]}, {"lag": 0, "lag_start": 0, "lag_end": 1},
    {"lag_start": 1}, {"lag_end": 1}, {"lag_start": 1, "lag_end": -1},
    {"lag_start": -1000000, "lag_end": 1000000},
    {"start": "bad"}, {"end": "2026-01-01"}, {"start": "2000-01-01"},
    {"start": "0001-01-01", "end": "0001-01-02", "lag": 1},
    {"start": "9999-12-30", "end": "9999-12-31", "lag": -1},
])
def test_api_validation_is_bounded_and_localized(client, params):
    response = client.get("/api/analytics/lags", params={
        "start": str(MON), "end": str(MON + timedelta(days=6)), "x": KEYS[0], "y": KEYS[1], **params})
    assert response.status_code == 422, response.text
    assert any("А" <= c <= "я" for c in response.json()["error"]["message"])


@pytest.mark.parametrize("missing", ["start", "end", "x", "y"])
def test_required_parameters(client, missing):
    params = {"start": str(MON), "end": str(MON), "x": KEYS[0], "y": KEYS[1]}
    del params[missing]
    assert client.get("/api/analytics/lags", params=params).status_code == 422


def test_api_grain_mismatch_typed(client):
    response = client.get("/api/analytics/lags", params={
        "start": str(MON), "end": str(MON), "x": "state.mood", "y": "weekly.state.mood.mean", "lag": 1})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "unsupported" and result["reason"] == "grain_mismatch"


def test_invalid_requests_rejected_before_loading(session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid request must not load data")
    monkeypatch.setattr(analytics, "get_dataset", forbidden)
    for kwargs in ({"lags": (8,)}, {"lags": (0,) * 16}, {"end": MON + timedelta(days=POLICY.max_period_days)},
                   {"keys": ("unknown", KEYS[1])}, {"start": date.min, "end": date.min, "lags": (1,)}):
        with pytest.raises(ValueError):
            get(session, **kwargs)


@pytest.mark.parametrize("keys", [KEYS, ("weekly.state.sleep_minutes.mean", "weekly.state.mood.mean")])
def test_one_build_four_selects_for_one_or_fifteen_lags_no_autoflush(
        database, session, health_area, monkeypatch, keys):
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
        for lags in ((1,), tuple(range(-7, 8))):
            with Session(database.engine, autoflush=True) as reading:
                pending = Area(name="Не сохранять", color="#ffffff")
                reading.add(pending)
                with reading.no_autoflush:
                    dirty = reading.get(Area, health_area["id"])
                dirty.name = "Не сохранять изменение"
                statements.clear()
                loads.clear()
                builds.clear()
                result = get(reading, keys, lags, start=date(2024, 1, 1), end=date(2024, 12, 31))
                assert len(result.results) == len(lags)
                assert len(loads) == len(builds) == 1 and loads == builds
                assert loads[0] == (result.source_range.start, result.source_range.end)
                assert len(statements) == 4
                assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
                assert pending in reading.new and pending.id is None
                assert dirty in reading.dirty and not reading.deleted
                statements.clear()
                LagAnalyticsRead(result).model_dump_json()
                assert statements == []
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before
