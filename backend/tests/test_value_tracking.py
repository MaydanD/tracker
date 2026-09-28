"""End-to-end value semantics, historical metadata, evaluation and restoration."""
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from app.domain.progress import current_streak, day_progress, week_progress
from app.services import analytics, backup, canonical, progress
from tests.helpers import alembic_config, habit_payload, run_migrations


def create_value(client, area_id, *, kind="ordinal_4", direction="positive", weight=1, importance="normal"):
    response = client.post("/api/habits", json={
        **habit_payload(area_id=area_id, weight=weight),
        "value_type": kind, "value_labels": ["нет", "да"] if kind == "binary" else ["ноль", "мало", "норм", "много"],
        "direction": direction, "importance": importance,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize("kind,values", [("binary", [0, 1]), ("ordinal_4", [0, 1, 2, 3])])
def test_valid_values_and_comments(client, app, health_area, kind, values):
    habit_id = create_value(client, health_area["id"], kind=kind)
    today = app.state.clock.today()
    endpoint = f"/api/habits/{habit_id}/entries/{today}"
    for value in values:
        result = client.put(endpoint, json={"status": "done", "value": value, "note": "comment"})
        assert result.status_code == 200, result.text
        assert result.json()["value"] == value
        assert result.json()["note"] == "comment"
        day = client.get(f"/api/progress/days/{today}").json()["day"]
        assert day["filled_count"] == 1
        assert day["completion"] == 100


@pytest.mark.parametrize("value", [None, -1, 4, 0.5, True, "1"])
def test_invalid_values_rejected_without_entry(client, app, health_area, value):
    habit_id = create_value(client, health_area["id"])
    result = client.put(f"/api/habits/{habit_id}/entries/{app.state.clock.today()}",
                        json={"status": "done", "value": value})
    assert result.status_code == 422, result.text
    assert client.get(f"/api/days/{app.state.clock.today()}").json()["items"][0]["entry"] is None


def test_binary_two_is_rejected(client, app, health_area):
    habit_id = create_value(client, health_area["id"], kind="binary")
    assert client.put(f"/api/habits/{habit_id}/entries/{app.state.clock.today()}",
                      json={"status": "done", "value": 2}).status_code == 422


@pytest.mark.parametrize("kind,direction,value,expected", [
    ("ordinal_4", "positive", 0, 0), ("ordinal_4", "positive", 1, 1/3),
    ("ordinal_4", "positive", 2, 2/3), ("ordinal_4", "positive", 3, 1),
    ("ordinal_4", "negative", 0, 1), ("ordinal_4", "negative", 1, 2/3),
    ("ordinal_4", "negative", 2, 1/3), ("ordinal_4", "negative", 3, 0),
    ("binary", "positive", 0, 0), ("binary", "positive", 1, 1),
])
def test_direction_score_and_zero_streak(client, app, session, health_area, kind, direction, value, expected):
    habit_id = create_value(client, health_area["id"], kind=kind, direction=direction, weight=3, importance="low")
    today = app.state.clock.today()
    client.put(f"/api/habits/{habit_id}/entries/{today}", json={"status": "done", "value": value})
    history = progress.load_histories(session)[0]
    result = day_progress((history,), today)
    assert result.required_weight == 3
    assert result.score == pytest.approx(expected * 100)
    assert result.filled_count == 1
    assert current_streak(history, today).current_streak == 1
    assert week_progress((history,), today, today).completed_weight == pytest.approx(expected * 3)


def test_neutral_zero_is_completion_and_numeric_analytics(client, app, session, health_area):
    habit_id = create_value(client, health_area["id"], direction="neutral", importance="high")
    today = app.state.clock.today()
    missing = client.get(f"/api/progress/days/{today}").json()["day"]
    assert missing["score"] is None and missing["filled_count"] == 0
    client.put(f"/api/habits/{habit_id}/entries/{today}", json={"status": "done", "value": 0})
    result = client.get(f"/api/progress/days/{today}").json()["day"]
    assert result["score"] is None and result["required_weight"] == 0
    assert result["filled_count"] == 1 and result["completion"] == 100
    dataset = analytics.get_dataset(session, today, today, today=today)
    key = f"habit.{habit_id}.daily.value"
    assert dataset.daily[0].values[key].value == 0
    assert key in {v.key for v in dataset.variables}
    config = dataset.daily[0].habits[habit_id].configuration.configuration
    assert config.importance == "high" and config.direction == "neutral"
    catalogue = client.get("/api/analytics/insights/variables").json()
    assert next(v for v in catalogue["variables"] if v["key"] == key)["supported"]


def test_new_backup_roundtrip_preserves_zero_and_configuration(client, app, health_area):
    habit_id = create_value(client, health_area["id"], direction="negative", importance="high", weight=2)
    today = app.state.clock.today()
    client.put(f"/api/habits/{habit_id}/entries/{today}", json={"status": "done", "value": 0})
    raw = client.get("/api/backup").content
    _, data = backup.validate_archive(raw, app.state.settings)
    version = data.habit_versions[0]
    assert (version.importance, version.weight, version.direction) == ("high", 2, "negative")
    assert version.value_labels == ["ноль", "мало", "норм", "много"]
    assert data.habit_entries[0].value == 0


def test_same_day_legacy_retired_once_and_history_preserved(client, app, session, health_area):
    old = client.post("/api/habits", json=habit_payload(area_id=health_area["id"])).json()
    today = app.state.clock.today()
    client.put(f"/api/habits/{old['id']}/entries/{today}", json={"status": "done"})
    canonical.reconcile_canonical(session, today=today)
    assert len(client.get("/api/habits").json()) == 24
    assert len(client.get("/api/areas").json()) == 4
    assert client.get(f"/api/habits/{old['id']}").json()["is_archived"]
    assert session.execute(text("select count(*) from daily_habit_entries")).scalar() == 1
    assert not canonical.reconcile_canonical(session, today=today).changed


def test_upgrade_intermediate_head_preserves_all_columns(tmp_path):
    from sqlalchemy import create_engine
    url = f"sqlite:///{(tmp_path / 'intermediate.db').as_posix()}"
    run_migrations(url, "5824a510506e")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO areas VALUES (1, 'Area', '#123456', 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, 0)"))
        c.execute(text("INSERT INTO habits VALUES (1, 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, 0)"))
        c.execute(text("INSERT INTO habit_versions (id,habit_id,version_number,effective_from,created_at,name,area_id,weight,tracking_mode,quantity_allows_decimal,schedule_type,value_type,value_labels,direction) VALUES (1,1,1,'2026-09-27',CURRENT_TIMESTAMP,'Old',1,3,'binary',0,'daily','binary','[\"нет\",\"да\"]','neutral')"))
        c.execute(text("INSERT INTO daily_habit_entries (id,habit_id,entry_date,status,created_at,updated_at,value) VALUES (1,1,'2026-09-27','done',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0)"))
        before = c.execute(text("select * from daily_habit_entries")).all()
    run_migrations(url)
    command.check(alembic_config(url))
    with engine.connect() as c:
        assert c.execute(text("select weight,importance from habit_versions")).one() == (3, "normal")
        assert c.execute(text("select * from daily_habit_entries")).all() == before
        assert c.execute(text("pragma foreign_key_check")).all() == []
    engine.dispose()
