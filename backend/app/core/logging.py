"""Conventional logging setup.

Deliberately small: one stream handler on the root logger with a readable
format. No JSON logging, no log shipping, no metrics stack — Tracker runs on a
single user's desktop.
"""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Chatty libraries that should not flood the console at INFO.
_NOISY_LOGGERS = ("sqlalchemy.engine", "alembic.runtime.migration")


def configure_logging(level: str = "INFO", *, database_echo: bool = False) -> None:
    """Configure root logging for the application process.

    Safe to call more than once (for example from tests).
    """
    numeric_level = logging.getLevelName(level.strip().upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Replace handlers we installed previously so repeated calls stay idempotent
    # while leaving handlers owned by other tools (pytest, uvicorn) alone.
    for handler in list(root.handlers):
        if getattr(handler, "_tracker_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler._tracker_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    if database_echo:
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)
    else:
        # Keep SQL statement logging quiet unless the user asked for DEBUG.
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(
                logging.INFO if numeric_level <= logging.DEBUG else logging.WARNING
            )


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (thin wrapper to keep imports uniform)."""
    return logging.getLogger(name)
