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
from sqlalchemy import (Column, DefaultClause, ForeignKeyConstraint, Integer,
                        MetaData, String, Table, create_engine, inspect, text)
from sqlalchemy.exc import IntegrityError

# Imported for side effects: registering all business tables on shared
# ``Base.metadata`` used as the migration/comparison target.
import data_agent.models.managed_file  # noqa: F401
import data_agent.models.session  # noqa: F401
from data_agent.config import database
from data_agent.config.config import config
from data_agent.models.user import Base

BUSINESS_TABLES = ("users", "sessions", "messages", "managed_files")


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
            "managed_files",
            "alembic_version",
        } <= tables

        assert _column_names(inspector, "users") >= {
            "id",
            "username",
            "email",
            "hashed_password",
            "role",
            "created_at",
            "updated_at",
        }
        role_column = next(
            column
            for column in inspector.get_columns("users")
            if column["name"] == "role"
        )
        assert role_column["nullable"] is False
        assert "user" in str(role_column["default"])
        assert any(
            constraint["name"] == "ck_users_role"
            for constraint in inspector.get_check_constraints("users")
        )
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
        assert _column_names(inspector, "managed_files") >= {
            "id",
            "file_id",
            "user_id",
            "original_name",
            "media_type",
            "size_bytes",
            "sha256",
            "storage_key",
            "created_at",
            "expires_at",
        }

        users_unique = _unique_index_columns(inspector, "users")
        assert ("username",) in users_unique
        assert ("email",) in users_unique
        assert ("session_id",) in _unique_index_columns(
            inspector, "sessions"
        )
        assert ("file_id",) in _unique_index_columns(
            inspector, "managed_files"
        )

        assert (("user_id",), "users", ("id",)) in _foreign_keys(
            inspector, "sessions"
        )
        assert (("session_id",), "sessions", ("id",)) in _foreign_keys(
            inspector, "messages"
        )
        assert (("user_id",), "users", ("id",)) in _foreign_keys(
            inspector, "managed_files"
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


def test_existing_data_is_preserved_and_backfilled(sqlite_url):
    command.upgrade(database._alembic_config(), "4e43e097f22b")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, email, hashed_password) "
                    "VALUES (1, 'existing', 'existing@example.test', 'hash')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, user_id, session_id, title) "
                    "VALUES (1, 1, 'existing-session', 'Existing')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO messages "
                    "(id, session_id, role, content) "
                    "VALUES (1, 1, 'user', 'preserved')"
                )
            )

        _upgrade_to_head()

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT role FROM users WHERE id = 1")
            ).scalar_one() == "user"
            assert connection.execute(
                text("SELECT COUNT(*) FROM sessions")
            ).scalar_one() == 1
            assert connection.execute(
                text("SELECT COUNT(*) FROM messages")
            ).scalar_one() == 1

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(username, email, hashed_password, role) "
                        "VALUES ('invalid', 'invalid@example.test', "
                        "'hash', 'owner')"
                    )
                )
    finally:
        engine.dispose()


def test_role_migration_can_downgrade_without_losing_users(sqlite_url):
    _upgrade_to_head()
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(username, email, hashed_password) "
                    "VALUES ('downgrade', 'downgrade@example.test', 'hash')"
                )
            )

        command.downgrade(database._alembic_config(), "4e43e097f22b")

        assert "role" not in _column_names(inspect(engine), "users")
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM users")
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_managed_file_migration_downgrade_preserves_users(sqlite_url):
    _upgrade_to_head()
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, email, hashed_password, role) "
                    "VALUES (1, 'file-owner', 'owner@example.test', "
                    "'hash', 'user')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO managed_files "
                    "(file_id, user_id, original_name, media_type, "
                    "size_bytes, sha256, storage_key, created_at, expires_at) "
                    "VALUES ('00000000-0000-0000-0000-000000000001', 1, "
                    "'sample.txt', 'text/plain', 1, "
                    f"'{'a' * 64}', '1/sample.txt', "
                    "'2026-01-01 00:00:00', '2026-01-02 00:00:00')"
                )
            )

        command.downgrade(database._alembic_config(), "8f3c1b7a2d4e")

        assert "managed_files" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM users")
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_legacy_unversioned_database_stamps_base_then_upgrades(sqlite_url):
    command.upgrade(database._alembic_config(), "4e43e097f22b")
    engine = create_engine(sqlite_url)
    previous_engine = database._engine
    previous_factory = database._session_factory
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(username, email, hashed_password) "
                    "VALUES ('legacy', 'legacy@example.test', 'hash')"
                )
            )
            connection.execute(text("DROP TABLE alembic_version"))

        database._engine = engine
        database._session_factory = None
        database._prepare_database()

        assert "role" in _column_names(inspect(engine), "users")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT username, role FROM users")
            ).one()
            assert row == ("legacy", "user")
    finally:
        database._engine = previous_engine
        database._session_factory = previous_factory
        engine.dispose()


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


@pytest.mark.parametrize(
    "variant",
    [
        "extra_table", "missing_table", "missing_users", "wrong_type",
        "nullable_password", "unexpected_default", "missing_unique_index",
        "missing_foreign_key", "extra_column", "unexpected_view",
        "unexpected_trigger",
    ],
)
def test_unknown_unversioned_schema_is_rejected_before_any_ddl(
    sqlite_url, tmp_path, monkeypatch, variant,
):
    command.upgrade(database._alembic_config(), "4e43e097f22b")
    source = create_engine(sqlite_url)
    metadata = MetaData()
    metadata.reflect(source)
    metadata.remove(metadata.tables["alembic_version"])
    source.dispose()
    if variant == "extra_table":
        Table("unrecognized", metadata, Column("id", Integer, primary_key=True))
    elif variant == "missing_table":
        metadata.remove(metadata.tables["messages"])
    elif variant == "missing_users":
        # An arbitrary nonempty database without users must not be mistaken
        # for a brand-new database.
        metadata = MetaData()
        Table("unrecognized", metadata, Column("id", Integer, primary_key=True))
    elif variant == "wrong_type":
        metadata.tables["users"].c.username.type = String(51)
    elif variant == "nullable_password":
        metadata.tables["users"].c.hashed_password.nullable = True
    elif variant == "unexpected_default":
        metadata.tables["users"].c.hashed_password.server_default = DefaultClause("x")
    elif variant == "missing_unique_index":
        users = metadata.tables["users"]
        users.indexes = {
            index for index in users.indexes
            if tuple(index.columns.keys()) != ("email",)
        }
    elif variant == "missing_foreign_key":
        messages = metadata.tables["messages"]
        messages.constraints = {
            c for c in messages.constraints if not isinstance(c, ForeignKeyConstraint)
        }
    elif variant == "extra_column":
        metadata.tables["users"].append_column(Column("unrecognized", String(20)))
    target_url = f"sqlite:///{(tmp_path / 'unknown.db').as_posix()}"
    engine = create_engine(target_url)
    metadata.create_all(engine)
    if variant == "unexpected_view":
        with engine.begin() as connection:
            connection.execute(text("CREATE VIEW unexpected AS SELECT id FROM users"))
    elif variant == "unexpected_trigger":
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TRIGGER unexpected AFTER INSERT ON users "
                "BEGIN UPDATE users SET email = 'changed@example.test' "
                "WHERE id = NEW.id; END"
            ))
    monkeypatch.setattr(config, "DATABASE_URL", target_url)
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(database, "_session_factory", None)

    def snapshot():
        with engine.connect() as connection:
            return connection.execute(text(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            )).all()

    before = snapshot()
    try:
        with pytest.raises(RuntimeError, match="database_schema_unknown"):
            database._prepare_database()
        assert snapshot() == before
        assert "alembic_version" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision", ["", "unrecognized", "b6f4e8c2a9d1"])
def test_version_label_does_not_bypass_schema_validation(
    sqlite_url, monkeypatch, revision,
):
    engine = create_engine(sqlite_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        ))
        if revision:
            connection.execute(
                text("INSERT INTO alembic_version VALUES (:revision)"),
                {"revision": revision},
            )
    monkeypatch.setattr(database, "_engine", engine)
    try:
        before = _schema_snapshot(engine)
        with pytest.raises(RuntimeError, match="database_schema_unknown"):
            database._prepare_database()
        assert _schema_snapshot(engine) == before
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all() == ([revision] if revision else [])
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision", ["4e43e097f22b", "8f3c1b7a2d4e", "head"])
def test_known_versioned_schema_can_initialize_without_losing_data(
    sqlite_url, monkeypatch, revision,
):
    command.upgrade(database._alembic_config(), revision)
    engine = create_engine(sqlite_url)
    monkeypatch.setattr(database, "_engine", engine)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, username, email, hashed_password) "
                "VALUES (1, 'canary', 'canary@example.test', 'offline-hash')"
            ))
        database._prepare_database()
        database.run_migrations()
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT username, email, hashed_password, role FROM users"
            )).all() == [
                ("canary", "canary@example.test", "offline-hash", "user"),
            ]
            assert connection.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalars().all() == ["b6f4e8c2a9d1"]
    finally:
        engine.dispose()
