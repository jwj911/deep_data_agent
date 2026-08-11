from pathlib import Path
from threading import RLock

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from data_agent.config.config import config
from data_agent.models.session import Message, Session
from data_agent.models.user import Base

# alembic.ini and the migrations/ directory live at the project root, two
# levels above this file (data_agent/config/database.py). Resolving the paths
# from __file__ keeps migrations working regardless of the process cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations"

_engine: Engine | None = None
_session_factory: sessionmaker[OrmSession] | None = None
_database_lock = RLock()


def _database_url() -> str:
    """Use the declared PyMySQL driver for legacy mysql:// URLs."""
    if config.DATABASE_URL.startswith("mysql://"):
        return config.DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
    return config.DATABASE_URL


def get_engine() -> Engine:
    """Create the SQLAlchemy engine only when the FastAPI service needs it."""
    global _engine

    if _engine is None:
        with _database_lock:
            if _engine is None:
                _engine = create_engine(_database_url())
    return _engine


def get_session_factory() -> sessionmaker[OrmSession]:
    """Create the session factory lazily with the database engine."""
    global _session_factory

    if _session_factory is None:
        with _database_lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=get_engine(),
                )
    return _session_factory


def get_db():
    """Dependency to get database session"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _alembic_config() -> AlembicConfig:
    """Build an Alembic config bound to the current application database URL.

    The paths are resolved from ``__file__`` and ``script_location`` is set to
    the absolute ``migrations/`` path so migrations run correctly no matter
    what the process working directory is. ``sqlalchemy.url`` is set from the
    single source of truth ``_database_url()``; ``migrations/env.py`` builds its
    own engine from the same helper, so the two stay consistent.
    """
    alembic_cfg = AlembicConfig(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    alembic_cfg.set_main_option("sqlalchemy.url", _database_url())
    return alembic_cfg


def run_migrations() -> None:
    """Upgrade the current application database to the latest migration head.

    This is idempotent: Alembic performs no changes when the database is
    already at head.
    """
    command.upgrade(_alembic_config(), "head")


def _prepare_database() -> None:
    """Prepare the database via versioned migrations.

    Three cases are handled without ever dropping or recreating existing data:

    * Database already tracked by Alembic (``alembic_version`` exists): upgrade
      to head (idempotent when already at head).
    * Legacy database built by the old ``create_all`` path (``users`` exists but
      ``alembic_version`` does not): its structure matches the initial baseline,
      so stamp it to head instead of recreating the tables.
    * Brand-new empty database (neither table exists): upgrade to head to
      create the schema.
    """
    alembic_cfg = _alembic_config()
    tables = set(inspect(get_engine()).get_table_names())
    has_version = "alembic_version" in tables
    has_business = "users" in tables

    if has_business and not has_version:
        command.stamp(alembic_cfg, "head")
    else:
        command.upgrade(alembic_cfg, "head")


def init_db():
    """Initialize the database by running versioned migrations to head."""
    _prepare_database()
