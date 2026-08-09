from threading import RLock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from data_agent.config.config import config
from data_agent.models.session import Message, Session
from data_agent.models.user import Base

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


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=get_engine())
