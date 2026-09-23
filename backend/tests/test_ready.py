"""Readiness endpoint tests, including the database-unavailable path."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_ready_reports_ready_with_a_migrated_database(client: TestClient) -> None:
    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "ok"},
    }


def test_ready_reports_unavailable_when_the_schema_is_behind(
    tmp_path: Path,
) -> None:
    """A reachable but un-migrated database is not ready.

    Product queries would fail with "no such table", so reporting not-ready here
    is what lets the UI tell the user to run the migration instead of showing a
    mysterious 500 later on.
    """
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="WARNING",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "ok", "migrations": "pending"},
    }


def test_health_still_works_when_the_schema_is_behind(tmp_path: Path) -> None:
    """Liveness must survive a stale schema so the UI can explain the problem."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="WARNING",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 503


def test_ready_reports_unavailable_when_database_cannot_be_opened(
    tmp_path: Path,
) -> None:
    # The database file lives in a directory that does not exist, so opening it
    # fails like a missing/locked database would in production.
    missing_parent = tmp_path / "missing" / "nested" / "tracker.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=f"sqlite+pysqlite:///{missing_parent.as_posix()}",
        log_level="WARNING",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "error"},
    }


def test_health_still_works_when_readiness_fails(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=(
            f"sqlite+pysqlite:///{(tmp_path / 'missing' / 'tracker.db').as_posix()}"
        ),
        log_level="WARNING",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 503
