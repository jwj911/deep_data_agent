from pathlib import Path
from threading import RLock

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from data_agent.config.config import config
from data_agent.config.schema_contract import (UnknownDatabaseSchemaError,
                                               ensure_revision_schema)
from data_agent.models.managed_file import ManagedFile  # noqa: F401
from data_agent.models.session import Message, Session
from data_agent.models.user import Base

# alembic.ini and the migrations/ directory live at the project root, two
# levels above this file (data_agent/config/database.py). Resolving the paths
# from __file__ keeps migrations working regardless of the process cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations"
_LEGACY_SCHEMA_REVISION = "4e43e097f22b"

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
    _prepare_database()


def _prepare_database() -> None:
    """Identify the complete schema before any startup stamp or DDL."""
    with _database_lock:
        alembic_cfg = _alembic_config()
        engine = get_engine()
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if inspector.get_view_names():
            raise UnknownDatabaseSchemaError()
        if "alembic_version" in tables:
            try:
                with engine.connect() as connection:
                    revisions = connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalars().all()
                known = {
                    rev.revision
                    for rev in ScriptDirectory.from_config(
                        alembic_cfg
                    ).walk_revisions()
                }
                if len(revisions) != 1 or revisions[0] not in known:
                    raise UnknownDatabaseSchemaError()
            except UnknownDatabaseSchemaError:
                raise
            except Exception as exc:
                raise UnknownDatabaseSchemaError() from exc
            ensure_revision_schema(engine, alembic_cfg, revisions[0])
        elif tables:
            ensure_revision_schema(
                engine, alembic_cfg, _LEGACY_SCHEMA_REVISION,
                unversioned=True,
            )
            command.stamp(alembic_cfg, _LEGACY_SCHEMA_REVISION)
        command.upgrade(alembic_cfg, "head")


def init_db():
    """Initialize the database by running versioned migrations to head."""
    _prepare_database()
