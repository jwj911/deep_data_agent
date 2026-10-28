"""Read-only schema checks before any startup migration writes."""

import re
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import Dialect


class UnknownDatabaseSchemaError(RuntimeError):
    """The database cannot safely be identified as a known migration revision."""

    def __init__(self) -> None:
        super().__init__("database_schema_unknown")


def _expression(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    # Normalize dialect quoting/parentheses while preserving literal contents:
    # 'ad min' and 'admin', or 'USER' and 'user', must remain different.
    expression = re.sub(r"_utf8mb4(?=')", "", str(value))
    tokens = re.findall(
        r"'(?:''|[^'])*'|[A-Za-z_][A-Za-z_0-9]*|\d+|[=<>!,+*/%-]",
        expression,
    )
    return tuple(t if t.startswith("'") else t.lower() for t in tokens)


def _has_triggers(engine: Engine) -> bool:
    if engine.dialect.name == "sqlite":
        query = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'"
    elif engine.dialect.name == "mysql":
        query = (
            "SELECT COUNT(*) FROM information_schema.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = DATABASE()"
        )
    else:
        raise UnknownDatabaseSchemaError()
    with engine.connect() as connection:
        return bool(connection.execute(text(query)).scalar_one())


def _signature(engine: Engine, dialect: Dialect, *, unversioned: bool):
    inspector = inspect(engine)
    if inspector.get_view_names() or _has_triggers(engine):
        raise UnknownDatabaseSchemaError()
    tables = set(inspector.get_table_names())
    if unversioned:
        tables.discard("alembic_version")
    signature = {}
    for name in sorted(tables):
        if engine.dialect.name == "mysql":
            options = inspector.get_table_options(name)
            if str(options.get("mysql_engine", "")).lower() != "innodb":
                raise UnknownDatabaseSchemaError()
        columns = []
        for column in inspector.get_columns(name):
            compiled_type = str(column["type"].compile(dialect=dialect)).upper()
            columns.append((
                column["name"], compiled_type,
                bool(column["nullable"]), _expression(column.get("default")),
            ))
            if (
                engine.dialect.name == "mysql"
                and column["name"] == "id"
                and name != "alembic_version"
                and column.get("autoincrement") is not True
            ):
                raise UnknownDatabaseSchemaError()
        foreign_keys = set()
        automatic_indexes = set()
        for fk in inspector.get_foreign_keys(name):
            constrained = tuple(fk["constrained_columns"])
            schema = fk.get("referred_schema")
            if schema == inspector.default_schema_name:
                schema = None
            options = {
                key: value for key, value in (fk.get("options") or {}).items()
                if value is not None and not (
                    key in {"ondelete", "onupdate"}
                    and str(value).upper() in {"RESTRICT", "NO ACTION"}
                )
            }
            foreign_keys.add((
                constrained, schema, fk["referred_table"],
                tuple(fk["referred_columns"]), tuple(sorted(options.items())),
            ))
            automatic_indexes.add((constrained, False))
        indexes = set()
        for index in inspector.get_indexes(name):
            if any((index.get("dialect_options") or {}).values()):
                raise UnknownDatabaseSchemaError()
            indexes.add((
                tuple(index["column_names"]), bool(index["unique"]),
            ))
        indexes.update(
            (tuple(c["column_names"]), True)
            for c in inspector.get_unique_constraints(name)
        )
        # InnoDB creates these supporting indexes for foreign keys. SQLite
        # does not; do not confuse a dialect artifact with a schema change.
        if dialect.name == "mysql":
            indexes -= automatic_indexes
        signature[name] = (
            tuple(sorted(columns)),
            tuple(inspector.get_pk_constraint(name)["constrained_columns"]),
            frozenset(indexes),
            frozenset(foreign_keys),
            frozenset(
                _expression(c["sqltext"])
                for c in inspector.get_check_constraints(name)
            ),
        )
    return signature


def ensure_revision_schema(
    engine: Engine,
    alembic_config: AlembicConfig,
    revision: str,
    *,
    unversioned: bool = False,
) -> None:
    """Compare against actual migration assets without writing to the target."""
    reference = create_engine("sqlite://")
    try:
        with reference.connect() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, revision)
        expected = _signature(
            reference, engine.dialect, unversioned=unversioned,
        )
        actual = _signature(
            engine, engine.dialect, unversioned=unversioned,
        )
        if actual != expected:
            raise UnknownDatabaseSchemaError()
    except UnknownDatabaseSchemaError:
        raise
    except Exception as exc:
        raise UnknownDatabaseSchemaError() from exc
    finally:
        alembic_config.attributes.pop("connection", None)
        reference.dispose()
