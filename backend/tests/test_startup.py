"""Application factory, startup wiring, and error envelope tests."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import DatabaseUnavailableError
from app.main import create_app


def test_factory_binds_settings_and_database(
    app: FastAPI, migrated_settings: Settings
) -> None:
    assert app.state.settings is migrated_settings
    assert app.state.database.database_url == migrated_settings.resolved_database_url


def test_startup_creates_the_data_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "runtime-data"
    settings = Settings(
        _env_file=None, app_env="test", data_dir=data_dir, log_level="WARNING"
    )
    assert not data_dir.exists()

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert data_dir.exists()


def test_factory_returns_independent_applications(tmp_path: Path) -> None:
    first = create_app(
        Settings(_env_file=None, app_env="test", data_dir=tmp_path / "one")
    )
    second = create_app(
        Settings(_env_file=None, app_env="test", data_dir=tmp_path / "two")
    )

    assert first is not second
    assert first.state.database.database_url != second.state.database.database_url

    first.state.database.dispose()
    second.state.database.dispose()


EXPECTED_PATHS = {
    "/api/analytics/confidence",
    "/api/analytics/guardrails",
    "/api/analytics/lags",
    "/api/analytics/descriptive",
    "/api/analytics/relationships",
    "/api/analytics/dataset",
    "/api/days/{state_date}/state",
    "/api/progress/days/{on}",
    "/api/progress/weeks/{on}",
    "/api/habits/{habit_id}/progress",
    # Stage 1
    "/api/health",
    "/api/ready",
    # Stage 2 — areas
    "/api/areas",
    "/api/areas/{area_id}",
    "/api/areas/{area_id}/archive",
    "/api/areas/{area_id}/unarchive",
    # Stage 2 — habits
    "/api/habits",
    "/api/habits/{habit_id}",
    "/api/habits/{habit_id}/archive",
    "/api/habits/{habit_id}/unarchive",
    "/api/habits/{habit_id}/versions",
    "/api/habits/{habit_id}/configuration",
    # Stage 3 — daily tracking
    "/api/days/{entry_date}",
    "/api/habits/{habit_id}/entries/{entry_date}",
    # Stage 6 — dashboard & calendar
    "/api/dashboard",
    "/api/calendar",
    "/api/days/{entry_date}/overview",
}


def test_openapi_documents_every_endpoint(client: TestClient) -> None:
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == EXPECTED_PATHS


def test_habits_and_areas_cannot_be_hard_deleted(client: TestClient) -> None:
    """Archiving protects history; no delete endpoint may creep in for them.

    A *daily entry* is different: it is the user's own note about a day, and
    clearing it returns the day to 'no entry'. That is the only delete in the API.
    """
    schema = client.get("/api/openapi.json").json()

    delete_operations = {
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method in operations
        if method.lower() == "delete"
    }

    assert delete_operations == {"DELETE /api/habits/{habit_id}/entries/{entry_date}", "DELETE /api/days/{state_date}/state"}


def test_interactive_docs_are_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_unknown_path_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unsupported_method_uses_the_error_envelope(client: TestClient) -> None:
    response = client.post("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_use_the_error_envelope(app: FastAPI) -> None:
    # A temporary parameterised route exercises the shared validation handler.
    @app.get("/api/_test/echo")
    def echo(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/api/_test/echo", params={"count": "not-a-number"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"]


def test_application_errors_use_the_error_envelope(app: FastAPI) -> None:
    @app.get("/api/_test/unavailable")
    def unavailable() -> None:
        raise DatabaseUnavailableError()

    with TestClient(app) as client:
        response = client.get("/api/_test/unavailable")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
