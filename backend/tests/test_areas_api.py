"""Area endpoints: CRUD, uniqueness, archive behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import habit_payload


def names(areas: list[dict]) -> list[str]:
    return [area["name"] for area in areas]


class TestCreate:
    def test_creates_an_area(self, client: TestClient) -> None:
        response = client.post(
            "/api/areas", json={"name": "Health", "color": "#2f9e5f"}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["id"] > 0
        assert body["name"] == "Health"
        assert body["color"] == "#2f9e5f"
        assert body["is_archived"] is False
        assert body["archived_at"] is None
        assert body["created_at"] and body["updated_at"]

    def test_trims_and_collapses_the_name(self, client: TestClient) -> None:
        response = client.post("/api/areas", json={"name": "  Deep   Work  "})

        assert response.status_code == 201
        assert response.json()["name"] == "Deep Work"

    def test_colour_defaults_when_omitted(self, client: TestClient) -> None:
        response = client.post("/api/areas", json={"name": "Health"})

        assert response.status_code == 201
        assert response.json()["color"].startswith("#")

    def test_normalises_colour_case(self, client: TestClient) -> None:
        response = client.post(
            "/api/areas", json={"name": "Health", "color": "#AABBCC"}
        )

        assert response.status_code == 201
        assert response.json()["color"] == "#aabbcc"

    def test_rejects_an_invalid_colour(self, client: TestClient) -> None:
        response = client.post(
            "/api/areas", json={"name": "Health", "color": "green"}
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_area_color"

    def test_rejects_an_empty_name(self, client: TestClient) -> None:
        response = client.post("/api/areas", json={"name": "   "})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_area_name"

    def test_rejects_a_duplicate_name_regardless_of_case(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post("/api/areas", json={"name": "health"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_name_conflict"


class TestListAndFetch:
    def test_lists_areas_alphabetically(self, client: TestClient) -> None:
        for name in ("Work", "Health", "Development"):
            client.post("/api/areas", json={"name": name})

        response = client.get("/api/areas")

        assert response.status_code == 200
        assert names(response.json()) == ["Development", "Health", "Work"]

    def test_lists_active_areas_only_by_default(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        client.post(f"/api/areas/{health_area['id']}/archive")

        assert names(client.get("/api/areas").json()) == ["Development"]

    def test_includes_archived_areas_on_request(
        self, client: TestClient, health_area: dict
    ) -> None:
        client.post(f"/api/areas/{health_area['id']}/archive")

        response = client.get("/api/areas", params={"include_archived": True})

        assert names(response.json()) == ["Health"]
        assert response.json()[0]["is_archived"] is True

    def test_fetches_a_single_area(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.get(f"/api/areas/{health_area['id']}")

        assert response.status_code == 200
        assert response.json()["name"] == "Health"

    def test_unknown_area_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/areas/4242")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "area_not_found"


class TestUpdate:
    def test_renames_an_area(self, client: TestClient, health_area: dict) -> None:
        response = client.patch(
            f"/api/areas/{health_area['id']}", json={"name": "Wellbeing"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Wellbeing"

    def test_recolours_an_area(self, client: TestClient, health_area: dict) -> None:
        response = client.patch(
            f"/api/areas/{health_area['id']}", json={"color": "#123456"}
        )

        assert response.status_code == 200
        assert response.json()["color"] == "#123456"

    def test_rejects_a_conflicting_rename(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        response = client.patch(
            f"/api/areas/{health_area['id']}", json={"name": "Development"}
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_name_conflict"

    def test_allows_renaming_an_area_to_its_own_name(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.patch(
            f"/api/areas/{health_area['id']}", json={"name": "Health"}
        )

        assert response.status_code == 200

    def test_rejects_an_empty_update(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.patch(f"/api/areas/{health_area['id']}", json={})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_unknown_area_returns_404(self, client: TestClient) -> None:
        response = client.patch("/api/areas/4242", json={"name": "Nope"})

        assert response.status_code == 404


class TestArchive:
    def test_archives_and_hides_an_area(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(f"/api/areas/{health_area['id']}/archive")

        assert response.status_code == 200
        body = response.json()
        assert body["is_archived"] is True
        assert body["archived_at"] is not None
        assert client.get("/api/areas").json() == []

    def test_archiving_twice_is_idempotent(
        self, client: TestClient, health_area: dict
    ) -> None:
        first = client.post(f"/api/areas/{health_area['id']}/archive")
        second = client.post(f"/api/areas/{health_area['id']}/archive")

        assert second.status_code == 200
        assert second.json()["archived_at"] == first.json()["archived_at"]

    def test_refuses_to_archive_an_area_with_active_habits(
        self, client: TestClient, health_area: dict
    ) -> None:
        client.post(
            "/api/habits",
            json=habit_payload(name="Reading", area_id=health_area["id"]),
        )

        response = client.post(f"/api/areas/{health_area['id']}/archive")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_has_active_habits"

    def test_archives_an_area_once_its_habits_are_archived(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = client.post(
            "/api/habits",
            json=habit_payload(name="Reading", area_id=health_area["id"]),
        ).json()
        client.post(f"/api/habits/{habit['id']}/archive")

        response = client.post(f"/api/areas/{health_area['id']}/archive")

        assert response.status_code == 200

    def test_unarchives_an_area(
        self, client: TestClient, health_area: dict
    ) -> None:
        client.post(f"/api/areas/{health_area['id']}/archive")

        response = client.post(f"/api/areas/{health_area['id']}/unarchive")

        assert response.status_code == 200
        assert response.json()["is_archived"] is False
        assert response.json()["archived_at"] is None
        assert names(client.get("/api/areas").json()) == ["Health"]

    def test_unarchiving_twice_is_idempotent(
        self, client: TestClient, health_area: dict
    ) -> None:
        response = client.post(f"/api/areas/{health_area['id']}/unarchive")

        assert response.status_code == 200
        assert response.json()["is_archived"] is False

    def test_unarchive_is_refused_when_the_name_is_taken(
        self, client: TestClient, health_area: dict
    ) -> None:
        client.post(f"/api/areas/{health_area['id']}/archive")
        client.post("/api/areas", json={"name": "Health"})

        response = client.post(f"/api/areas/{health_area['id']}/unarchive")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "area_name_conflict"

    def test_unknown_area_returns_404(self, client: TestClient) -> None:
        assert client.post("/api/areas/4242/archive").status_code == 404
        assert client.post("/api/areas/4242/unarchive").status_code == 404


class TestNoHardDelete:
    def test_areas_cannot_be_deleted(self, client: TestClient) -> None:
        """Areas are archived instead of deleted, to protect history."""
        response = client.delete("/api/areas/1")

        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"
