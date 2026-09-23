"""Run the backend development server: ``python -m app [--reload]``.

Passing ``log_config=None`` to uvicorn keeps the application's own logging
configuration in charge, so uvicorn and application log lines share one format.
"""

from __future__ import annotations

import argparse

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        prog="python -m app", description="Run the Tracker backend server."
    )
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server when source files change (development only).",
    )
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
