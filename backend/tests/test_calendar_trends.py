from fastapi.testclient import TestClient

from tests.helpers import habit_payload


def test_calendar_trends_group_recorded_completions_by_area_and_habit(
    client: TestClient, health_area: dict,
) -> None:
    today = client.get("/api/dashboard").json()["today"]
    habit_response = client.post(
        "/api/habits",
        json=habit_payload(area_id=health_area["id"], name="Reading"),
    )
    assert habit_response.status_code == 201, habit_response.text
    habit = habit_response.json()

    entry_response = client.put(
        f"/api/habits/{habit['id']}/entries/{today}",
        json={"status": "done"},
    )
    assert entry_response.status_code == 200, entry_response.text

    missed_habit_response = client.post(
        "/api/habits",
        json=habit_payload(area_id=health_area["id"], name="Exercise"),
    )
    assert missed_habit_response.status_code == 201, missed_habit_response.text
    missed_habit = missed_habit_response.json()
    missed_response = client.put(
        f"/api/habits/{missed_habit['id']}/entries/{today}",
        json={"status": "missed"},
    )
    assert missed_response.status_code == 200, missed_response.text

    response = client.get(
        "/api/calendar",
        params={"start": today, "end": today, "include_trends": "true"},
    )

    assert response.status_code == 200, response.text
    day = response.json()[0]
    assert day["area_scores"] == [
        {
            "area_id": health_area["id"],
            "name": health_area["name"],
            "color": health_area["color"],
            "score": 50.0,
        }
    ]
    assert {item["habit_id"]: item["score"] for item in day["habit_scores"]} == {
        habit["id"]: 100.0,
        missed_habit["id"]: 0.0,
    }


def test_calendar_trends_can_be_omitted_for_calendar_clients(
    client: TestClient,
) -> None:
    today = client.get("/api/dashboard").json()["today"]

    response = client.get("/api/calendar", params={"start": today, "end": today})

    assert response.status_code == 200
    assert response.json()[0]["area_scores"] == []
    assert response.json()[0]["habit_scores"] == []
