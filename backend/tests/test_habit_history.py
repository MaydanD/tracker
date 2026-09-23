"""Habit configuration history.

The point of these tests: editing a habit must never rewrite the meaning of past
days. Every change is recorded as a configuration version effective from a
calendar date, and earlier versions stay exactly as they were.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.domain.errors import ConfigurationHistoryError
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode
from app.services import habits as habit_service


def today_offset(days: int) -> str:
    return (today_local() + timedelta(days=days)).isoformat()


def make_config(area_id: int, **overrides: object) -> HabitConfig:
    values: dict[str, object] = {
        "name": "Reading",
        "area_id": area_id,
        "weight": 1,
        "tracking_mode": TrackingMode.BINARY,
        "schedule": Schedule.create("daily"),
    }
    values.update(overrides)
    return HabitConfig.create(**values)  # type: ignore[arg-type]


def create_habit(client: TestClient, area_id: int, **overrides: object) -> dict:
    from tests.helpers import habit_payload

    response = client.post(
        "/api/habits", json=habit_payload(area_id=area_id, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def versions(client: TestClient, habit_id: int) -> list[dict]:
    response = client.get(f"/api/habits/{habit_id}/versions")
    assert response.status_code == 200, response.text
    return response.json()


class TestInitialVersion:
    def test_a_new_habit_has_exactly_one_version(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        history = versions(client, habit["id"])

        assert len(history) == 1
        assert history[0]["version_number"] == 1
        assert history[0]["effective_from"] == today_local().isoformat()
        assert history[0]["habit_id"] == habit["id"]

    def test_the_first_version_describes_the_created_configuration(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            weight=2,
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
            schedule={"type": "weekdays", "weekdays": [0, 2, 4]},
        )

        version = versions(client, habit["id"])[0]

        assert version["name"] == "Walking"
        assert version["weight"] == 2
        assert version["quantity_unit"] == "km"
        assert version["quantity_allows_decimal"] is True
        assert version["schedule"]["weekdays"] == [0, 2, 4]
        assert version["schedule"]["weekly_required_count"] == 3


class TestSameDayEdits:
    def test_a_same_day_edit_updates_that_days_version(
        self, client: TestClient, health_area: dict
    ) -> None:
        """One version per habit per day, so the quota of versions stays honest."""
        habit = create_habit(client, health_area["id"], name="Reading", weight=1)

        client.put(
            f"/api/habits/{habit['id']}",
            json={
                "name": "Reading",
                "area_id": health_area["id"],
                "weight": 3,
                "tracking_mode": "binary",
                "schedule": {"type": "daily"},
            },
        )

        history = versions(client, habit["id"])

        assert len(history) == 1
        assert history[0]["version_number"] == 1
        assert history[0]["weight"] == 3

    def test_an_unchanged_configuration_does_not_create_a_version(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading", weight=2)

        response = client.put(
            f"/api/habits/{habit['id']}",
            json={
                "name": "Reading",
                "area_id": health_area["id"],
                "weight": 2,
                "tracking_mode": "binary",
                "schedule": {"type": "daily"},
            },
        )

        assert response.status_code == 200
        assert len(versions(client, habit["id"])) == 1

    def test_the_habit_response_reflects_the_latest_edit(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        client.put(
            f"/api/habits/{habit['id']}",
            json={
                "name": "Deep reading",
                "area_id": health_area["id"],
                "weight": 1,
                "tracking_mode": "binary",
                "schedule": {"type": "daily"},
            },
        )

        assert client.get(f"/api/habits/{habit['id']}").json()["name"] == "Deep reading"


class TestLaterChanges:
    def test_a_later_change_appends_a_version(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], weight=1)

        habit_service.update_habit(
            session,
            habit["id"],
            make_config(health_area["id"], weight=3),
            effective_date=today_local() + timedelta(days=1),
        )

        history = versions(client, habit["id"])

        assert [entry["version_number"] for entry in history] == [2, 1]
        assert history[0]["effective_from"] == today_offset(1)
        assert history[0]["weight"] == 3
        assert history[1]["weight"] == 1
        assert history[1]["effective_from"] == today_offset(0)

    def test_a_weight_change_preserves_the_old_value(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], weight=2)

        habit_service.update_habit(
            session,
            habit["id"],
            make_config(health_area["id"], weight=1),
            effective_date=today_local() + timedelta(days=2),
        )

        history = versions(client, habit["id"])

        assert history[0]["weight"] == 1
        assert history[1]["weight"] == 2

    def test_a_schedule_change_preserves_the_old_schedule(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        habit_service.update_habit(
            session,
            habit["id"],
            make_config(
                health_area["id"],
                schedule=Schedule.create("weekdays", weekdays=[0, 2, 4]),
            ),
            effective_date=today_local() + timedelta(days=1),
        )

        history = versions(client, habit["id"])

        assert history[0]["schedule"]["type"] == "weekdays"
        assert history[1]["schedule"]["type"] == "daily"

    def test_an_area_move_preserves_the_old_area(
        self,
        session: Session,
        client: TestClient,
        health_area: dict,
        other_area: dict,
    ) -> None:
        habit = create_habit(client, health_area["id"])

        habit_service.update_habit(
            session,
            habit["id"],
            make_config(other_area["id"]),
            effective_date=today_local() + timedelta(days=1),
        )

        history = versions(client, habit["id"])

        assert history[0]["area_id"] == other_area["id"]
        assert history[0]["area"]["name"] == "Development"
        assert history[1]["area_id"] == health_area["id"]
        assert history[1]["area"]["name"] == "Health"

    def test_a_rename_preserves_the_old_name(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        habit_service.update_habit(
            session,
            habit["id"],
            make_config(health_area["id"], name="Deep reading"),
            effective_date=today_local() + timedelta(days=1),
        )

        history = versions(client, habit["id"])

        assert history[0]["name"] == "Deep reading"
        assert history[1]["name"] == "Reading"

    def test_successive_changes_accumulate(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], weight=1)

        for day, weight in ((1, 2), (2, 3)):
            habit_service.update_habit(
                session,
                habit["id"],
                make_config(health_area["id"], weight=weight),
                effective_date=today_local() + timedelta(days=day),
            )

        history = versions(client, habit["id"])

        assert [entry["version_number"] for entry in history] == [3, 2, 1]
        assert [entry["weight"] for entry in history] == [3, 2, 1]


class TestEffectiveConfiguration:
    def test_resolves_the_configuration_for_a_past_date(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        """This is what Stage 4 needs: 'what weight applied on date X?'."""
        habit = create_habit(client, health_area["id"], weight=1)
        habit_service.update_habit(
            session,
            habit["id"],
            make_config(health_area["id"], weight=3),
            effective_date=today_local() + timedelta(days=1),
        )

        on_today = client.get(
            f"/api/habits/{habit['id']}/configuration",
            params={"on": today_offset(0)},
        )
        on_tomorrow = client.get(
            f"/api/habits/{habit['id']}/configuration",
            params={"on": today_offset(1)},
        )
        later = client.get(
            f"/api/habits/{habit['id']}/configuration",
            params={"on": today_offset(30)},
        )

        assert on_today.json()["version_number"] == 1
        assert on_today.json()["weight"] == 1
        assert on_tomorrow.json()["version_number"] == 2
        assert on_tomorrow.json()["weight"] == 3
        assert later.json()["version_number"] == 2

    def test_a_date_before_the_habit_existed_is_a_404(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        response = client.get(
            f"/api/habits/{habit['id']}/configuration",
            params={"on": today_offset(-1)},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "configuration_not_found"

    def test_a_missing_date_is_a_validation_error(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        response = client.get(f"/api/habits/{habit['id']}/configuration")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_unknown_habit_returns_404(self, client: TestClient) -> None:
        response = client.get(
            "/api/habits/4242/configuration", params={"on": today_offset(0)}
        )

        assert response.status_code == 404


class TestHistoryGuardrails:
    def test_a_change_before_the_current_version_is_rejected(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], weight=1)

        with pytest.raises(ConfigurationHistoryError) as raised:
            habit_service.update_habit(
                session,
                habit["id"],
                make_config(health_area["id"], weight=3),
                effective_date=today_local() - timedelta(days=1),
            )

        # Surfaces through the shared error envelope as a 422.
        assert raised.value.status_code == 422
        assert raised.value.code == "invalid_configuration_date"
        assert len(versions(client, habit["id"])) == 1

    def test_history_of_an_unknown_habit_returns_404(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/habits/4242/versions")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "habit_not_found"
