"""Liveness endpoint tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "Tracker",
        "version": __version__,
        "environment": "test",
    }


def test_health_works_without_the_database(app: FastAPI) -> None:
    """Liveness must work even if the database cannot be opened."""
    # No lifespan is run here on purpose: the process is alive regardless.
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_exposes_cors_for_the_vite_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
