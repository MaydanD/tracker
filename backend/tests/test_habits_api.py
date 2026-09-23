"""Habit endpoints: configuration, validation, filtering, archive behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services import areas as area_service
from app.services import habits as habit_service
from tests.helpers import habit_payload


def create_habit(client: TestClient, area_id: int, **overrides: object) -> dict:
    response = client.post(
        "/api/habits", json=habit_payload(area_id=area_id, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    def test_duplicate_names_in_the_same_area_are_allowed(
        self, client: TestClient, health_area: dict
    ) -> None:
        first = create_habit(client, health_area["id"], name="Reading")
        second = create_habit(client, health_area["id"], name="Reading")
        assert first["id"] != second["id"]
        assert len(client.get("/api/habits").json()) == 2

    def test_creates_a_binary_daily_habit(
        self, client: TestClient, health_area: dict
    ) -> None:
        body = create_habit(
            client, health_area["id"], name="Reading", weight=2, description="Books"
        )

        assert body["name"] == "Reading"
        assert body["description"] == "Books"
        assert body["weight"] == 2
        assert body["tracking_mode"] == "binary"
        assert body["quantity_unit"] is None
        assert body["area"]["name"] == "Health"
        assert body["area_id"] == health_area["id"]
        assert body["is_archived"] is False
        assert body["schedule"] == {
            "type": "daily",
            "weekdays": [],
            "times_per_week": None,
            "weekly_required_count": 7,
            "summary": "Every day",
        }

    def test_creation_records_the_first_configuration_version(
        self, client: TestClient, health_area: dict
    ) -> None:
        body = create_habit(client, health_area["id"])

        assert body["current_version"]["version_number"] == 1
        assert body["current_version"]["effective_from"]

    def test_creates_a_quantity_habit_with_a_unit(
        self, client: TestClient, health_area: dict
    ) -> None:
        body = create_habit(
            client,
            health_area["id"],
            name="Reading",
            tracking_mode="binary_quantity",
            quantity_unit="  pages ",
            quantity_allows_decimal=False,
        )

        assert body["tracking_mode"] == "binary_quantity"
        assert body["quantity_unit"] == "pages"
        assert body["quantity_allows_decimal"] is False

    def test_creates_a_weekday_schedule(
        self, client: TestClient, health_area: dict
    ) -> None:
        body = create_habit(
            client,
            health_area["id"],
            schedule={"type": "weekdays", "weekdays": [4, 0, 2]},
        )

        assert body["schedule"]["weekdays"] == [0, 2, 4]
        assert body["schedule"]["weekly_required_count"] == 3
        assert body["schedule"]["summary"] == "Mon, Wed, Fri (3 per week)"

    def test_creates_a_times_per_week_schedule(
        self, client: TestClient, health_area: dict
    ) -> None:
        body = create_habit(
            client,
            health_area["id"],
            schedule={"type": "times_per_week", "times_per_week": 3},
        )

        assert body["schedule"]["times_per_week"] == 3
        assert body["schedule"]["weekly_required_count"] == 3
        assert body["schedule"]["summary"] == "3 per week"

    def test_trims_the_name(self, client: TestClient, health_area: dict) -> None:
        body = create_habit(client, health_area["id"], name="  Reading  ")

        assert body["name"] == "Reading"


class TestValidation:
    @pytest.mark.parametrize("weight", [0, 4])
    def test_rejects_an_invalid_weight(
        self, client: TestClient, health_area: dict, weight: int
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(area_id=health_area["id"], weight=weight),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_weight"

    def test_rejects_a_quantity_habit_without_a_unit(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                tracking_mode="binary_quantity",
                quantity_unit=None,
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_quantity_unit"

    def test_rejects_a_weekday_schedule_without_days(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                schedule={"type": "weekdays", "weekdays": []},
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_schedule"

    def test_rejects_duplicate_weekdays(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                schedule={"type": "weekdays", "weekdays": [1, 1]},
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_schedule"

    @pytest.mark.parametrize("weekday", [-1, 7])
    def test_rejects_invalid_weekdays(
        self, client: TestClient, health_area: dict, weekday: int
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                schedule={"type": "weekdays", "weekdays": [weekday]},
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_schedule"

    @pytest.mark.parametrize("times", [0, 8])
    def test_rejects_an_out_of_range_weekly_quota(
        self, client: TestClient, health_area: dict, times: int
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                schedule={"type": "times_per_week", "times_per_week": times},
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_schedule"

    def test_rejects_a_weekday_schedule_with_an_independent_quota(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"],
                schedule={
                    "type": "weekdays",
                    "weekdays": [0, 2, 4],
                    "times_per_week": 2,
                },
            ),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_schedule"

    def test_rejects_an_unknown_schedule_type(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(
                area_id=health_area["id"], schedule={"type": "monthly"}
            ),
        )

        assert response.status_code == 422

    def test_rejects_an_unknown_area(self, client: TestClient) -> None:
        response = client.post("/api/habits", json=habit_payload(area_id=4242))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "area_not_found"

    def test_rejects_an_archived_area(
        self, client: TestClient, health_area: dict
    ) -> None:
        client.post(f"/api/areas/{health_area['id']}/archive")

        response = client.post(
            "/api/habits", json=habit_payload(area_id=health_area["id"])
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_archived"

    def test_rejects_an_empty_name(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(
            "/api/habits",
            json=habit_payload(area_id=health_area["id"], name="   "),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_habit_name"


class TestListAndFetch:
    def test_lists_habits_by_area_then_name(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        create_habit(client, other_area["id"], name="Reading")
        create_habit(client, health_area["id"], name="Sleep")
        create_habit(client, health_area["id"], name="Exercise")

        response = client.get("/api/habits")

        assert response.status_code == 200
        # Grouped by area name (Development before Health), then by habit name,
        # which is the order the UI presents them in.
        assert [habit["name"] for habit in response.json()] == [
            "Reading",
            "Exercise",
            "Sleep",
        ]
        assert [habit["area"]["name"] for habit in response.json()] == [
            "Development",
            "Health",
            "Health",
        ]

    def test_filters_by_area(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        create_habit(client, other_area["id"], name="Reading")
        create_habit(client, health_area["id"], name="Sleep")

        response = client.get("/api/habits", params={"area_id": health_area["id"]})

        assert [habit["name"] for habit in response.json()] == ["Sleep"]

    def test_lists_active_habits_only_by_default(
        self, client: TestClient, health_area: dict
    ) -> None:
        kept = create_habit(client, health_area["id"], name="Sleep")
        archived = create_habit(client, health_area["id"], name="Reading")
        client.post(f"/api/habits/{archived['id']}/archive")

        assert [habit["id"] for habit in client.get("/api/habits").json()] == [kept["id"]]

    def test_includes_archived_habits_on_request(
        self, client: TestClient, health_area: dict
    ) -> None:
        create_habit(client, health_area["id"], name="Sleep")
        archived = create_habit(client, health_area["id"], name="Reading")
        client.post(f"/api/habits/{archived['id']}/archive")

        response = client.get("/api/habits", params={"include_archived": True})

        assert len(response.json()) == 2

    def test_fetches_a_single_habit(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Sleep")

        response = client.get(f"/api/habits/{habit['id']}")

        assert response.status_code == 200
        assert response.json() == habit

    def test_unknown_habit_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/habits/4242")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "habit_not_found"


class TestUpdate:
    def test_replaces_the_configuration(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading", weight=1)

        response = client.put(
            f"/api/habits/{habit['id']}",
            json=habit_payload(
                area_id=health_area["id"],
                name="Deep reading",
                weight=3,
                tracking_mode="binary_quantity",
                quantity_unit="pages",
                schedule={"type": "times_per_week", "times_per_week": 5},
            ),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Deep reading"
        assert body["weight"] == 3
        assert body["quantity_unit"] == "pages"
        assert body["schedule"]["weekly_required_count"] == 5

    def test_can_move_a_habit_to_another_area(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        response = client.put(
            f"/api/habits/{habit['id']}",
            json=habit_payload(area_id=other_area["id"]),
        )

        assert response.status_code == 200
        assert response.json()["area"]["name"] == "Development"

    def test_rejects_an_invalid_update(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        response = client.put(
            f"/api/habits/{habit['id']}",
            json=habit_payload(area_id=health_area["id"], weight=9),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_weight"

    def test_unknown_habit_returns_404(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.put(
            "/api/habits/4242", json=habit_payload(area_id=health_area["id"])
        )

        assert response.status_code == 404


class TestArchive:
    def test_restore_requires_an_active_area(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = client.post(
            "/api/habits", json=habit_payload(area_id=health_area["id"])
        ).json()
        client.post(f"/api/habits/{habit['id']}/archive")
        assert client.post(f"/api/areas/{health_area['id']}/archive").status_code == 200

        response = client.post(f"/api/habits/{habit['id']}/unarchive")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_archived"
        assert client.get(f"/api/habits/{habit['id']}").json()["is_archived"] is True
        client.post(f"/api/areas/{health_area['id']}/unarchive")
        restored = client.post(f"/api/habits/{habit['id']}/unarchive")
        assert restored.status_code == 200
        assert restored.json()["is_archived"] is False

    def test_archives_and_restores_a_habit(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        archived = client.post(f"/api/habits/{habit['id']}/archive")
        assert archived.status_code == 200
        assert archived.json()["is_archived"] is True
        assert archived.json()["archived_at"] is not None
        assert client.get("/api/habits").json() == []

        restored = client.post(f"/api/habits/{habit['id']}/unarchive")
        assert restored.status_code == 200
        assert restored.json()["is_archived"] is False
        assert len(client.get("/api/habits").json()) == 1

    def test_archiving_twice_is_idempotent(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])

        first = client.post(f"/api/habits/{habit['id']}/archive")
        second = client.post(f"/api/habits/{habit['id']}/archive")

        assert second.json()["archived_at"] == first.json()["archived_at"]

    def test_an_archived_habit_keeps_its_history(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"])
        client.post(f"/api/habits/{habit['id']}/archive")

        response = client.get(f"/api/habits/{habit['id']}/versions")

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_unknown_habit_returns_404(self, client: TestClient) -> None:
        assert client.post("/api/habits/4242/archive").status_code == 404
        assert client.post("/api/habits/4242/unarchive").status_code == 404


class TestDatabaseConstraints:
    """The database enforces the same structural rules as the domain layer."""

    def _habit_with_version(self, session: Session, area_id: int) -> int:
        from app.domain.habits import HabitConfig
        from app.domain.schedule import Schedule
        from app.domain.tracking import TrackingMode

        habit = habit_service.create_habit(
            session,
            HabitConfig.create(
                name="Reading",
                area_id=area_id,
                weight=1,
                tracking_mode=TrackingMode.BINARY,
                schedule=Schedule.create("daily"),
            ),
        )
        return habit.id

    def test_rejects_an_out_of_range_weight(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_with_version(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO habit_versions (habit_id, version_number, "
                    "effective_from, created_at, name, area_id, weight, "
                    "tracking_mode, quantity_allows_decimal, schedule_type) "
                    "VALUES (:habit_id, 9, '2026-01-01', CURRENT_TIMESTAMP, "
                    "'Bad', :area_id, 4, 'binary', 0, 'daily')"
                ),
                {"habit_id": habit_id, "area_id": area_id},
            )
            session.commit()

    def test_rejects_a_malformed_schedule_shape(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_with_version(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO habit_versions (habit_id, version_number, "
                    "effective_from, created_at, name, area_id, weight, "
                    "tracking_mode, quantity_allows_decimal, schedule_type) "
                    "VALUES (:habit_id, 9, '2026-01-01', CURRENT_TIMESTAMP, "
                    "'Bad', :area_id, 1, 'binary', 0, 'weekdays')"
                ),
                {"habit_id": habit_id, "area_id": area_id},
            )
            session.commit()

    def test_rejects_a_quantity_unit_on_a_binary_habit(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_with_version(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO habit_versions (habit_id, version_number, "
                    "effective_from, created_at, name, area_id, weight, "
                    "tracking_mode, quantity_unit, quantity_allows_decimal, "
                    "schedule_type) VALUES (:habit_id, 9, '2026-01-01', "
                    "CURRENT_TIMESTAMP, 'Bad', :area_id, 1, 'binary', 'pages', "
                    "0, 'daily')"
                ),
                {"habit_id": habit_id, "area_id": area_id},
            )
            session.commit()

    def test_rejects_two_versions_for_the_same_day(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_with_version(session, area_id)
        existing = session.execute(
            text("SELECT effective_from FROM habit_versions WHERE habit_id = :id"),
            {"id": habit_id},
        ).scalar_one()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO habit_versions (habit_id, version_number, "
                    "effective_from, created_at, name, area_id, weight, "
                    "tracking_mode, quantity_allows_decimal, schedule_type) "
                    "VALUES (:habit_id, 2, :effective_from, CURRENT_TIMESTAMP, "
                    "'Reading', :area_id, 1, 'binary', 0, 'daily')"
                ),
                {
                    "habit_id": habit_id,
                    "area_id": area_id,
                    "effective_from": str(existing),
                },
            )
            session.commit()
