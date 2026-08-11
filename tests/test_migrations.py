"""Deterministic migration tests.

These tests never touch a real MySQL/Redis instance. They drive Alembic
against throwaway SQLite files under ``tmp_path`` and compare the resulting
schema against the shared ``Base.metadata`` that the ORM models register.

The application resolves the migration database URL from
``data_agent.config.database._database_url()``, which reads the single
``config.DATABASE_URL`` instance attribute at call time. ``migrations/env.py``
uses the same helper, so patching ``config.DATABASE_URL`` to a temporary
SQLite file redirects both the programmatic Alembic config and env.py to the
throwaway database without reloading any modules.
"""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

# Imported for its side effect: registering the Session and Message tables on
# the shared ``Base.metadata`` used as the migration/comparison target.
import data_agent.models.session  # noqa: F401
from data_agent.config import database
from data_agent.config.config import config
from data_agent.models.user import Base

BUSINESS_TABLES = ("users", "sessions", "messages")


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch):
    """Point the app/migration URL at a fresh throwaway SQLite file."""
    db_file = tmp_path / "migrated.db"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(config, "DATABASE_URL", url)
    return url


def _upgrade_to_head() -> None:
    command.upgrade(database._alembic_config(), "head")


def _column_names(inspector, table) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _unique_index_columns(inspector, table) -> set[tuple[str, ...]]:
    return {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table)
        if index["unique"]
    }


def _foreign_keys(inspector, table) -> set[tuple]:
    return {
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            tuple(fk["referred_columns"]),
        )
        for fk in inspector.get_foreign_keys(table)
    }


def _schema_snapshot(engine) -> dict[str, dict]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    return {
        "tables": tables,
        "columns": {
            table: _column_names(inspector, table) for table in tables
        },
        "unique_indexes": {
            table: _unique_index_columns(inspector, table)
            for table in tables
        },
        "foreign_keys": {
            table: _foreign_keys(inspector, table) for table in tables
        },
    }


def test_upgrade_head_builds_expected_schema(sqlite_url):
    _upgrade_to_head()

    engine = create_engine(sqlite_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        assert {
            "users",
            "sessions",
            "messages",
            "alembic_version",
        } <= tables

        assert _column_names(inspector, "users") >= {
            "id",
            "username",
            "email",
            "hashed_password",
            "created_at",
            "updated_at",
        }
        assert _column_names(inspector, "sessions") >= {
            "id",
            "user_id",
            "session_id",
            "title",
            "created_at",
            "updated_at",
        }
        assert _column_names(inspector, "messages") >= {
            "id",
            "session_id",
            "role",
            "content",
            "created_at",
        }

        users_unique = _unique_index_columns(inspector, "users")
        assert ("username",) in users_unique
        assert ("email",) in users_unique
        assert ("session_id",) in _unique_index_columns(
            inspector, "sessions"
        )

        assert (("user_id",), "users", ("id",)) in _foreign_keys(
            inspector, "sessions"
        )
        assert (("session_id",), "sessions", ("id",)) in _foreign_keys(
            inspector, "messages"
        )
    finally:
        engine.dispose()


def test_migration_schema_matches_model_metadata(sqlite_url, tmp_path):
    _upgrade_to_head()
    migrated_engine = create_engine(sqlite_url)

    created_file = tmp_path / "created.db"
    created_engine = create_engine(f"sqlite:///{created_file.as_posix()}")
    Base.metadata.create_all(created_engine)

    try:
        migrated = _schema_snapshot(migrated_engine)
        created = _schema_snapshot(created_engine)
    finally:
        migrated_engine.dispose()
        created_engine.dispose()

    assert migrated["tables"] == set(BUSINESS_TABLES)
    assert migrated["tables"] == created["tables"]
    assert migrated["columns"] == created["columns"]
    assert migrated["unique_indexes"] == created["unique_indexes"]
    assert migrated["foreign_keys"] == created["foreign_keys"]


def test_migration_head_is_unique(sqlite_url):
    heads = ScriptDirectory.from_config(
        database._alembic_config()
    ).get_heads()

    assert len(heads) == 1


def test_no_drift_between_metadata_and_migrations(sqlite_url):
    _upgrade_to_head()

    engine = create_engine(sqlite_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "render_as_batch": True},
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    # compare_metadata was empirically verified to return an empty diff on
    # SQLite for this baseline (no server_default/type noise), so any entry
    # here signals a real drift between the ORM models and the migration.
    assert diff == []
