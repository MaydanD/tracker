"""Stage 8 insights: HTTP contract, gating, discovery cost and snapshot policy.

The seed below is deliberately readable: mood drives energy exactly, a habit is
completed exactly when mood is high, and a second habit is never completed at
all. That produces, in one dataset, a well-supported relationship, a
representative-lag tie, blocked candidates and genuinely unevaluable ones.
"""

from datetime import date, timedelta
import json

import pytest
from sqlalchemy import event, select

from app.db.models import InsightSnapshot
from app.domain.analytics.builder import dates
from app.domain.analytics.types import Grain
from app.domain.analytics.insights import insight_fingerprint
from app.domain.daily_state import StateValues
from app.schemas.insights import InsightAnalyticsRead, InsightDetailRead
from app.services import analytics, daily, daily_state, habits
from app.services.insights import InsightRequest, get_insights
from tests.helpers import FrozenClock
from tests.test_progress_api import MON, config, make

TODAY = MON + timedelta(days=120)
START = MON
END = MON + timedelta(days=89)
WINDOW = {"start": START.isoformat(), "end": END.isoformat()}
# The widest sweep the policy allows: state budget grows, not the variable budget.
WIDE = {**WINDOW, "max_variables": "8"}


def save(session, habit_id, on, status="done"):
    daily.save_entry(session, habit_id, on, status=status, today=TODAY)


def seed(session, area_id):
    """90 days built to contain every interesting gating outcome at once.

    * mood and energy are identical -> a passing, well-supported relationship;
    * "Тренировка" is done exactly when mood >= 3 -> a strong habit association;
    * "Прогулка" is recorded only on even days -> moderate coverage, a warning;
    * "Чтение" is never completed -> a constant series, genuinely unevaluable;
    * sleep is an unrelated sawtooth -> a weak effect the guardrails block.
    """
    trained = make(session, area_id, name="Тренировка", weight=3)
    walk = make(session, area_id, name="Прогулка", weight=2)
    never = make(session, area_id, name="Чтение", weight=1)
    for index, on in enumerate(dates(START - timedelta(days=7), END)):
        mood = index % 5 + 1
        daily_state.save_state(session, on, StateValues(
            mood=mood, energy=mood, sleep_minutes=600 + index % 30 * 4), today=TODAY)
        if on < START:
            continue
        save(session, trained.id, on, "done" if mood >= 3 else "missed")
        save(session, never.id, on, "missed")
        if index % 2 == 0:
            save(session, walk.id, on, "done" if mood >= 4 else "missed")
    return trained, walk, never


@pytest.fixture()
def seeded(app, session, health_area):
    app.state.clock = FrozenClock(TODAY)
    return seed(session, health_area["id"])


def snapshot_rows(session):
    return list(session.scalars(select(InsightSnapshot).order_by(InsightSnapshot.id)))


# --- feed -----------------------------------------------------------------------------

def test_feed_is_one_aggregated_russian_payload(client, seeded):
    response = client.get("/api/analytics/insights", params=WINDOW)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "discovery" and payload["lags"] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert payload["sort_order"][0] == "guardrail_usability"
    assert payload["insights"], "the seed must produce at least one insight"
    for insight in payload["insights"]:
        assert insight["status"] in ("preliminary", "stable", "well_supported", "warning")
        assert insight["kind"] == "association"
        assert insight["guardrail"]["verdict"] in ("pass", "pass_with_warnings")
        assert insight["in_default_feed"] is True
        assert insight["text"]["full"].startswith(insight["text"]["prefix"])
        # Labels are human-readable: a raw registry label or key must never leak.
        for variable in (insight["x"], insight["y"]):
            assert not variable["label"].startswith("Привычка №")
            assert variable["key"] not in insight["text"]["full"]
        assert insight["caveats"], "every insight carries at least one limitation"
    # The whole payload is JSON-serialisable without NaN or Infinity.
    json.dumps(payload, allow_nan=False)
    InsightAnalyticsRead.model_validate(payload)


def test_feed_summary_counts_match_the_family(client, seeded):
    payload = client.get("/api/analytics/insights", params=WINDOW).json()
    counts = payload["summary"]["counts"]
    assert counts["hypotheses"] == 225 and counts["groups"] == 15
    assert counts["shown"] == counts["in_default_feed"] == len(payload["insights"])
    # ``by_status`` counts display units, so the six statuses partition the groups.
    assert sum(counts["by_status"].values()) == counts["groups"]
    assert counts["admissible_hypotheses"] + counts["blocked_hypotheses"] \
        + counts["unevaluable_hypotheses"] == counts["hypotheses"]
    assert counts["admissible_hypotheses"] >= counts["shown"]
    assert sum(counts["by_blocking_reason"].values()) > 0
    assert payload["summary"]["availability"] == "ok"


def test_role_labels_use_the_current_habit_name(client, seeded):
    payload = client.get("/api/analytics/insights",
                         params={**WIDE, "include_hidden": "true"}).json()
    labels = {variable["label"] for insight in payload["insights"]
              for variable in (insight["x"], insight["y"])}
    assert {"Тренировка", "Прогулка", "Чтение"} <= labels
    assert all(not label.startswith("Привычка №") for label in labels)


def test_a_partially_recorded_habit_becomes_a_warning_not_a_claim(client, seeded):
    payload = client.get("/api/analytics/insights", params=WIDE).json()
    walk = next(item for item in payload["insights"]
                if "Прогулка" in {item["x"]["label"], item["y"]["label"]})
    assert walk["status"] == "warning"
    assert walk["guardrail"]["verdict"] == "pass_with_warnings"
    assert "moderate_coverage" in [reason["code"] for reason in walk["guardrail"]["warnings"]]
    assert walk["confidence"]["level"] == "preliminary"
    assert "moderate_coverage" in [item["code"] for item in walk["caveats"]]
    assert walk["evidence"]["coverage"]["pair_coverage"] < 0.6


def test_blocked_candidates_are_hidden_by_default_and_available_on_request(client, seeded):
    default = client.get("/api/analytics/insights", params=WINDOW).json()
    hidden = client.get("/api/analytics/insights",
                        params={**WINDOW, "include_hidden": "true"}).json()
    assert len(hidden["insights"]) > len(default["insights"])
    assert all(item["in_default_feed"] for item in default["insights"])
    extra = [item for item in hidden["insights"] if not item["in_default_feed"]]
    assert extra, "non-admissible candidates must stay reachable, not silently dropped"
    assert {item["status"] for item in extra} <= {"hidden", "not_evaluable"}
    blocked = [item for item in extra if item["status"] == "hidden"]
    assert blocked and all(item["guardrail"]["blocking_reasons"] for item in blocked)
    assert all(item["text"]["prefix"] == "Результат не прошёл статистические проверки: "
               for item in blocked)


def test_not_evaluable_hypotheses_are_not_presented_as_preliminary(client, seeded):
    payload = client.get("/api/analytics/insights",
                         params={**WIDE, "include_hidden": "true"}).json()
    assert payload["summary"]["counts"]["by_status"]["not_evaluable"] > 0
    unevaluable = [item for item in payload["insights"] if item["status"] == "not_evaluable"]
    assert unevaluable
    for insight in unevaluable:
        assert insight["confidence"]["level"] is None
        assert insight["in_default_feed"] is False
        assert insight["text"]["prefix"] == ""
        assert insight["relationship"]["coefficient"] is None
        codes = [item["code"] for item in insight["caveats"]]
        assert "constant_series" in codes or "insufficient_data" in insight["confidence"]["reason"]
        if "constant_series" in codes:
            assert "не рассчитана" in insight["text"]["full"]
        # A reason-specific statement is shown instead of a direction claim.
        assert insight["text"]["full"].startswith(
            ("Для показателей «", "Связь между показателями «"))


def test_one_group_produces_one_card_with_every_lag_kept_as_alternative(client, seeded):
    payload = client.get("/api/analytics/insights", params=WINDOW).json()
    by_pair = {}
    for insight in payload["insights"]:
        by_pair.setdefault(tuple(sorted((insight["x"]["key"], insight["y"]["key"]))), []).append(insight)
    assert all(len(items) == 1 for items in by_pair.values())
    tied = next(insight for insight in payload["insights"]
                if {insight["x"]["key"], insight["y"]["key"]} == {"state.energy", "state.mood"})
    # Lag 0 ties with lag 5 on verdict, confidence and magnitude; the smaller lag wins.
    assert tied["lag"] == 0
    assert {item["lag"] for item in tied["alternatives"]} == {0, 1, 2, 3, 4, 5, 6, 7}
    assert sum(item["is_representative"] for item in tied["alternatives"]) == 1
    representative = next(item for item in tied["alternatives"] if item["is_representative"])
    assert representative["fingerprint"] == tied["fingerprint"]
    assert len(tied["alternatives"]) == 15  # 8 lags in both temporal directions
    assert any(item["guardrail"] == "pass" for item in tied["alternatives"])
    assert "representative_lag_only" in [item["code"] for item in tied["caveats"]]


def test_representative_is_chosen_only_among_hypotheses_that_passed_the_family(client, seeded):
    payload = client.get("/api/analytics/insights", params=WINDOW).json()
    for insight in payload["insights"]:
        assert insight["guardrail"]["verdict"] in ("pass", "pass_with_warnings")
        assert insight["guardrail"]["family_size"] == 225
        assert insight["guardrail"]["tested_size"] <= 225
        assert insight["guardrail"]["adjusted_q_value"] is not None
        assert insight["guardrail"]["adjusted_q_value"] <= insight["guardrail"]["threshold"]


# --- catalogue ------------------------------------------------------------------------

def test_catalogue_exposes_labels_types_and_areas(client, seeded):
    payload = client.get("/api/analytics/insights/variables").json()
    assert payload["discovery_policy"]["default_variable_budget"] == 6
    assert payload["areas"] and payload["areas"][0]["name"] == "Health"
    variables = {item["key"]: item for item in payload["variables"]}
    assert variables["state.mood"]["label"] == "Настроение"
    assert variables["daily.score"]["group"] == "score"
    assert variables["state.mood"]["group"] == "state"
    assert "habit." not in variables["state.mood"]["label"]
    trained = next(item for item in payload["variables"] if item["label"] == "Тренировка")
    assert trained["group"] == "habit" and trained["supported"] is True
    assert trained["in_default_sweep"] is True
    assert variables["state.sleep_status"]["supported"] is False
    assert next(item for item in payload["variables"]
                if item["label"] == "Чтение")["in_default_sweep"] is False
    json.dumps(payload, allow_nan=False)


# --- detail, charts and evidence ------------------------------------------------------


def detail_of(client, insight, params=WINDOW):
    query = {"start": params["start"], "end": params["end"],
             "mode": "explorer" if "x" in params else "discovery",
             "x": insight["x"]["key"], "y": insight["y"]["key"], "lag": insight["lag"]}
    for name in ("lags", "max_variables"):
        if name in params:
            query[name] = params[name]
    return client.get(f"/api/analytics/insights/{insight['fingerprint']}", params=query)


def pick(payload, predicate):
    return next(item for item in payload["insights"] if predicate(item))


def test_detail_carries_evidence_charts_and_history(client, seeded):
    feed = client.get("/api/analytics/insights", params=WINDOW).json()
    insight = pick(feed, lambda item: {item["x"]["key"], item["y"]["key"]} == {
        "state.energy", "state.mood"})
    response = detail_of(client, insight)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["candidate"]["fingerprint"] == insight["fingerprint"]
    assert detail["history"] == []  # GET must never write history
    assert detail["snapshot_policy"].startswith("Снимок истории создаётся только")
    chart = detail["chart"]
    assert chart["pairs"], "a numeric/ordinal pair must expose its aligned observations"
    assert len(chart["lag_profile"]) == 15
    assert [item["name"] for item in chart["segments"]] == ["early", "middle", "recent"]
    keys = {item["key"] for item in chart["summaries"]}
    assert {"series", "relationship", "lag_profile", "segments"} <= keys
    assert all(item["summary"] and item["title"] for item in chart["summaries"])
    assert len(chart["x"]["points"]) == 90 and chart["x"]["variable"]["label"] == "Энергия"
    json.dumps(detail, allow_nan=False)
    InsightDetailRead.model_validate(detail)


def test_detail_chart_gaps_are_nulls_not_zeros_and_booleans_get_groups(client, seeded):
    feed = client.get("/api/analytics/insights", params=WIDE).json()
    walk = pick(feed, lambda item: "Прогулка" in {item["x"]["label"], item["y"]["label"]})
    detail = detail_of(client, walk, WIDE).json()
    chart = detail["chart"]
    group_evidence = detail["candidate"]["evidence"]["effect"]["group"]
    assert group_evidence is not None and group_evidence["true_count"] > 0
    assert group_evidence["false_count"] > 0
    assert group_evidence["true_median"] is not None or group_evidence["true_mean"] is not None
    booleans = [series for series in (chart["x"], chart["y"])
                if series["variable"]["type"] == "boolean"]
    assert booleans, "the habit side of the pair is boolean"
    series = booleans[0]["points"]
    gaps = [point for point in series if point["missing"]]
    assert gaps and all(point["value"] is None for point in gaps)
    assert all(point["value"] in (0.0, 1.0, None) for point in series)
    assert not chart["pairs"], "boolean pairs must not be drawn as a continuous scatter"
    group = next(item for item in chart["summaries"] if item["key"] == "groups")
    assert "«Да»" in group["summary"] and "«Нет»" in group["summary"]


def test_detail_exposes_the_full_technical_evidence(client, seeded):
    feed = client.get("/api/analytics/insights", params=WINDOW).json()
    insight = pick(feed, lambda item: item["status"] in ("stable", "well_supported"))
    evidence = detail_of(client, insight).json()["candidate"]["evidence"]
    assert evidence["sample"]["n"] > 0 and evidence["coverage"]["pair_coverage"] is not None
    assert evidence["methods"]["methods"] and evidence["methods"]["agreement"]
    assert evidence["effect"]["minimum_absolute_effect"] > 0
    assert evidence["weekday"]["status"] in ("passed", "failed", "not_applicable",
                                             "not_evaluable")
    assert {item["name"] for item in evidence["checks"]} >= {
        "sample_size", "coverage", "effect_size", "weekday_control", "multiple_comparisons"}
    assert evidence["stability"]["segment_count"] == 3


# --- history and snapshot policy ------------------------------------------------------

REFRESH = {"start": START.isoformat(), "end": END.isoformat()}


def refresh(client, **overrides):
    response = client.post("/api/analytics/insights/refresh", json={**REFRESH, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def test_get_requests_never_write_history(client, session, seeded):
    before = len(snapshot_rows(session))
    for _ in range(3):
        client.get("/api/analytics/insights", params=WINDOW)
        client.get("/api/analytics/insights", params={**WINDOW, "include_hidden": "true"})
    assert len(snapshot_rows(session)) == before == 0


def test_refresh_is_idempotent_within_one_calendar_day(client, session, seeded):
    first = refresh(client)["snapshots"]
    assert first["created"] == first["total"] > 0 and first["updated"] == 0
    rows = snapshot_rows(session)
    before = [(row.fingerprint, row.updated_at, row.statement, row.presentation_status)
              for row in rows]
    second = refresh(client)["snapshots"]
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == second["total"] == first["total"]
    after = [(row.fingerprint, row.updated_at, row.statement, row.presentation_status)
             for row in snapshot_rows(session)]
    assert before == after, "an identical same-day refresh must not touch a single row"


def test_refresh_snapshots_the_representative_of_every_group_and_stores_provenance(
        client, session, seeded):
    result = refresh(client)
    assert result["snapshots"]["total"] == result["analytics"]["summary"]["counts"]["groups"]
    assert result["analytics"]["summary"]["counts"]["shown"] < result["snapshots"]["total"]
    rows = snapshot_rows(session)
    for row in rows:
        assert row.fingerprint and len(row.fingerprint) == 64
        assert row.insight_policy_version == "1" and row.template_version == "1"
        assert row.guardrail_policy_version == "1" and row.confidence_policy_version == "1"
        assert row.evaluated_on == TODAY and row.period_start == START and row.period_end == END
        assert row.grain == "daily" and row.lag_unit == "day"
        assert row.presentation_status in ("preliminary", "stable", "well_supported",
                                           "warning", "hidden", "not_evaluable")
        isinstance(row.blocking_reasons, list) and isinstance(row.warnings, list)
        assert row.statement == row.statement.strip() != ""


def test_second_evaluation_day_appends_one_ordered_snapshot_per_hypothesis(
        app, client, session, seeded):
    refresh(client)
    fingerprints = sorted(row.fingerprint for row in snapshot_rows(session))
    app.state.clock = FrozenClock(TODAY + timedelta(days=1))
    second = refresh(client)["snapshots"]
    assert second["created"] == second["total"] == len(fingerprints)
    for fingerprint in fingerprints:
        history = client.get(f"/api/analytics/insights/{fingerprint}/history").json()
        assert [item["evaluated_on"] for item in history] == [
            TODAY.isoformat(), (TODAY + timedelta(days=1)).isoformat()]
        assert all(item["fingerprint"] == fingerprint for item in history)


def test_history_is_empty_until_the_first_explicit_refresh(client, seeded):
    feed = client.get("/api/analytics/insights", params=WINDOW).json()
    fingerprint = feed["insights"][0]["fingerprint"]
    assert client.get(f"/api/analytics/insights/{fingerprint}/history").json() == []
    refresh(client)
    history = client.get(f"/api/analytics/insights/{fingerprint}/history").json()
    assert len(history) == 1 and history[0]["evaluated_on"] == TODAY.isoformat()
    assert history[0]["period"]["start"] == START.isoformat()


def test_first_seen_is_reported_after_a_snapshot_exists(app, client, session, seeded):
    feed = client.get("/api/analytics/insights", params=WINDOW).json()
    assert feed["insights"][0]["first_seen"] is None
    refresh(client)
    later = client.get("/api/analytics/insights", params=WINDOW).json()
    assert all(item["first_seen"] == TODAY.isoformat() for item in later["insights"])
    app.state.clock = FrozenClock(TODAY + timedelta(days=2))
    refresh(client)
    newest = client.get("/api/analytics/insights", params=WINDOW).json()
    assert all(item["first_seen"] == TODAY.isoformat() for item in newest["insights"])


# --- identity across rename and archive ------------------------------------------------


def test_renaming_a_habit_keeps_one_identity_and_updates_only_the_label(
        app, client, session, health_area, seeded):
    trained, _walk, _never = seeded
    before = client.get("/api/analytics/insights", params=WINDOW).json()
    target = pick(before, lambda item: "Тренировка" in {item["x"]["label"], item["y"]["label"]})
    habit_side = "x" if target["x"]["label"] == "Тренировка" else "y"
    old_key = target[habit_side]["key"]
    refresh(client)

    habits.update_habit(session, trained.id,
                        config(health_area["id"], name="Силовая тренировка", weight=3),
                        effective_date=START + timedelta(days=30))
    app.state.clock = FrozenClock(TODAY + timedelta(days=1))
    refresh(client)

    other_key = target["x"]["key"] if habit_side == "y" else target["y"]["key"]
    after = client.get("/api/analytics/insights", params=WINDOW).json()
    # The same *pair* is found by stable key, never by its (mutable) label.
    renamed = pick(after, lambda item: {item["x"]["key"], item["y"]["key"]}
                   == {old_key, other_key})
    assert renamed["fingerprint"] == target["fingerprint"]
    assert renamed[habit_side]["label"] == "Силовая тренировка"
    history = client.get(
        f"/api/analytics/insights/{target['fingerprint']}/history").json()
    assert len(history) == 2, "a rename must not fork the history"
    assert [item["evaluated_on"] for item in history] == [TODAY.isoformat(),
                                                          (TODAY + timedelta(days=1)).isoformat()]
    assert history[0][f"{habit_side}_label"] == "Тренировка"
    assert history[1][f"{habit_side}_label"] == "Силовая тренировка"
    assert all(item["fingerprint"] == target["fingerprint"] for item in history)


def test_history_survives_archiving_and_marks_the_habit(client, session, seeded):
    trained, walk, _never = seeded
    assert trained and walk
    refresh(client)
    fingerprint = pick(
        client.get("/api/analytics/insights", params=WINDOW).json(),
        lambda item: "Прогулка" in {item["x"]["label"], item["y"]["label"]})["fingerprint"]
    habits.archive_habit(session, walk.id)

    history = client.get(f"/api/analytics/insights/{fingerprint}/history").json()
    assert len(history) == 1
    assert "Прогулка" in (history[0]["x_label"], history[0]["y_label"])
    flags = [history[0]["x_archived"], history[0]["y_archived"]]
    assert True in flags and None in flags
    # The archived habit leaves the *current* discovery sweep but keeps its history.
    after = client.get("/api/analytics/insights", params=WINDOW).json()
    assert all("Прогулка" not in {item["x"]["label"], item["y"]["label"]}
               for item in after["insights"])
    catalogue = client.get("/api/analytics/insights/variables").json()
    archived = next(item for item in catalogue["variables"] if item["habit_id"] == walk.id)
    assert archived["is_archived"] is True and archived["label"].endswith("(в архиве)")


# --- cost -----------------------------------------------------------------------------


def statement_counter(session):
    """Count SQL statements issued on this test's own engine (never shared)."""

    counts: list[int] = []

    def before(*_args):
        counts.append(1)

    event.listen(session.get_bind(), "before_cursor_execute", before)
    return counts


def test_one_dataset_build_and_one_family_per_request(monkeypatch, client, seeded):
    builds: list[int] = []
    families: list[int] = []
    original_build = analytics.get_dataset
    from app.services import insights as service

    original_family = service.analyze_guardrails
    monkeypatch.setattr(analytics, "get_dataset",
                        lambda *a, **k: (builds.append(1), original_build(*a, **k))[1])
    monkeypatch.setattr(service, "analyze_guardrails",
                        lambda *a, **k: (families.append(1), original_family(*a, **k))[1])

    feed = client.get("/api/analytics/insights", params=WINDOW).json()
    assert (len(builds), len(families)) == (1, 1)
    insight = feed["insights"][0]
    detail_of(client, insight)
    assert (len(builds), len(families)) == (2, 2)
    refresh(client)
    # Refresh recomputes the family once but builds the dataset once as well.
    assert (len(builds), len(families)) == (3, 3)
    client.get(f"/api/analytics/insights/{insight['fingerprint']}/history")
    assert (len(builds), len(families)) == (3, 3)


def test_sql_statement_count_does_not_grow_with_the_number_of_hypotheses(
        client, session, seeded):
    narrow = statement_counter(session)
    client.get("/api/analytics/insights", params={**WINDOW, "lags": "0"})
    narrow_queries = len(narrow)

    wide = statement_counter(session)
    payload = client.get("/api/analytics/insights", params=WINDOW).json()
    wide_queries = len(wide)
    assert payload["summary"]["counts"]["hypotheses"] == 225
    assert narrow_queries <= wide_queries
    # 225 hypotheses behave exactly like 6: the count is per request, not per hypothesis.
    assert wide_queries == narrow_queries, (narrow_queries, wide_queries)
    assert wide_queries <= 24, wide_queries


# --- explorer mode and display filters -----------------------------------------------


def test_explorer_mode_evaluates_one_pre_selected_pair(client, seeded):
    payload = client.get("/api/analytics/insights", params={
        **WINDOW, "x": "state.mood", "y": "state.energy"}).json()
    assert payload["mode"] == "explorer" and len(payload["insights"]) == 1
    insight = payload["insights"][0]
    assert insight["guardrail"]["family_mode"] == "single"
    assert insight["guardrail"]["family_rank"] is None
    assert len(insight["alternatives"]) == 1
    assert insight["status"] in ("preliminary", "stable", "well_supported")
    # A same-period pair is canonicalised, so requesting it reversed is the same insight.
    reversed_pair = client.get("/api/analytics/insights", params={
        **WINDOW, "x": "state.energy", "y": "state.mood"}).json()["insights"][0]
    assert reversed_pair["fingerprint"] == insight["fingerprint"]


def test_explorer_negative_lag_is_honest_about_the_order(client, seeded):
    """A negative lag must never read as if the requested X came first."""
    payload = client.get("/api/analytics/insights", params={
        **WINDOW, "x": "daily.score", "y": "habit.1.daily.completion",
        "lag": "-1"}).json()
    insight = payload["insights"][0]
    assert insight["orientation"] == "x_later" and insight["lag"] == -1
    assert insight["text"]["timing"] == "Обратный порядок: 1 день"
    assert "negative_lag_reversed_order" in [item["code"] for item in insight["caveats"]]
    # The sentence starts from the *earlier* measurement (the habit), not from X.
    assert insight["text"]["statement"] == (
        "После дней, когда было отмечено «Тренировка», на следующий день значение "
        "«Процент выполнения» обычно было выше.")

    weak = client.get("/api/analytics/insights", params={
        **WINDOW, "x": "state.mood", "y": "state.sleep_minutes", "lag": "-1"}).json()
    weak_insight = weak["insights"][0]
    assert weak_insight["text"]["timing"] == "Обратный порядок: 1 день"
    # A reversed pair with no signal stays directionless instead of inventing one.
    assert "обычно было" not in weak_insight["text"]["statement"]


def test_confidence_and_verdict_filters_are_applied_by_the_backend(client, seeded):
    hidden = client.get("/api/analytics/insights",
                        params={**WIDE, "include_hidden": "true"}).json()
    levels = {item["confidence"]["level"] for item in hidden["insights"]}
    assert {"preliminary", "well_supported"} <= levels

    filtered = client.get("/api/analytics/insights", params={
        **WIDE, "include_hidden": "true", "confidence": "preliminary"}).json()
    assert filtered["insights"]
    assert {item["confidence"]["level"] for item in filtered["insights"]} == {"preliminary"}

    blocked = client.get("/api/analytics/insights", params={
        **WIDE, "include_hidden": "true", "verdicts": "blocked"}).json()
    assert blocked["insights"]
    assert {item["guardrail"]["verdict"] for item in blocked["insights"]} == {"blocked"}

    focused = client.get("/api/analytics/insights", params={
        **WIDE, "include_hidden": "true", "variables": "state.sleep_minutes"}).json()
    assert focused["insights"]
    assert all("state.sleep_minutes" in {item["x"]["key"], item["y"]["key"]}
               for item in focused["insights"])
    # Filters change the presentation only; the family and its verdicts do not move.
    assert focused["summary"]["counts"]["hypotheses"] == 420


# --- error contract ------------------------------------------------------------------


def _error_code(response):
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] and body["error"]["message"]
    return body["error"]["code"]


@pytest.mark.parametrize("params,expected", [
    ({"start": "2026-10-05", "end": "2026-09-05"}, "invalid_insight_request"),
    ({"start": "2026-09-07", "end": "2026-09-09"}, "invalid_insight_request"),
    ({"start": "2024-01-01", "end": "2026-09-07"}, "invalid_insight_request"),
    ({"start": "2026-09-07", "end": "2027-02-07"}, "invalid_insight_request"),
    ({**WINDOW, "x": "state.mood"}, "invalid_insight_request"),
    ({**WINDOW, "x": "state.mood", "y": "state.nope"}, "invalid_insight_request"),
    ({**WINDOW, "confidence": "banana"}, "invalid_insight_request"),
    ({**WINDOW, "verdicts": "banana"}, "invalid_insight_request"),
    ({**WINDOW, "x": "state.mood", "y": "state.energy", "lags": "0"},
     "invalid_insight_request"),
    ({**WINDOW, "max_variables": "3"}, "invalid_insight_request"),
    ({**WINDOW, "lag": "-3"}, "invalid_insight_request"),
])
def test_invalid_requests_are_typed_and_localized(client, seeded, params, expected):
    response = client.get("/api/analytics/insights", params=params)
    assert response.status_code == 422, response.text
    assert _error_code(response) == expected


def test_missing_dates_are_reported_as_a_localized_validation_error(client, seeded):
    response = client.get("/api/analytics/insights", params={"start": START.isoformat()})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "даты" in response.json()["error"]["message"]


def test_detail_rejects_a_fingerprint_that_does_not_describe_the_hypothesis(client, seeded):
    other = insight_fingerprint("state.mood", "state.sleep_minutes", Grain.DAILY, 0)
    response = client.get(f"/api/analytics/insights/{other}", params={
        "start": START.isoformat(), "end": END.isoformat(), "x": "state.mood",
        "y": "state.energy", "lag": "0", "mode": "explorer"})
    assert response.status_code == 422
    assert _error_code(response) == "insight_identity_mismatch"


def test_unknown_history_and_forbidden_methods_are_reported_clearly(client, seeded):
    assert client.get("/api/analytics/insights/" + "0" * 64 + "/history").json() == []
    missing = client.get("/api/analytics/insights/" + "0" * 64, params={
        "start": START.isoformat(), "end": END.isoformat(), "x": "state.mood",
        "y": "state.energy", "mode": "explorer"})
    assert missing.status_code == 404 and _error_code(missing) == "insight_not_found"
    assert client.post("/api/analytics/insights", json=WINDOW).status_code == 405
    assert client.get("/api/analytics/insights/refresh").status_code == 405


def test_insufficient_data_is_not_an_http_error(client, session, health_area, app):
    app.state.clock = FrozenClock(TODAY)
    payload = client.get("/api/analytics/insights", params=WINDOW)
    assert payload.status_code == 200
    body = payload.json()
    assert body["insights"] == []
    assert body["summary"]["availability"] == "no_data"
    assert body["summary"]["message"] == "За выбранный период данных для аналитики нет."


def test_too_few_paired_days_report_insufficient_data_without_an_error(client, session,
                                                                     health_area, app):
    app.state.clock = FrozenClock(TODAY)
    for index in range(3):
        daily_state.save_state(session, START + timedelta(days=40 + index),
                               StateValues(mood=index + 2, energy=index + 1), today=TODAY)
    body = client.get("/api/analytics/insights", params=WINDOW).json()
    assert body["summary"]["availability"] == "insufficient_data"
    assert body["summary"]["message"] == (
        "Пока недостаточно совместных наблюдений для устойчивых выводов.")
    assert body["insights"] == []
    assert body["summary"]["counts"]["hypotheses"] > 0
    assert body["summary"]["counts"]["evaluated_hypotheses"] == 0


def test_concurrent_refresh_resolves_unique_key_conflicts(monkeypatch, session, database, seeded):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from app.services import insights as service

    request = InsightRequest(START, END)
    evaluated = service.evaluate(session, request, today=TODAY)
    monkeypatch.setattr(service, "evaluate", lambda *a, **k: evaluated)
    barrier = Barrier(2)
    original = Session.scalars

    def synchronized_rows(self, statement, *args, **kwargs):
        result = original(self, statement, *args, **kwargs)
        sql = str(statement)
        if "WHERE insight_snapshots.evaluated_on =" in sql:
            rows = list(result)
            barrier.wait(timeout=20)  # Both requests saw the same empty table.
            return rows
        return result

    monkeypatch.setattr(Session, "scalars", synchronized_rows)

    def run():
        with database.session() as worker:
            return service.refresh(worker, request, today=TODAY).snapshots

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    rows = snapshot_rows(session)
    assert len(rows) > 0
    assert sum(result.created for result in results) == len(rows)
    assert sum(result.unchanged for result in results) == len(rows)
    assert len({(row.fingerprint, row.evaluated_on) for row in rows}) == len(rows)


def test_alternative_labels_disambiguate_both_temporal_directions(client, seeded):
    payload = client.get("/api/analytics/insights", params=WINDOW).json()
    insight = payload["insights"][0]
    alternatives = [item for item in insight["alternatives"] if item["lag"] == 1]
    assert len(alternatives) == 2
    assert alternatives[0]["timing"] != alternatives[1]["timing"]
    for item in alternatives:
        assert insight["x"]["label"] in item["timing"]
        assert insight["y"]["label"] in item["timing"]
        assert "На следующий день" in item["timing"]


def test_history_limit_keeps_latest_evaluations_in_chronological_order(session, seeded):
    from app.services import insights as service
    from app.domain.analytics.insight_types import POLICY

    insight = service.get_insights(session, InsightRequest(START, END), today=TODAY).insights[0]
    for index in range(POLICY.maximum_history_returned + 1):
        on = TODAY - timedelta(days=index)
        session.add(InsightSnapshot(**service._snapshot_values(insight, on)))
    session.commit()
    history = service.get_history(session, insight.fingerprint)
    assert len(history) == POLICY.maximum_history_returned
    assert history[-1].evaluated_on == TODAY
    assert history[0].evaluated_on == TODAY - timedelta(days=199)
