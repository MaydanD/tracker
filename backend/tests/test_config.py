"""Configuration tests: defaults, overrides, and the settings that break easily."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app import __version__
from app.core import config, paths
from app.core.config import DEFAULT_CORS_ORIGINS, Settings


def build_settings(**overrides: object) -> Settings:
    """Settings that ignore any developer .env file on disk."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults_are_development_friendly() -> None:
    settings = build_settings()

    assert settings.app_name == "Tracker"
    assert settings.app_version == __version__
    assert settings.app_env == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.api_prefix == "/api"
    assert settings.log_level == "INFO"
    assert settings.portable is False
    assert settings.data_dir is None
    assert settings.database_url is None
    assert settings.cors_origins == list(DEFAULT_CORS_ORIGINS)


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom_dir = tmp_path / "custom-data"
    monkeypatch.setenv("TRACKER_APP_ENV", "production")
    monkeypatch.setenv("TRACKER_PORT", "8123")
    monkeypatch.setenv("TRACKER_LOG_LEVEL", "debug")
    monkeypatch.setenv("TRACKER_DATA_DIR", str(custom_dir))

    settings = build_settings()

    assert settings.app_env == "production"
    assert settings.port == 8123
    assert settings.log_level == "DEBUG"  # normalised
    assert settings.resolved_data_dir == custom_dir.resolve()
    assert settings.is_development is False


def test_data_dir_derives_a_deterministic_sqlite_url(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    settings = build_settings(data_dir=data_dir)

    expected_path = data_dir.resolve() / "tracker.db"

    assert settings.resolved_data_dir == data_dir.resolve()
    assert settings.resolved_database_path == expected_path
    assert settings.resolved_database_url == (
        f"sqlite+pysqlite:///{expected_path.as_posix()}"
    )
    # Forward slashes keep the URL valid on Windows.
    assert "\\" not in settings.resolved_database_url


def test_relative_data_dir_is_absolutised(tmp_path: Path) -> None:
    settings = build_settings(data_dir=Path("relative-data"))

    assert settings.resolved_data_dir.is_absolute()


def test_explicit_database_url_wins_over_data_dir(tmp_path: Path) -> None:
    settings = build_settings(
        data_dir=tmp_path / "data", database_url="sqlite+pysqlite:///:memory:"
    )

    assert settings.resolved_database_url == "sqlite+pysqlite:///:memory:"


def test_cors_origins_accept_a_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TRACKER_CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173 ,"
    )

    assert build_settings().cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_empty_cors_origins_disable_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKER_CORS_ORIGINS", "")

    assert build_settings().cors_origins == []


def test_api_prefix_is_normalised_and_validated() -> None:
    assert build_settings(api_prefix="/api/").api_prefix == "/api"

    with pytest.raises(ValidationError):
        build_settings(api_prefix="api")


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(log_level="chatty")


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(app_env="staging")


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(port=70000)


def test_unknown_prefixed_variable_is_ignored_but_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACKER_LOG_LEVL", "DEBUG")  # typo

    # Unknown variables never break startup ...
    assert build_settings().log_level == "INFO"
    # ... but they are surfaced so the typo is visible in the startup log.
    assert config.unknown_environment_variables() == ["TRACKER_LOG_LEVL"]


def test_known_variables_are_not_reported_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACKER_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SOME_OTHER_TOOL", "1")

    assert config.unknown_environment_variables() == []


def test_dotenv_file_is_read_and_unrelated_keys_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SOME_OTHER_TOOL=1\nTRACKER_PORT=9001\nTRACKER_LOG_LEVEL=warning\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)  # type: ignore[arg-type]

    assert settings.port == 9001
    assert settings.log_level == "WARNING"


def test_development_data_dir_is_next_to_the_repository() -> None:
    assert paths.default_data_dir() == paths.project_root() / ".data"


def test_frozen_build_uses_user_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))

    assert paths.default_data_dir() == tmp_path / "AppData" / "Tracker"


def test_frozen_portable_build_keeps_data_next_to_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)

    assert paths.default_data_dir(portable=True) == tmp_path / "data"
