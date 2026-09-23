"""Alembic environment.

The target database is resolved from the application's own settings so that
migrations always land in the same place the application uses:

1. ``alembic -x db_url=...`` (highest priority, also used by the test suite);
2. ``sqlalchemy.url`` in alembic.ini;
3. application settings — ``TRACKER_DATABASE_URL``, else ``<data dir>/tracker.db``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.core.paths import ensure_data_dir
from app.db.base import Base
from app.db.database import create_db_engine

# Importing the models package registers every table on Base.metadata.
from app.db import models  # noqa: F401  (side-effect import)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def resolve_database_url() -> str:
    """Determine which database this migration run targets."""
    x_arguments = context.get_x_argument(as_dictionary=True)
    if x_arguments.get("db_url"):
        return x_arguments["db_url"]

    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured:
        return configured

    settings = get_settings()
    # SQLite cannot create a database file inside a missing directory.
    ensure_data_dir(settings.resolved_data_dir)
    return settings.resolved_database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it against a database."""
    context.configure(
        url=resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the resolved database."""
    connectable = create_db_engine(resolve_database_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite cannot ALTER most columns; batch mode recreates the table
            # instead, which keeps future migrations possible on this database.
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
