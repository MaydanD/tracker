"""Guardrail service/HTTP contract: families, read purity, SQL bound, integration."""

from datetime import date, timedelta
import json

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Area
from app.domain.analytics.builder import dates
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.guardrail_types import POLICY
from app.domain.daily_state import StateValues
from app.schemas.confidence import ConfidenceAnalyticsRead
from app.schemas.guardrails import GuardrailAnalyticsRead
from app.services import analytics, daily, daily_state, habits
from app.services.confidence import get_confidence
from app.services.guardrails import family_source_range, get_guardrails
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make


TODAY = MON + timedelta(days=120)
SLEEP, COMPUTER = "state.sleep_minutes", "state.computer_minutes"
WEEKLY = ("weekly.state.sleep_minutes.mean", "weekly.state.computer_minutes.mean")


def lcg(count, seed=7):
    value, out = seed, []
    for _ in range(count):
        value = (value * 1103515245 + 12345) % (2 ** 31)
        out.append(200 + value % 1000)
    return out


def seed_states(session, start, end, values=None):
    days = list(dates(start, end))
    if values is None:
        values = [StateValues(sleep_minutes=600 + index % 30 * 4,
                              computer_minutes=650 + index % 30 * 4,
                              mood=index % 5 + 1, alcohol=bool(index % 2))
                  for index in range(len(days))]
    for on, value in zip(days, values):
        daily_state.save_state(session, on, value, today=TODAY)


def seed_shifted(session, start, count, *, shift=2):
    """computer(t) equals sleep(t + shift), so the real association is a lag."""
    sleep = lcg(count + shift)
    days = list(dates(start, start + timedelta(days=count - 1)))
    for index, on in enumerate(days):
        daily_state.save_state(session, on, StateValues(sleep_minutes=sleep[index],
                                                        computer_minutes=sleep[index + shift]),
                               today=TODAY)


def single(session, *, start=MON, end=None, lag=0, keys=(SLEEP, COMPUTER)):
    return get_guardrails(session, start, end or MON + timedelta(days=89),
                          (keys + (lag,),), mode="single", today=TODAY)


def hypothesis(result, lag=0):
    return next(item for item in result.hypotheses if item.lag == lag)


# --- single hypothesis ---------------------------------------------------------------

def test_single_hypothesis_is_uncorrected_and_fully_reported(session):
    seed_states(session, MON, MON + timedelta(days=89))
    result = single(session)
    item = hypothesis(result)
    assert result.family.mode == "single"
    assert result.family.multiple_comparisons_checked is False
    assert result.family.requested_size == result.family.evaluable_size == 1
    assert item.multiple_comparisons.status == "not_applicable"
    assert item.multiple_comparisons.raw_p_value is not None
    assert item.multiple_comparisons.adjusted_q_value is None
    assert item.verdict == "pass"
    assert item.effect.coefficient is not None and item.effect.absolute_coefficient >= 0.15
    assert item.sample.n == 90 and item.coverage.pair_coverage == 1
    assert [check.name for check in item.checks] == [
        "sample_size", "coverage", "group_balance", "effect_size", "weekday_control",
        "temporal_stability", "multiple_comparisons"]


def test_lag_sign_keeps_the_stage_7d_semantics(session):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=96))
    for lag in (0, 5, -5):
        item = hypothesis(single(session, lag=lag), lag)
        assert item.lag == lag
        assert item.target_period == Period(MON, MON + timedelta(days=89))
        assert item.relationship.x_period.start == MON - timedelta(days=lag)
        assert item.relationship.x_period.end == MON + timedelta(days=89 - lag)
        assert item.relationship.n == 90


def test_binary_relationship_reports_group_evidence_and_balance(session):
    values = [StateValues(alcohol=index < 20, sleep_minutes=600 + index) for index in range(90)]
    seed_states(session, MON, MON + timedelta(days=89), values)
    item = hypothesis(single(session, keys=("state.alcohol", SLEEP)))
    assert item.effect.group.boolean_side == "x"
    assert item.effect.group.true_count == 20 and item.effect.group.false_count == 70
    assert item.effect.group.minority_share == pytest.approx(20 / 90)
    assert item.effect.group.true_mean is not None
    assert next(check for check in item.checks if check.name == "group_balance").status == "passed"


def test_dynamic_habit_variable_flows_through_guardrails(session, health_area):
    habit = make(session, health_area["id"], tracking_mode="binary_quantity", quantity_unit="км")
    for offset in range(90):
        daily.save_entry(session, habit.id, MON + timedelta(days=offset), status="done",
                         quantity_value=offset % 7 + 1, today=TODAY)
        daily_state.save_state(session, MON + timedelta(days=offset),
                               StateValues(sleep_minutes=600 + offset % 30 * 4), today=TODAY)
    quantity = f"habit.{habit.id}.daily.quantity"
    before = hypothesis(single(session, keys=(quantity, SLEEP)))
    assert before.x.key == quantity and before.sample.n == 90
    assert before.verdict != "not_evaluable" and before.effect.coefficient is not None
    habits.update_habit(session, habit.id,
                        config(health_area["id"], name="Переименовано",
                               tracking_mode="binary_quantity", quantity_unit="м", weight=3),
                        effective_date=MON + timedelta(days=45))
    after = hypothesis(single(session, keys=(quantity, SLEEP)))
    assert after.verdict == "not_evaluable"
    assert after.relationship.reason == "mixed_quantity_units"
    assert after.effect.coefficient is None


# --- families ------------------------------------------------------------------------

def test_lag_family_is_corrected_as_one_family(session):
    seed_shifted(session, MON - timedelta(days=8), 98, shift=2)
    result = get_guardrails(session, MON, MON + timedelta(days=89),
                            tuple((COMPUTER, SLEEP, lag) for lag in range(8)),
                            mode="lag_scan", today=TODAY)
    assert result.family.mode == "lag_scan"
    assert result.family.requested_size == result.family.tested_size == 8
    assert result.family.multiple_comparisons_checked is True
    assert [item.lag for item in result.hypotheses if item.verdict == "pass"] == [2]
    blocked = [item for item in result.hypotheses if item.verdict == "blocked"]
    assert len(blocked) == 7
    assert all("false_discovery_risk" in [reason.code for reason in item.blocking_reasons]
               for item in blocked)
    assert result.family.verdicts == {"pass": 1, "pass_with_warnings": 0, "blocked": 7,
                                     "not_evaluable": 0}


def test_matrix_family_matches_the_relationship_matrix_contract(session):
    seed_states(session, MON, MON + timedelta(days=89))
    keys = (SLEEP, COMPUTER, "state.mood", "state.alcohol")
    hypotheses = tuple((first, second, 0) for index, first in enumerate(sorted(keys))
                       for second in sorted(keys)[index + 1:])
    result = get_guardrails(session, MON, MON + timedelta(days=89), hypotheses, mode="matrix",
                            today=TODAY)
    assert result.family.mode == "matrix"
    assert result.family.requested_size == len(hypotheses) == 6
    assert {(item.x.key, item.y.key) for item in result.hypotheses} == {
        (first, second) for index, first in enumerate(sorted(keys))
        for second in sorted(keys)[index + 1:]}
    assert [item.index for item in result.hypotheses] == list(range(6))


def test_family_source_range_unions_every_lag_window(session):
    seed_states(session, MON - timedelta(days=8), MON + timedelta(days=96))
    positive = family_source_range(MON, MON + timedelta(days=89),
                                  tuple((SLEEP, COMPUTER, lag) for lag in range(8)))
    assert positive == Period(MON - timedelta(days=7), MON + timedelta(days=89))
    negative = family_source_range(MON, MON + timedelta(days=89),
                                  tuple((SLEEP, COMPUTER, lag) for lag in (-7, 0)))
    assert negative == Period(MON, MON + timedelta(days=96))
    assert family_source_range(MON, MON + timedelta(days=89), ((SLEEP, COMPUTER, 0),)) == \
        Period(MON, MON + timedelta(days=89))


def test_mixed_grain_hypothesis_only_needs_the_target_period():
    assert family_source_range(MON, MON + timedelta(days=89),
                               ((SLEEP, "weekly.state.mood.mean", 3),)) == \
        Period(MON, MON + timedelta(days=89))


def test_invalid_request_fails_before_any_dataset_is_loaded(session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid guardrail request must not load data")
    monkeypatch.setattr(analytics, "get_dataset", forbidden)
    with pytest.raises(ValueError):
        family_source_range(MON, MON + timedelta(days=9), (("unknown.key", SLEEP, 0),))
    with pytest.raises(ValueError):
        family_source_range(MON, MON + timedelta(days=9), ())


# --- read-only and SQL bound ---------------------------------------------------------

def test_guardrails_endpoint_is_read_only_and_serializes_without_nan(database, session, client, app):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=96))
    app.state.clock = FrozenClock(TODAY)
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    params = {"start": str(MON), "end": str(MON + timedelta(days=89)),
              "x": COMPUTER, "y": SLEEP, "lags": [0, 1, 2, 3]}
    response = client.get("/api/analytics/guardrails", params=params)
    assert response.status_code == 200, response.text
    parsed = GuardrailAnalyticsRead.model_validate_json(response.text).root
    assert parsed.contract_version == "7F.1"
    assert parsed.guardrail_policy_version == parsed.policy.version == POLICY.version
    assert parsed.policy.minimum_n == POLICY.minimum_n
    assert parsed.family.mode == "lag_scan" and len(parsed.hypotheses) == 4
    assert parsed.today == app.state.clock.today()
    assert "NaN" not in response.text and "Infinity" not in response.text
    json.dumps(response.json(), allow_nan=False)
    assert client.get("/api/analytics/guardrails", params=params).text == response.text
    assert client.post("/api/analytics/guardrails", params=params).status_code == 405
    assert "/api/analytics/guardrails" in client.get("/api/openapi.json").json()["paths"]
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before


@pytest.mark.parametrize("selection,expected", [
    ({"x": SLEEP, "y": COMPUTER}, "single"),
    ({"x": SLEEP, "y": COMPUTER, "lag": 3}, "single"),
    ({"x": SLEEP, "y": COMPUTER, "lags": [0, 1, 2, 3]}, "lag_scan"),
    ({"x": SLEEP, "y": COMPUTER, "lag_start": -2, "lag_end": 2}, "lag_scan"),
    ({"variables": [SLEEP, COMPUTER, "state.mood"]}, "matrix"),
])
def test_family_mode_and_dataset_build_are_constant(database, session, health_area, monkeypatch,
                                                   selection, expected):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=96))
    for _ in range(10):
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
            result = get_guardrails(reading, MON, MON + timedelta(days=89),
                                   _hypotheses(selection), mode=expected, today=TODAY)
            assert result.family.mode == expected
            assert len(result.hypotheses) >= 1
            # One dataset build for the whole family: no per-hypothesis, per-segment
            # or per-weekday SQL.
            assert len(loads) == len(builds) == 1 and loads == builds
            assert loads[0] == (result.source_range.start, result.source_range.end)
            assert len(statements) == 4
            assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
            assert pending in reading.new and pending.id is None
            assert dirty in reading.dirty and not reading.deleted
            statements.clear()
            GuardrailAnalyticsRead(result).model_dump_json()
            assert statements == []
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before


def _hypotheses(selection):
    if "variables" in selection:
        keys = selection["variables"]
        return tuple((first, second, 0) for index, first in enumerate(sorted(keys))
                     for second in sorted(keys)[index + 1:])
    lags = selection.get("lags")
    if lags is not None:
        return tuple((selection["x"], selection["y"], lag) for lag in lags)
    if "lag_start" in selection:
        return tuple((selection["x"], selection["y"], lag)
                     for lag in range(selection["lag_start"], selection["lag_end"] + 1))
    return ((selection["x"], selection["y"], selection.get("lag", 0)),)


# --- weekly grain --------------------------------------------------------------------

def test_weekly_family_uses_the_same_pipeline(session):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=96))
    result = get_guardrails(session, MON, MON + timedelta(days=89), ((WEEKLY + (0,)),),
                            mode="single", today=TODAY)
    item = result.hypotheses[0]
    assert item.grain is not None and item.lag_unit == "week"
    assert item.sample.n >= 10
    assert item.weekday.status == "not_applicable"
    assert item.verdict in ("pass", "pass_with_warnings", "blocked")
    assert any(check.name == "multiple_comparisons" for check in item.checks)


# --- integration with the Stage 7E confidence engine ---------------------------------

def test_confidence_reports_the_guardrail_summary_and_keeps_it_separate(session):
    # Both variables rise on Fridays only: the raw association is a weekday rhythm.
    values = [StateValues(sleep_minutes=600 + 60 * (offset % 7 == 4),
                          computer_minutes=300 + 60 * (offset % 7 == 4))
              for offset in range(90)]
    seed_states(session, MON, MON + timedelta(days=89), values)
    result = get_confidence(session, MON, MON + timedelta(days=89), SLEEP, COMPUTER, today=TODAY)
    assert result.relationship.coefficient == pytest.approx(1.0)
    assert result.guardrail is not None
    assert result.guardrail.status == "blocked"
    assert result.guardrail.blocking_reasons == ("weekday_explained",)
    assert result.guardrail.confidence_capped is True
    # Guardrails and confidence stay separate fields: the association is blocked
    # evidence, yet its history-maturity is still reported.
    assert result.confidence == "stable"
    assert result.evidence.stability.direction_consistent is True
    assert result.status == "evaluated"


def test_blocked_evidence_can_never_be_well_supported(session):
    x, z = lcg(90), lcg(90, seed=13)
    values = [StateValues(sleep_minutes=a,
                          computer_minutes=min(1440, max(0, int(0.05 * a + 0.55 * w))))
              for a, w in zip(x, z)]
    seed_states(session, MON, MON + timedelta(days=89), values)
    result = get_confidence(session, MON, MON + timedelta(days=89), SLEEP, COMPUTER, today=TODAY)
    assert result.guardrail is not None and result.guardrail.status == "blocked"
    assert "below_effect_threshold" in result.guardrail.blocking_reasons
    assert result.guardrail.confidence_capped is True
    assert result.confidence == "stable"           # mature history, inadmissible evidence
    assert result.relationship.strength in ("weak", "moderate")


def test_not_evaluable_guardrail_leaves_confidence_without_a_level(session):
    seed_states(session, MON, MON + timedelta(days=29))
    result = get_confidence(session, MON, MON + timedelta(days=29), SLEEP,
                            "weekly.state.mood.mean", today=TODAY)
    assert result.status == "not_evaluable" and result.confidence is None
    assert result.reason == "grain_mismatch"
    assert result.guardrail is not None and result.guardrail.status == "not_evaluable"
    assert result.guardrail.confidence_capped is False


def test_confidence_endpoint_exposes_the_guardrail_summary(database, session, client, app):
    seed_states(session, MON - timedelta(days=7), MON + timedelta(days=96))
    app.state.clock = FrozenClock(TODAY)
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    response = client.get("/api/analytics/confidence", params={
        "start": str(MON), "end": str(MON + timedelta(days=89)), "x": SLEEP, "y": COMPUTER,
        "lag": 3})
    assert response.status_code == 200, response.text
    parsed = ConfidenceAnalyticsRead.model_validate_json(response.text).root
    assert parsed.guardrail is not None
    assert parsed.guardrail.status in ("pass", "pass_with_warnings", "blocked", "not_evaluable")
    assert parsed.guardrail.policy_version == POLICY.version
    assert parsed.guardrail.family_size == 1          # one hypothesis, no family correction
    assert parsed.confidence in ("preliminary", "stable", "well_supported")
    json.dumps(response.json(), allow_nan=False)
    with database.engine.connect() as connection:
        assert list(connection.connection.driver_connection.iterdump()) == before


def test_confidence_and_guardrails_share_one_dataset_build(database, session, monkeypatch):
    seed_states(session, MON, MON + timedelta(days=89))
    loads, statements = [], []
    original = analytics.get_dataset

    def counted(*args, **kwargs):
        loads.append((args[1], args[2]))
        return original(*args, **kwargs)

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    monkeypatch.setattr(analytics, "get_dataset", counted)
    event.listen(database.engine, "before_cursor_execute", record)
    try:
        with Session(database.engine) as reading:
            statements.clear()
            analytics.get_dataset(reading, MON, MON + timedelta(days=89), today=TODAY)
            baseline = len(statements)
            loads.clear()
            statements.clear()
            result = get_confidence(reading, MON, MON + timedelta(days=89), SLEEP, COMPUTER,
                                    today=TODAY)
        assert result.guardrail is not None
        assert len(loads) == 1                        # guardrails reuse the same dataset
        assert 0 < baseline <= 4
        assert len(statements) == baseline            # guardrails add no SQL at all
    finally:
        event.remove(database.engine, "before_cursor_execute", record)


# --- validation ----------------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {"x": "", "y": COMPUTER}, {"x": COMPUTER}, {"y": SLEEP},
    {"x": "unknown", "y": COMPUTER}, {"x": "habit.999.daily.quantity", "y": COMPUTER},
    {"x": COMPUTER, "y": SLEEP, "lag": 8}, {"x": COMPUTER, "y": SLEEP, "lag": -8},
    {"x": COMPUTER, "y": SLEEP, "lags": [1], "lag": 1},
    {"x": COMPUTER, "y": SLEEP, "lag_start": 3, "lag_end": -1},
    {"x": COMPUTER, "y": SLEEP, "lag_start": 3},
    {"variables": [SLEEP]},
    {"variables": [SLEEP, COMPUTER], "x": SLEEP, "y": COMPUTER},
    {"variables": [SLEEP, COMPUTER], "lag": 1},
    {"start": "bad"}, {"start": "2000-01-01"},
    {"start": str(MON + timedelta(days=7))},
])
def test_guardrail_validation_is_bounded_and_localized(client, params):
    query = {"start": str(MON), "end": str(MON + timedelta(days=6)), "x": SLEEP, "y": COMPUTER,
             **params}
    response = client.get("/api/analytics/guardrails", params=query)
    assert response.status_code == 422, response.text
    assert any("А" <= letter <= "я" for letter in response.json()["error"]["message"])


@pytest.mark.parametrize("missing", ["start", "end"])
def test_required_parameters(client, missing):
    params = {"start": str(MON), "end": str(MON + timedelta(days=6)), "x": SLEEP, "y": COMPUTER}
    del params[missing]
    assert client.get("/api/analytics/guardrails", params=params).status_code == 422


def test_the_full_lag_range_is_the_largest_possible_family(client):
    response = client.get("/api/analytics/guardrails", params={
        "start": str(MON), "end": str(MON + timedelta(days=6)), "x": SLEEP, "y": COMPUTER,
        "lags": list(range(-7, 8))})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["family"]["mode"] == "lag_scan"
    assert data["family"]["requested_size"] == 15
    assert data["lags"] == list(range(-7, 8))


def test_too_many_matrix_variables_is_rejected(client):
    response = client.get("/api/analytics/guardrails", params={
        "start": str(MON), "end": str(MON + timedelta(days=6)),
        "variables": [f"habit.{index}.daily.quantity" for index in range(30)]})
    assert response.status_code == 422, response.text
