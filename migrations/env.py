"""Alembic environment for Deep Data Agent.

This environment reuses the application configuration and the shared
SQLAlchemy ``Base.metadata`` so migrations stay aligned with the ORM models.

Notes
-----
* ``logging.config.fileConfig`` is intentionally NOT called here. Doing so
  would reconfigure the root logger and override the structured logging set up
  in ``data_agent.config.logger``. Alembic still logs through its own module
  loggers without any extra configuration.
* The database URL is taken from ``data_agent.config.database._database_url``
  so a single source of truth (``DATABASE_URL``) drives both the app and
  migrations. Nothing is hard-coded in ``alembic.ini``.
* ``render_as_batch=True`` enables batch operations so ``ALTER`` statements
  work on SQLite, and ``compare_type=True`` lets autogenerate detect column
  type changes.
"""
from alembic import context
from sqlalchemy import create_engine

# ``data_agent.models.session`` is imported for its side effects only:
# importing it registers the Session and Message tables on the shared
# ``Base.metadata`` used as ``target_metadata`` below.
import data_agent.models.session  # noqa: F401
from data_agent.config.database import _database_url
from data_agent.models.user import Base

# The Alembic Config object provides access to values within alembic.ini.
config = context.config

# Shared metadata for autogenerate support and offline rendering.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configure the context with just a URL and emit SQL to the script output
    instead of connecting to a database.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Create an engine from the application database URL and associate a live
    connection with the migration context.
    """
    connectable = create_engine(_database_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
