"""Verify migration refusal and preservation against a private MySQL instance."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _docker(*args, env=None):
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, env=env, timeout=90,
    )
    if result.returncode:
        raise RuntimeError("mysql_control_container_command_failed")
    return result.stdout.strip()


def verify(url: str) -> dict:
    """Only accept a disposable server with no existing application databases."""
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LOG_FILE_PATH"] = ""
    logging.disable(logging.CRITICAL)
    from alembic import command
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url

    from data_agent.config import database
    from data_agent.config.config import config
    from data_agent.config.schema_contract import (UnknownDatabaseSchemaError,
                                                   _signature)

    address = make_url(url)
    if address.database:
        raise RuntimeError("mysql_control_requires_database_free_url")
    admin = create_engine(address)
    deadline = time.monotonic() + 75
    while True:
        try:
            with admin.connect() as connection:
                existing = set(connection.execute(text("SHOW DATABASES")).scalars())
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("mysql_control_startup_timeout") from None
            time.sleep(0.25)
    if existing - {"mysql", "sys", "information_schema", "performance_schema"}:
        raise RuntimeError("mysql_control_server_is_not_empty")
    previous = (config.DATABASE_URL, database._engine, database._session_factory)
    cases = []

    def setup(revision=None):
        name = "dda_schema_" + secrets.token_hex(8)
        with admin.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{name}`"))
        config.DATABASE_URL = address.set(database=name).render_as_string(
            hide_password=False,
        )
        engine = create_engine(config.DATABASE_URL)
        database._engine = engine
        database._session_factory = None
        if revision:
            command.upgrade(database._alembic_config(), revision)
        return engine

    def seed(engine):
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, username, email, hashed_password) "
                "VALUES (1, 'schema-canary', 'schema@example.invalid', 'offline-hash')"
            ))
            connection.execute(text(
                "INSERT INTO sessions (id,user_id,session_id,title) "
                "VALUES (1,1,'schema-canary','preserved')"
            ))
            connection.execute(text(
                "INSERT INTO messages (id,session_id,role,content) "
                "VALUES (1,1,'user','offline-canary')"
            ))

    def rows(engine):
        with engine.connect() as connection:
            return [
                connection.execute(text(f"SELECT * FROM `{table}` ORDER BY id")).all()
                for table in ("users", "sessions", "messages")
                if table in inspect(engine).get_table_names()
            ]

    def snapshot(engine):
        with engine.connect() as connection:
            objects = connection.execute(text(
                "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"
            )).all()
            ddl = [
                tuple(connection.execute(text(f"SHOW CREATE TABLE `{name}`")).one())
                for name, _kind in objects
            ]
            triggers = connection.execute(text(
                "SELECT TRIGGER_NAME,ACTION_STATEMENT FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA=DATABASE() ORDER BY TRIGGER_NAME"
            )).all()
            revision = (
                connection.execute(text("SELECT * FROM alembic_version")).all()
                if "alembic_version" in dict(objects) else []
            )
            return ddl, triggers, revision, rows(engine)

    try:
        engine = setup()
        database.init_db()
        database.run_migrations()
        cases.append("empty")
        engine.dispose()
        for revision in ("4e43e097f22b", "8f3c1b7a2d4e", "head", "unversioned"):
            engine = setup("4e43e097f22b" if revision == "unversioned" else revision)
            seed(engine)
            before = rows(engine)
            if revision == "unversioned":
                with engine.begin() as connection:
                    connection.execute(text("DROP TABLE alembic_version"))
            database.init_db()
            database.run_migrations()
            after = rows(engine)
            assert len(before) == len(after) == 3
            # The role migration appends one server-owned default to users.
            assert tuple(after[0][0][:4]) == tuple(before[0][0][:4])
            assert after[1:] == before[1:]
            with engine.connect() as connection:
                assert connection.execute(text("SELECT role FROM users")).scalar_one() == "user"
            cases.append(revision)
            engine.dispose()

        mutations = {
            "extra_table": "CREATE TABLE unexpected (id INT PRIMARY KEY)",
            "missing_table": "DROP TABLE messages",
            "wrong_type": "ALTER TABLE users MODIFY username VARCHAR(51) NOT NULL",
            "nullable_password": "ALTER TABLE users MODIFY hashed_password VARCHAR(255) NULL",
            "unexpected_default": "ALTER TABLE users ALTER hashed_password SET DEFAULT 'x'",
            "missing_unique_index": "ALTER TABLE users DROP INDEX ix_users_email",
            "extra_column": "ALTER TABLE users ADD unexpected VARCHAR(20)",
            "unexpected_view": "CREATE VIEW unexpected AS SELECT id FROM users",
            "unexpected_trigger": (
                "CREATE TRIGGER unexpected BEFORE INSERT ON users FOR EACH ROW "
                "SET NEW.email = 'changed@example.invalid'"
            ),
            "nontransactional_table": "ALTER TABLE messages ENGINE=MyISAM",
            "missing_autoincrement": "ALTER TABLE messages MODIFY id INTEGER NOT NULL",
        }
        for label in (*mutations, "missing_foreign_key", "empty_revision",
                      "unknown_revision", "forged_head"):
            engine = setup("4e43e097f22b")
            seed(engine)
            with engine.begin() as connection:
                if label in ("empty_revision", "unknown_revision", "forged_head"):
                    connection.execute(text("DELETE FROM alembic_version"))
                    if label != "empty_revision":
                        connection.execute(
                            text("INSERT INTO alembic_version VALUES (:revision)"),
                            {"revision": "unknown" if label == "unknown_revision" else "b6f4e8c2a9d1"},
                        )
                else:
                    connection.execute(text("DROP TABLE alembic_version"))
                    if label in ("missing_foreign_key", "nontransactional_table"):
                        fk = inspect(engine).get_foreign_keys("messages")[0]["name"]
                        connection.execute(text(f"ALTER TABLE messages DROP FOREIGN KEY `{fk}`"))
                    if label != "missing_foreign_key":
                        connection.execute(text(mutations[label]))
            before = snapshot(engine)
            try:
                database.init_db()
            except UnknownDatabaseSchemaError:
                pass
            else:
                raise RuntimeError("mysql_control_refusal_missing_" + label)
            assert snapshot(engine) == before, label
            cases.append(label)
            engine.dispose()
        return {"gate": "mysql_schema", "passed": len(cases), "cases": cases}
    except Exception:
        # Safe schema diagnostics contain no URLs, passwords or canary rows.
        try:
            print(json.dumps({
                "diagnostic": "schema_signature",
                "actual": repr(_signature(database._engine, database._engine.dialect, unversioned=False)),
            }), file=sys.stderr)
        except Exception:
            pass
        raise
    finally:
        config.DATABASE_URL, database._engine, database._session_factory = previous
        admin.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="mysql:8.4")
    args = parser.parse_args()
    container_id = None
    try:
        password = secrets.token_hex(24)
        child_env = dict(os.environ, MYSQL_ROOT_PASSWORD=password)
        container_id = _docker(
            "run", "-d", "--pull=never", "--label", "dda.gate=mysql-schema",
            "--tmpfs", "/var/lib/mysql:rw,size=768m",
            "-p", "127.0.0.1::3306", "-e", "MYSQL_ROOT_PASSWORD",
            args.image, env=child_env,
        )
        port = json.loads(_docker("inspect", container_id))[0][
            "NetworkSettings"
        ]["Ports"]["3306/tcp"][0]["HostPort"]
        result = verify(f"mysql+pymysql://root:{password}@127.0.0.1:{port}")
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"gate": "mysql_schema", "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        if container_id:
            _docker("rm", "-f", container_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
