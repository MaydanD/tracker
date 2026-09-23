"""Typed application configuration.

Settings are read from the process environment using the ``TRACKER_`` prefix,
optionally seeded by a ``.env`` file (``backend/.env`` first, then ``.env`` in
the current working directory — the latter wins).

Unrecognised variables are ignored rather than fatal (a shared ``.env`` file may
contain another tool's keys), but ``unknown_environment_variables()`` reports
typo'd ``TRACKER_*`` names so the app can warn about them at startup instead of
silently falling back to a default.

There is deliberately no secret management here: Tracker is a local,
single-user desktop application.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__
from app.core.paths import (
    database_file,
    default_data_dir,
    ensure_data_dir,
    sqlite_url_for_path,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Application configuration (environment prefix: ``TRACKER_``)."""

    model_config = SettingsConfigDict(
        env_prefix="TRACKER_",
        env_file=(BACKEND_DIR / ".env", Path(".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Tracker"
    app_version: str = __version__
    app_env: Environment = "development"

    # HTTP server
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = "/api"

    # Development convenience: Vite serves the SPA on this origin and proxies
    # /api to the backend, so CORS is only needed for direct cross-origin calls.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS)
    )

    # Storage
    data_dir: Path | None = None
    database_url: str | None = None
    # Reserved for the portable Windows build (data next to the executable).
    portable: bool = False

    # Logging
    log_level: str = "INFO"

    # -- validation ---------------------------------------------------------

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            level = value.strip().upper()
            if level not in VALID_LOG_LEVELS:
                raise ValueError(
                    f"log_level must be one of {sorted(VALID_LOG_LEVELS)}"
                )
            return level
        return value

    @field_validator("api_prefix")
    @classmethod
    def _normalise_api_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not prefix.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return prefix.rstrip("/") or "/api"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        # Accept a comma-separated string (comfortable in a .env file) as well
        # as a real list. NoDecode stops pydantic-settings from demanding JSON.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # -- resolved locations -------------------------------------------------

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def resolved_data_dir(self) -> Path:
        """Absolute directory for runtime data."""
        return resolve_data_dir_for(self)

    @property
    def resolved_database_path(self) -> Path:
        """Absolute path of the SQLite database file."""
        return database_file(self.resolved_data_dir)

    @property
    def resolved_database_url(self) -> str:
        """SQLAlchemy URL: an explicit override wins, otherwise the data dir wins."""
        if self.database_url:
            return self.database_url
        return sqlite_url_for_path(self.resolved_database_path)

    def ensure_directories(self) -> Path:
        """Create the runtime data directory if it does not exist yet."""
        return ensure_data_dir(self.resolved_data_dir)


def resolve_data_dir_for(settings: Settings) -> Path:
    """Resolve the data directory without importing settings back into paths.py."""
    if settings.data_dir is not None:
        return Path(settings.data_dir).expanduser().resolve()
    return default_data_dir(portable=settings.portable)


def known_environment_variable_names() -> set[str]:
    """Environment variable names that map to a setting."""
    return {f"TRACKER_{name.upper()}" for name in Settings.model_fields}


def unknown_environment_variables() -> list[str]:
    """``TRACKER_*`` process variables that do not correspond to any setting.

    Almost always a typo (``TRACKER_LOG_LEVL``), which would otherwise be
    silently ignored and quietly fall back to the default value.
    """
    known = known_environment_variable_names()
    return sorted(
        name
        for name in os.environ
        if name.upper().startswith("TRACKER_") and name.upper() not in known
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings used by the app factory and Alembic.

    Tests build ``Settings(...)`` instances directly so that the cache never
    leaks configuration between test cases.
    """
    return Settings()
