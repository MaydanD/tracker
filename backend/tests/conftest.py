"""Shared test fixtures.

Every test runs against its own temporary data directory and SQLite file, so the
developer's real ``.data/tracker.db`` is never opened, migrated or modified.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import today_local
from app.db.database import Database, create_database
from app.main import create_app
from tests.helpers import FrozenClock, run_migrations


@pytest.fixture(autouse=True)
def clean_tracker_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient TRACKER_* variables so tests are deterministic."""
    for name in list(os.environ):
        if name.startswith("TRACKER_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Isolated application settings (temp data dir, never a developer .env)."""
    return Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="WARNING",
    )


@pytest.fixture()
def migrated_settings(settings: Settings) -> Settings:
    """Settings whose database has been created and migrated to head."""
    settings.ensure_directories()
    run_migrations(settings.resolved_database_url)
    return settings


@pytest.fixture()
def database(migrated_settings: Settings) -> Iterator[Database]:
    """Database container bound to the migrated temporary database."""
    db = create_database(migrated_settings)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture()
def session(database: Database) -> Iterator[Session]:
    """A session against the migrated temporary database."""
    with database.session() as db_session:
        yield db_session


@pytest.fixture()
def frozen_clock() -> FrozenClock:
    """The clock the default ``app`` fixture injects.

    Frozen on the machine's local date because habits are created with that as
    their first configuration date; calendar rules can then be exercised against
    explicit dates instead of whatever "now" happens to be.
    """
    return FrozenClock(today_local())


@pytest.fixture()
def app(migrated_settings: Settings, frozen_clock: FrozenClock) -> FastAPI:
    """Application instance under test, with a deterministic clock."""
    return create_app(migrated_settings, clock=frozen_clock)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    """Test client with lifespan events executed."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def health_area(client: TestClient) -> dict[str, Any]:
    """An active 'Health' area, created through the API."""
    response = client.post("/api/areas", json={"name": "Health", "color": "#2f9e5f"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def other_area(client: TestClient) -> dict[str, Any]:
    """A second active area, created through the API."""
    response = client.post(
        "/api/areas", json={"name": "Development", "color": "#4a7cc7"}
    )
    assert response.status_code == 201, response.text
    return response.json()
