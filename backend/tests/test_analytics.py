"""Canonical analytics contract: missingness, history, scopes and read purity."""

from datetime import UTC, date, datetime, timedelta
import json

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Area
from app.domain.analytics.builder import MAX_RANGE_DAYS
from app.domain.analytics.types import Availability as A, Grain, Value, VariableType
from app.domain.daily_state import StateValues
from app.domain.schedule import Schedule
from app.schemas.analytics import AnalyticsDatasetRead
from app.services import daily_state, habits
from app.services.analytics import get_dataset
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make, save


def dataset(session, start=MON, end=None, today=None):
    return get_dataset(session, start, end or start, today=today or MON + timedelta(days=30))


def state(session, offset, **values):
    daily_state.save_state(session, MON + timedelta(days=offset), StateValues(**values),
                           today=MON + timedelta(days=30))


def feature(row, key, value, availability=A.PRESENT):
    assert row.values[key] == Value(value, availability)
    if value is not None:
        assert type(row.values[key].value) is type(value)


def test_absent_state_empty_fields_zero_false_and_text(session):
    state(session, 1, computer_overuse=False, computer_minutes=180,
          gaming=False, gaming_minutes=0, note="Только источник")
    data = dataset(session, end=MON + timedelta(days=2))
    feature(data.daily[0], "state.alcohol", None, A.SOURCE_MISSING)
    feature(data.daily[1], "state.alcohol", None, A.FIELD_MISSING)
    for name in ("mood", "energy", "wellbeing"):
        feature(data.daily[1], f"state.{name}", None, A.FIELD_MISSING)
    feature(data.daily[1], "state.computer_overuse", False)
    feature(data.daily[1], "state.computer_minutes", 180)
    feature(data.daily[1], "state.gaming_minutes", 0)
    assert data.daily[1].state_source.note == "Только источник"
    assert not any("note" in v.key or "alcohol_detail" in v.key for v in data.variables)


@pytest.mark.parametrize("gaming,minutes", [(True, 90), (True, None), (False, None), (False, 0), (None, None)])
def test_gaming_observations_stay_separate(session, gaming, minutes):
    state(session, 0, gaming=gaming, gaming_minutes=minutes, note="Запись")
    row = dataset(session).daily[0]
    feature(row, "state.gaming", gaming, A.FIELD_MISSING if gaming is None else A.PRESENT)
    feature(row, "state.gaming_minutes", minutes, A.FIELD_MISSING if minutes is None else A.PRESENT)


@pytest.mark.parametrize("alcohol", [True, False, None])
def test_alcohol_three_states(session, alcohol):
    state(session, 0, alcohol=alcohol, alcohol_detail="Вино" if alcohol else None, note="Запись")
    row = dataset(session).daily[0]
    feature(row, "state.alcohol", alcohol, A.FIELD_MISSING if alcohol is None else A.PRESENT)
    assert row.state_source.alcohol_detail == ("Вино" if alcohol else None)


@pytest.mark.parametrize("status,minutes", [("underslept", 600), ("normal", None), (None, 0), (None, 480)])
def test_sleep_independent(session, status, minutes):
    state(session, 0, sleep_status=status, sleep_minutes=minutes)
    row = dataset(session).daily[0]
    feature(row, "state.sleep_status", status, A.FIELD_MISSING if status is None else A.PRESENT)
    feature(row, "state.sleep_minutes", minutes, A.FIELD_MISSING if minutes is None else A.PRESENT)


def test_weekly_only_observed_values_and_counts(session):
    state(session, 0, mood=1, alcohol=True, gaming=True, gaming_minutes=120, sleep_status="normal")
    state(session, 1, mood=5, alcohol=False, gaming=False, gaming_minutes=0)
    state(session, 2, note="Нет оценок")
    data = dataset(session, end=MON + timedelta(days=6))
    row = data.weekly[0]
    feature(row, "weekly.state.mood.mean", 3.0)
    feature(row, "weekly.state.mood.observed_count", 2)
    feature(row, "weekly.state.energy.mean", None, A.NO_OBSERVATIONS)
    feature(row, "weekly.state.energy.observed_count", 0)
    feature(row, "weekly.state.alcohol.true_count", 1)
    feature(row, "weekly.state.alcohol.false_count", 1)
    feature(row, "weekly.state.alcohol.observed_count", 2)
    feature(row, "weekly.state.gaming_minutes.mean", 60.0)
    feature(row, "weekly.state.sleep_status.observed_count", 1)


def test_habit_absence_skip_missed_quantity_and_no_obligations(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=1),
             tracking_mode="binary_quantity", quantity_unit="км", quantity_allows_decimal=True)
    save(session, h.id, 2, "skipped", skip_reason="Отдых")
    save(session, h.id, 3, "missed", quantity_value=0)
    save(session, h.id, 4, quantity_value="6.4")
    data = dataset(session, end=MON + timedelta(days=4))
    key = f"habit.{h.id}.daily"
    feature(data.daily[0], f"{key}.status", None, A.NOT_APPLICABLE)
    feature(data.daily[1], f"{key}.status", None, A.SOURCE_MISSING)
    feature(data.daily[2], f"{key}.status", "skipped")
    feature(data.daily[2], f"{key}.quantity", None, A.FIELD_MISSING)
    feature(data.daily[3], f"{key}.status", "missed")
    feature(data.daily[3], f"{key}.quantity", 0.0)
    feature(data.daily[4], f"{key}.quantity", 6.4)
    feature(data.daily[0], "daily.score", None, A.NO_OBLIGATIONS)
    feature(data.daily[1], "daily.score", 0.0)
    feature(data.daily[4], "daily.score", 100.0)
    assert data.daily[4].habits[h.id].entry.quantity_micro == 6400000
    assert data.daily[2].habits[h.id].entry.skip_reason == "Отдых"


def test_historical_rename_weight_units_and_schedule(session, health_area):
    area = health_area["id"]
    h = make(session, area, weight=1, tracking_mode="binary_quantity", quantity_unit="км")
    save(session, h.id, 0, quantity_value=3)
    habits.update_habit(session, h.id, config(area, name="Новое имя", weight=3,
        tracking_mode="binary_quantity", quantity_unit="м", schedule=Schedule.create("weekdays", weekdays=[2, 4])),
        effective_date=MON + timedelta(days=2))
    save(session, h.id, 3, quantity_value=500)
    habits.update_habit(session, h.id, config(area, name="Третье имя", weight=2,
        schedule=Schedule.create("times_per_week", times_per_week=5)), effective_date=MON + timedelta(days=4))
    data = dataset(session, end=MON + timedelta(days=13))
    key = f"habit.{h.id}.daily"
    assert data.daily[0].habits[h.id].configuration.configuration.name == "Чтение"
    assert data.daily[0].habits[h.id].configuration.configuration.quantity_unit == "км"
    assert data.daily[3].habits[h.id].configuration.configuration.quantity_unit == "м"
    feature(data.daily[0], f"{key}.weight", 1)
    feature(data.daily[2], f"{key}.weight", 3)
    feature(data.daily[4], f"{key}.weight", 2)
    feature(data.daily[4], f"{key}.quantity", None, A.NOT_APPLICABLE)
    feature(data.daily[3], f"{key}.status", "done")  # off-preferred date is applicable
    feature(data.daily[3], f"{key}.required_weight", None, A.NOT_APPLICABLE)
    feature(data.weekly[0], f"habit.{h.id}.weekly.quota", 2)
    feature(data.weekly[0], f"habit.{h.id}.weekly.required_weight", 8)  # two daily + 2 * 3
    feature(data.weekly[1], f"habit.{h.id}.weekly.quota", 5)
    assert data.weekly[0].habits[0].weekly_effective_from == MON + timedelta(days=2)
    assert data.weekly[0].habits[0].preferred_weekdays == (2, 4)
    assert len({v.key for v in data.variables}) == len(data.variables)
    assert all(set(r.values) == set(data.daily[0].values) for r in data.daily)


def test_same_day_config_collapse_and_stable_registry(session, health_area):
    area = health_area["id"]
    h = make(session, area)
    before = dataset(session)
    habits.update_habit(session, h.id, config(area, name="Другое имя", weight=3), effective_date=MON)
    after = dataset(session)
    assert before.variables == after.variables
    feature(before.daily[0], "daily.required_weight", 1)
    feature(after.daily[0], "daily.required_weight", 3)
    assert after.daily[0].habits[h.id].configuration.configuration.name == "Другое имя"


def test_archive_week_preserves_quota_and_legacy_records(session, health_area):
    h = make(session, health_area["id"], schedule=Schedule.create("times_per_week", times_per_week=4))
    save(session, h.id, 0)
    h.is_archived = True
    h.archived_at = datetime(2026, 9, 9).astimezone(UTC)
    session.commit()
    result = dataset(session, end=MON + timedelta(days=13))
    feature(result.weekly[0], f"habit.{h.id}.weekly.quota", 4)
    feature(result.weekly[1], f"habit.{h.id}.weekly.quota", None, A.NOT_APPLICABLE)
    h.archived_at = None
    session.commit()
    legacy = dataset(session)
    feature(legacy.daily[0], f"habit.{h.id}.daily.status", None, A.NOT_APPLICABLE)
    assert legacy.daily[0].habits[h.id].entry.status == "done"


def test_inactive_unrelated_identity_excluded_but_future_week_identity_included(session, health_area):
    a = make(session, health_area["id"], start=MON - timedelta(days=30))
    a.is_archived = True
    a.archived_at = datetime(2026, 8, 20).astimezone(UTC)
    session.commit()
    b = make(session, health_area["id"], start=MON + timedelta(days=4))
    make(session, health_area["id"], start=MON + timedelta(days=7))
    result = dataset(session)
    assert {v.habit_id for v in result.variables if v.habit_id is not None} == {b.id}
    feature(result.daily[0], f"habit.{b.id}.daily.status", None, A.NOT_APPLICABLE)
    feature(result.weekly[0], f"habit.{b.id}.weekly.required_weight", 3)


def test_archive_before_first_effective_config_has_no_applicable_dates(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=4))
    h.is_archived = True
    h.archived_at = datetime(2026, 9, 9).astimezone(UTC)
    session.commit()
    result = dataset(session, end=MON + timedelta(days=6))
    assert not any(v.habit_id is not None for v in result.variables)


def test_weekly_to_daily_and_quota_cap_match_stage4(session, health_area):
    area = health_area["id"]
    h = make(session, area, weight=2, schedule=Schedule.create("times_per_week", times_per_week=2))
    for offset in range(4):
        save(session, h.id, offset)
    habits.update_habit(session, h.id, config(area, weight=3), effective_date=MON + timedelta(days=4))
    save(session, h.id, 4)
    row = dataset(session, end=MON + timedelta(days=6)).weekly[0]
    feature(row, f"habit.{h.id}.weekly.completed_count", 4)
    feature(row, f"habit.{h.id}.weekly.completed_weight", 7)  # capped weekly 4 + daily 3
    feature(row, f"habit.{h.id}.weekly.required_weight", 13)
    feature(row, f"habit.{h.id}.weekly.daily_completed_count", 1)


def test_partial_request_has_full_progress_but_only_requested_state(session, health_area):
    h = make(session, health_area["id"], schedule=Schedule.create("weekdays", weekdays=[0, 2, 4]))
    save(session, h.id, 0)
    state(session, 0, mood=1)
    state(session, 2, mood=5)
    data = dataset(session, start=MON + timedelta(days=2), end=MON + timedelta(days=4))
    row = data.weekly[0]
    assert (row.requested_days, row.elapsed_requested_days, row.calendar_elapsed_days) == (3, 3, 7)
    assert row.partial_requested_week and not row.unfinished_week
    assert row.progress_scope == "calendar_week" and row.state_scope == "requested_elapsed_dates"
    assert row.week_start == MON and row.week_end == MON + timedelta(days=6)
    feature(row, f"habit.{h.id}.weekly.completed_count", 1)  # Monday outside requested range
    feature(row, "weekly.state.mood.mean", 5.0)
    feature(row, "weekly.state.mood.observed_count", 1)


def test_first_tracked_partial_week_keeps_full_quota(session, health_area):
    h = make(session, health_area["id"], start=MON + timedelta(days=4),
             schedule=Schedule.create("times_per_week", times_per_week=5))
    row = dataset(session, end=MON + timedelta(days=6)).weekly[0]
    assert row.active_habit_days == 3
    assert not row.partial_requested_week
    feature(row, f"habit.{h.id}.weekly.quota", 5)


def test_today_future_and_planned_skip(session, health_area):
    h = make(session, health_area["id"])
    save(session, h.id, 3, "skipped", skip_reason="План")
    data = dataset(session, end=MON + timedelta(days=13), today=MON + timedelta(days=2))
    feature(data.daily[2], "daily.date_relation", "today")
    feature(data.daily[2], "daily.score", 0.0)
    for row in data.daily[3:]:
        feature(row, "daily.score", None, A.FUTURE)
        feature(row, "daily.completed_weight", None, A.FUTURE)
        feature(row, "state.alcohol", None, A.FUTURE)
        feature(row, f"habit.{h.id}.daily.status", None, A.FUTURE)
        feature(row, "daily.required_weight", 1)
    assert data.daily[3].habits[h.id].entry.status == "skipped"
    assert data.weekly[0].elapsed_requested_days == 3
    assert data.weekly[0].unfinished_week
    feature(data.weekly[1], "weekly.score", None, A.FUTURE)
    feature(data.weekly[1], "weekly.completed_weight", None, A.FUTURE)
    feature(data.weekly[1], "weekly.state.mood.observed_count", None, A.FUTURE)
    feature(data.weekly[1], f"habit.{h.id}.weekly.completed_weight", None, A.FUTURE)


def test_future_requested_slice_of_current_week_has_no_observed_counts(session):
    data = dataset(session, start=MON + timedelta(days=3), end=MON + timedelta(days=4), today=MON)
    row = data.weekly[0]
    assert row.calendar_elapsed_days == 1 and row.elapsed_requested_days == 0
    feature(row, "weekly.state.alcohol.false_count", None, A.FUTURE)
    feature(row, "weekly.score", None, A.NO_OBLIGATIONS)  # full calendar week scope


def test_archives_and_new_habits_do_not_change_columns_within_dataset(session, health_area):
    a = make(session, health_area["id"])
    save(session, a.id, 3)
    a.is_archived = True
    a.archived_at = datetime(2026, 9, 9).astimezone(UTC)
    session.commit()
    b = make(session, health_area["id"], start=MON + timedelta(days=3))
    data = dataset(session, end=MON + timedelta(days=4))
    assert {v.habit_id for v in data.variables if v.habit_id is not None} == {a.id, b.id}
    feature(data.daily[0], f"habit.{b.id}.daily.status", None, A.NOT_APPLICABLE)
    feature(data.daily[3], f"habit.{a.id}.daily.status", None, A.NOT_APPLICABLE)
    assert data.daily[3].habits[a.id].entry.status == "done"  # source preserved outside obligations
    assert not data.daily[3].habits[a.id].applicable
    assert all(set(r.values) == set(data.daily[0].values) for r in data.daily)


@pytest.mark.parametrize("start,end,count,weeks", [
    (date(2024, 2, 29), date(2024, 2, 29), 1, 1),
    (date(2024, 2, 1), date(2024, 2, 29), 29, 5),
    (date(2024, 1, 1), date(2024, 12, 31), 366, 53),
    (date(2025, 1, 1), date(2025, 12, 31), 365, 53),
    (date(2020, 12, 31), date(2021, 1, 4), 5, 2),
    (date(2026, 9, 13), date(2026, 9, 14), 2, 2),
    (date.min, date.min, 1, 1),
    (date.max, date.max, 1, 1),
])
def test_ranges_and_calendar_edges(session, start, end, count, weeks):
    data = dataset(session, start, end)
    assert len(data.daily) == count and len(data.weekly) == weeks
    assert data.daily[0].date == start and data.daily[-1].date == end
    assert all(w.week_start.weekday() == 0 for w in data.weekly)
    assert sum(w.requested_days for w in data.weekly) == count
    for row in data.daily:
        feature(row, "daily.weekday", str(row.date.weekday()))
        feature(row, "daily.iso_year", row.date.isocalendar().year)
        feature(row, "daily.iso_week", str(row.date.isocalendar().week))


def test_iso_year_is_not_calendar_year(session):
    row = dataset(session, date(2021, 1, 1)).daily[0]
    feature(row, "daily.year", 2021)
    feature(row, "daily.iso_year", 2020)
    feature(row, "daily.iso_week", "53")


def test_registry_complete_deterministic_and_typed(session, health_area):
    make(session, health_area["id"])
    state(session, 0, mood=2, alcohol=False)
    data = dataset(session)
    assert data.variables == dataset(session).variables
    assert {v.type for v in data.variables} == set(VariableType)
    for grain, rows in ((Grain.DAILY, data.daily), (Grain.WEEKLY, data.weekly)):
        definitions = {v.key: v for v in data.variables if v.grain == grain}
        for row in rows:
            assert set(row.values) == set(definitions)
            for key, cell in row.values.items():
                variable = definitions[key]
                assert variable.source and variable.missing_semantics and variable.label
                assert any("А" <= c <= "я" for c in variable.label)
                if cell.value is not None:
                    allowed = {VariableType.NUMERIC: (int, float), VariableType.ORDINAL: (int,),
                               VariableType.BOOLEAN: (bool,), VariableType.CATEGORICAL: (str,)}[variable.type]
                    assert type(cell.value) in allowed
                    if variable.categories:
                        assert cell.value in variable.categories


def test_http_serialization_and_clock(client, app, session, health_area):
    app.state.clock = FrozenClock(MON)
    make(session, health_area["id"])
    state(session, 0, mood=1, computer_overuse=False, computer_minutes=0, sleep_status="normal")
    response = client.get("/api/analytics/dataset", params={"start": MON.isoformat(), "end": MON.isoformat()})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["today"] == MON.isoformat()
    values = data["daily"][0]["values"]
    assert values["state.computer_overuse"]["value"] is False
    assert values["state.computer_minutes"]["value"] == 0
    assert type(values["state.mood"]["value"]) is int
    assert values["state.sleep_status"]["value"] == "normal"
    assert values["state.alcohol"]["value"] is None
    assert "NaN" not in response.text and "Infinity" not in response.text
    assert AnalyticsDatasetRead.model_validate_json(response.text).root == dataset(session, today=MON)


@pytest.mark.parametrize("params", [
    {}, {"start": "bad", "end": "2026-09-07"},
    {"start": "2026-09-08", "end": "2026-09-07"},
    {"start": "2000-01-01", "end": "2026-09-07"},
])
def test_endpoint_rejects_invalid_range(client, params):
    response = client.get("/api/analytics/dataset", params=params)
    assert response.status_code == 422
    assert "error" in response.json()


def test_internal_limit_before_loading(session):
    with pytest.raises(ValueError):
        dataset(session, MON, MON + timedelta(days=MAX_RANGE_DAYS))
    with pytest.raises(ValueError):
        dataset(session, MON, MON - timedelta(days=1))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_rejected(value):
    with pytest.raises(ValueError):
        Value(value)


def test_null_requires_reason():
    with pytest.raises(ValueError):
        Value(None)
    with pytest.raises(ValueError):
        Value(False, A.SOURCE_MISSING)


def test_bounded_queries_read_only_and_no_autoflush(database, session, health_area):
    for _ in range(12):
        h = make(session, health_area["id"], start=date(2024, 1, 1))
        save(session, h.id, 0)
    state(session, 0, mood=4)
    with database.engine.connect() as connection:
        before = list(connection.connection.driver_connection.iterdump())
    statements = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(database.engine, "before_cursor_execute", record)
    try:
        for start, end in ((MON, MON), (date(2024, 1, 1), date(2024, 12, 31))):
            statements.clear()
            with Session(database.engine, autoflush=True) as reading:
                pending = Area(name="Не сохранять", color="#ffffff")
                reading.add(pending)
                result = dataset(reading, start, end)
                assert pending in reading.new and pending.id is None
                assert not reading.dirty and not reading.deleted
                assert len(statements) == 4  # habits, versions + area join, entries, states
                assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
                statements.clear()
                json.loads(AnalyticsDatasetRead(result).model_dump_json())
                assert not statements
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    with database.engine.connect() as connection:
        after = list(connection.connection.driver_connection.iterdump())
    assert after == before
