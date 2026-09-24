"""Filesystem location strategy for Tracker.

Runtime data (the SQLite database and, in later stages, backups) must live in a
deterministic place that is *not* mixed into the source tree and that survives
being packaged into a Windows executable.

Resolution order for the data directory:

1. an explicit override (``Settings.data_dir`` / ``TRACKER_DATA_DIR``);
2. a frozen (PyInstaller) build: next to the executable when running in
   portable mode, otherwise the per-user application data directory;
3. development: ``<repository root>/.data``, which is git-ignored.

All of that logic lives here so the Stage 12 desktop packaging work only has to
touch this module instead of the rest of the application.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DATABASE_FILENAME = "tracker.db"
BACKUPS_DIRECTORY_NAME = "backups"
APP_DIRECTORY_NAME = "Tracker"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle (desktop build)."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Repository root, derived from this file's position (backend/app/core/paths.py)."""
    return Path(__file__).resolve().parents[3]


def executable_dir() -> Path:
    """Directory containing the running executable (meaningful only when frozen)."""
    return Path(sys.executable).resolve().parent


def user_data_dir() -> Path:
    """Per-user application data directory (``%LOCALAPPDATA%\\Tracker`` on Windows)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_DIRECTORY_NAME
    return Path.home() / f".{APP_DIRECTORY_NAME.lower()}"


def default_data_dir(*, portable: bool = False) -> Path:
    """Default data directory for the current run mode."""
    if is_frozen():
        # Portable installs keep their data next to the executable so the whole
        # folder can be moved to another machine; normal installs use user data.
        return executable_dir() / "data" if portable else user_data_dir()
    return project_root() / ".data"


def resolve_data_dir(explicit: Path | None = None, *, portable: bool = False) -> Path:
    """Return the data directory to use, honouring an explicit override first."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return default_data_dir(portable=portable)


def ensure_data_dir(path: Path) -> Path:
    """Create the data directory (and parents) if needed and return it."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path)


def database_file(data_dir: Path) -> Path:
    """Absolute path of the SQLite database file inside ``data_dir``."""
    return Path(data_dir) / DATABASE_FILENAME


def backups_dir(data_dir: Path) -> Path:
    """Directory holding automatic backups, kept separate from the database.

    Mixing backups into the same folder as ``tracker.db`` would invite treating
    them as one dataset; a dedicated subdirectory also means a future export or
    packaging step has an obvious place to look.
    """
    return Path(data_dir) / BACKUPS_DIRECTORY_NAME


def sqlite_url_for_path(path: Path) -> str:
    """Build a SQLAlchemy SQLite URL for ``path``.

    Forward slashes are used because Python's ``as_posix()`` yields
    ``C:/dir/file.db`` on Windows, which is the form SQLAlchemy documents for
    absolute SQLite paths on that platform.
    """
    return f"sqlite+pysqlite:///{Path(path).expanduser().as_posix()}"
