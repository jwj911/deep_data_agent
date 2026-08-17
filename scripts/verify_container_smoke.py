"""Verify the release Compose topology without external service calls."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib import error, parse, request

SERVICES = ("mysql", "redis", "fastapi", "langgraph", "frontend")
MIGRATIONS_VERSIONS_PATH = Path("migrations/versions")
COMMAND_TIMEOUT_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 10
DIAGNOSTIC_LINE_LIMIT = 100
DIAGNOSTIC_LINE_LENGTH = 4096

CANARY_TIMESTAMP = "2026-01-02 03:04:05"
CANARY_USER = (
    "900001",
    "container_smoke_user",
    "container-smoke@example.invalid",
    "not-a-real-password-hash",
    "user",
    CANARY_TIMESTAMP,
    CANARY_TIMESTAMP,
)
CANARY_SESSION = (
    "900002",
    CANARY_USER[0],
    "container-smoke-session",
    "Container smoke session",
    CANARY_TIMESTAMP,
    CANARY_TIMESTAMP,
)
CANARY_MESSAGE = (
    "900003",
    CANARY_SESSION[0],
    "user",
    "container-smoke-canary",
    CANARY_TIMESTAMP,
)
CANARY_ROW = CANARY_USER + CANARY_SESSION + CANARY_MESSAGE
LEGACY_CANARY_ROW = (
    CANARY_USER[:4]
    + CANARY_USER[5:]
    + CANARY_SESSION
    + CANARY_MESSAGE
)

MYSQL_SHELL_COMMAND = (
    'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
    "exec mysql --batch --raw --skip-column-names --protocol=socket "
    '-uroot "$MYSQL_DATABASE"'
)
REVISION_SQL = "SELECT version_num FROM alembic_version ORDER BY version_num;"
CANARY_SQL = """\
SELECT
    u.id, u.username, u.email, u.hashed_password, u.role,
    u.created_at, u.updated_at,
    s.id, s.user_id, s.session_id, s.title, s.created_at, s.updated_at,
    m.id, m.session_id, m.role, m.content, m.created_at
FROM users AS u
JOIN sessions AS s ON s.user_id = u.id
JOIN messages AS m ON m.session_id = s.id
WHERE u.id = 900001 AND s.id = 900002 AND m.id = 900003;
"""
LEGACY_CANARY_SQL = CANARY_SQL.replace(
    "u.id, u.username, u.email, u.hashed_password, u.role,\n",
    "u.id, u.username, u.email, u.hashed_password,\n",
)
SEED_HEAD_SQL = f"""\
INSERT INTO users
    (id, username, email, hashed_password, role, created_at, updated_at)
VALUES
    ({CANARY_USER[0]}, '{CANARY_USER[1]}', '{CANARY_USER[2]}',
     '{CANARY_USER[3]}', '{CANARY_USER[4]}', '{CANARY_USER[5]}',
     '{CANARY_USER[6]}');
INSERT INTO sessions
    (id, user_id, session_id, title, created_at, updated_at)
VALUES
    ({CANARY_SESSION[0]}, {CANARY_SESSION[1]}, '{CANARY_SESSION[2]}',
     '{CANARY_SESSION[3]}', '{CANARY_SESSION[4]}',
     '{CANARY_SESSION[5]}');
INSERT INTO messages
    (id, session_id, role, content, created_at)
VALUES
    ({CANARY_MESSAGE[0]}, {CANARY_MESSAGE[1]}, '{CANARY_MESSAGE[2]}',
     '{CANARY_MESSAGE[3]}', '{CANARY_MESSAGE[4]}');
"""
LEGACY_SCHEMA_SQL = f"""\
CREATE TABLE users (
    id INTEGER NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY ix_users_email (email),
    KEY ix_users_id (id),
    UNIQUE KEY ix_users_username (username)
) ENGINE=InnoDB;
CREATE TABLE sessions (
    id INTEGER NOT NULL AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_sessions_id (id),
    UNIQUE KEY ix_sessions_session_id (session_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB;
CREATE TABLE messages (
    id INTEGER NOT NULL AUTO_INCREMENT,
    session_id INTEGER NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY ix_messages_id (id),
    FOREIGN KEY (session_id) REFERENCES sessions (id)
) ENGINE=InnoDB;
{SEED_HEAD_SQL.replace(
    ", role, created_at, updated_at",
    ", created_at, updated_at",
).replace(
    f", '{CANARY_USER[4]}', '{CANARY_USER[5]}',",
    f", '{CANARY_USER[5]}',",
)}
"""
LEGACY_SHAPE_SQL = """\
SELECT
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = DATABASE() AND table_name = 'alembic_version'),
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'users' AND column_name = 'role');
"""
EMPTY_DATABASE_SQL = """\
SELECT COUNT(*)
FROM information_schema.tables
WHERE table_schema = DATABASE();
"""

REDACTED_ENV_NAMES = {
    "COMPOSE_DATABASE_URL",
    "JWT_SECRET_KEY",
    "MOONSHOT_API_KEY",
    "MYSQL_ROOT_PASSWORD",
    "TAVILY_API_KEY",
}
TENANT_USERS = (
    ("container-tenant-a", "container-tenant-a@example.com"),
    ("container-tenant-b", "container-tenant-b@example.com"),
)
TENANT_PASSWORD = "container-tenant-test-password"


class SmokeError(RuntimeError):
    """A redacted container smoke verification failure."""


@dataclass(frozen=True)
class ComposeContext:
    """Arguments identifying one isolated Compose project."""

    compose_files: tuple[Path, ...]
    env_file: Path
    project_name: str

    def command(self, *arguments: str) -> list[str]:
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
        ]
        for compose_file in self.compose_files:
            command.extend(("-f", str(compose_file)))
        command.extend(("-p", self.project_name, *arguments))
        return command


def _run_command(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def _compose_output(
    context: ComposeContext,
    *arguments: str,
    input_text: str | None = None,
    operation: str,
) -> str:
    try:
        result = _run_command(
            context.command(*arguments),
            input_text=input_text,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeError(f"{operation} did not complete") from exc
    if result.returncode != 0:
        raise SmokeError(f"{operation} failed")
    return result.stdout


def _mysql(context: ComposeContext, sql: str, operation: str) -> str:
    return _compose_output(
        context,
        "exec",
        "-T",
        "mysql",
        "sh",
        "-ec",
        MYSQL_SHELL_COMMAND,
        input_text=sql,
        operation=operation,
    )


def _literal_assignment(
    module: ast.Module,
    name: str,
) -> object | None:
    for node in module.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if value is None or not any(
            isinstance(target, ast.Name) and target.id == name
            for target in targets
        ):
            continue
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError) as exc:
            raise SmokeError(f"migration {name} is not static") from exc
    return None


def resolve_migration_head(repository_root: Path) -> str:
    """Resolve one static Alembic head without importing project packages."""

    versions_dir = repository_root / MIGRATIONS_VERSIONS_PATH
    if not versions_dir.is_dir():
        raise SmokeError("migration versions directory is missing")

    revisions: set[str] = set()
    referenced: set[str] = set()
    for candidate in sorted(versions_dir.glob("*.py")):
        try:
            module = ast.parse(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise SmokeError("migration source is not readable") from exc
        revision = _literal_assignment(module, "revision")
        if revision is None:
            continue
        if not isinstance(revision, str) or not revision:
            raise SmokeError("migration revision is invalid")
        if revision in revisions:
            raise SmokeError("migration revisions are not unique")
        revisions.add(revision)

        parent = _literal_assignment(module, "down_revision")
        if parent is None:
            continue
        parents = parent if isinstance(parent, (tuple, list)) else (parent,)
        if not all(isinstance(item, str) and item for item in parents):
            raise SmokeError("migration parent revision is invalid")
        referenced.update(parents)

    if not revisions or not referenced.issubset(revisions):
        raise SmokeError("migration graph is incomplete")
    heads = revisions - referenced
    if len(heads) != 1:
        raise SmokeError("migration head is not unique")
    return heads.pop()


def _decode_compose_ps(output: str) -> list[dict[str, object]]:
    stripped = output.strip()
    if not stripped:
        raise SmokeError("Compose returned no service status")
    try:
        decoded = json.loads(stripped)
        if isinstance(decoded, dict):
            return [decoded]
        if isinstance(decoded, list) and all(
            isinstance(item, dict) for item in decoded
        ):
            return decoded
    except json.JSONDecodeError:
        pass

    rows: list[dict[str, object]] = []
    try:
        for line in stripped.splitlines():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError
            rows.append(item)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SmokeError("Compose service status is invalid") from exc
    return rows


def verify_services(context: ComposeContext) -> None:
    output = _compose_output(
        context,
        "ps",
        "--all",
        "--format",
        "json",
        operation="Compose service status",
    )
    rows = _decode_compose_ps(output)
    services = {
        str(row.get("Service", "")): (
            str(row.get("State", "")).lower(),
            str(row.get("Health", "")).lower(),
        )
        for row in rows
    }
    if set(services) != set(SERVICES):
        raise SmokeError("Compose service set is incomplete")
    if any(
        state != "running" or health != "healthy"
        for state, health in services.values()
    ):
        raise SmokeError("one or more Compose services are not healthy")


def verify_http_endpoints(
    fastapi_url: str,
    langgraph_url: str,
    frontend_url: str,
) -> None:
    endpoints = (
        ("FastAPI", fastapi_url, True),
        ("LangGraph", langgraph_url, False),
        ("Frontend", frontend_url, False),
    )
    for name, url, require_health_body in endpoints:
        try:
            with request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
                status = response.status
                body = response.read(4096)
        except (error.URLError, OSError, TimeoutError) as exc:
            raise SmokeError(f"{name} HTTP endpoint is unavailable") from exc
        if status != 200:
            raise SmokeError(f"{name} HTTP endpoint returned non-200")
        if require_health_body:
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SmokeError("FastAPI health response is invalid") from exc
            if payload != {"status": "healthy"}:
                raise SmokeError("FastAPI health response is invalid")


def _json_request(
    method: str,
    url: str,
    *,
    body: dict[str, object] | None = None,
    token: str | None = None,
    form: dict[str, str] | None = None,
) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = parse.urlencode(form).encode("utf-8")
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    http_request = request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(
            http_request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            status = response.status
            content = response.read(65536)
    except error.HTTPError as exc:
        status = exc.code
        content = exc.read(65536)
    except (error.URLError, OSError, TimeoutError) as exc:
        raise SmokeError("tenant HTTP request did not complete") from exc
    if not content:
        return status, None
    try:
        return status, json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SmokeError("tenant HTTP response is invalid") from exc


def _service_base(url: str, suffix: str) -> str:
    normalized = url.rstrip("/")
    if not normalized.endswith(suffix):
        raise SmokeError("tenant HTTP base URL is invalid")
    return normalized[: -len(suffix)]


def _register_tenant_user(
    fastapi_base: str,
    username: str,
    email: str,
) -> tuple[int, str]:
    status, registered = _json_request(
        "POST",
        f"{fastapi_base}/api/auth/register",
        body={
            "username": username,
            "email": email,
            "password": TENANT_PASSWORD,
        },
    )
    if (
        status != 200
        or not isinstance(registered, dict)
        or not isinstance(registered.get("id"), int)
    ):
        raise SmokeError("tenant registration failed")
    status, login = _json_request(
        "POST",
        f"{fastapi_base}/api/auth/login",
        form={
            "username": username,
            "password": TENANT_PASSWORD,
        },
    )
    if (
        status != 200
        or not isinstance(login, dict)
        or not isinstance(login.get("access_token"), str)
    ):
        raise SmokeError("tenant login failed")
    return registered["id"], login["access_token"]


def _thread_ids(payload: object) -> set[str]:
    if not isinstance(payload, list):
        raise SmokeError("thread search response is invalid")
    thread_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or not isinstance(
            item.get("thread_id"),
            str,
        ):
            raise SmokeError("thread search response is invalid")
        thread_ids.add(item["thread_id"])
    return thread_ids


def _search_thread_ids(
    langgraph_base: str,
    token: str,
) -> set[str]:
    status, search = _json_request(
        "POST",
        f"{langgraph_base}/threads/search",
        token=token,
        body={"limit": 100},
    )
    if status != 200:
        raise SmokeError("tenant thread search failed")
    return _thread_ids(search)


def verify_tenant_isolation(
    context: ComposeContext,
    *,
    fastapi_url: str,
    langgraph_url: str,
) -> None:
    """Verify two-user Agent isolation without invoking the model."""
    fastapi_base = _service_base(fastapi_url, "/api/health")
    langgraph_base = _service_base(langgraph_url, "/info")
    users = [
        _register_tenant_user(fastapi_base, username, email)
        for username, email in TENANT_USERS
    ]

    status, _ = _json_request(
        "POST",
        f"{fastapi_base}/api/query",
        body={"query": "must not run"},
    )
    if status != 401:
        raise SmokeError("anonymous FastAPI Agent request was not rejected")
    status, _ = _json_request(
        "POST",
        f"{langgraph_base}/threads/search",
        body={"limit": 10},
    )
    if status != 403:
        raise SmokeError("anonymous LangGraph request was not rejected")

    status, assistants = _json_request(
        "POST",
        f"{langgraph_base}/assistants/search",
        token=users[0][1],
        body={"graph_id": "agent", "limit": 10},
    )
    if (
        status != 200
        or not isinstance(assistants, list)
        or any(
            not isinstance(item, dict)
            or item.get("graph_id") != "agent"
            or not isinstance(item.get("assistant_id"), str)
            for item in assistants
        )
    ):
        raise SmokeError("assistant search escaped the application graph")
    status, _ = _json_request(
        "POST",
        f"{langgraph_base}/assistants/search",
        token=users[0][1],
        body={"graph_id": "forged", "limit": 10},
    )
    if status not in {400, 404}:
        raise SmokeError("unknown assistant graph was not rejected")
    if assistants:
        assistant_id = assistants[0]["assistant_id"]
        status, assistant = _json_request(
            "GET",
            f"{langgraph_base}/assistants/{assistant_id}",
            token=users[0][1],
        )
        if (
            status != 200
            or not isinstance(assistant, dict)
            or assistant.get("graph_id") != "agent"
        ):
            raise SmokeError("application assistant read failed")
    status, _ = _json_request(
        "POST",
        f"{langgraph_base}/assistants",
        token=users[0][1],
        body={"graph_id": "agent", "name": "must-not-create"},
    )
    if status != 403:
        raise SmokeError("assistant write operation was allowed")

    created: list[dict[str, object]] = []
    for index, (user_id, token) in enumerate(users):
        status, thread = _json_request(
            "POST",
            f"{langgraph_base}/threads",
            token=token,
            body={
                "metadata": {
                    "graph_id": "agent",
                    "owner": str(users[1 - index][0]),
                }
            },
        )
        if (
            status != 200
            or not isinstance(thread, dict)
            or not isinstance(thread.get("thread_id"), str)
            or not isinstance(thread.get("metadata"), dict)
            or thread["metadata"].get("owner") != str(user_id)
        ):
            raise SmokeError("tenant thread creation was not owner-scoped")
        created.append(thread)

    search_requests = [
        (index, token)
        for _ in range(2)
        for index, (_, token) in enumerate(users)
    ]
    with ThreadPoolExecutor(max_workers=len(search_requests)) as executor:
        searches = [
            executor.submit(_search_thread_ids, langgraph_base, token)
            for _, token in search_requests
        ]
        search_results = [
            (index, search.result())
            for (index, _), search in zip(
                search_requests,
                searches,
                strict=True,
            )
        ]
    for index, visible in search_results:
        own_id = str(created[index]["thread_id"])
        other_id = str(created[1 - index]["thread_id"])
        if own_id not in visible or other_id in visible:
            raise SmokeError("tenant thread search crossed owners")

    thread_a = str(created[0]["thread_id"])
    token_a = users[0][1]
    token_b = users[1][1]
    for method, path, body in (
        ("GET", f"/threads/{thread_a}", None),
        ("GET", f"/threads/{thread_a}/history", None),
        ("GET", f"/threads/{thread_a}/state", None),
        (
            "POST",
            f"/threads/{thread_a}/state",
            {"values": {}},
        ),
        (
            "PATCH",
            f"/threads/{thread_a}",
            {"metadata": {"changed": True}},
        ),
        ("POST", f"/threads/{thread_a}/copy", None),
        ("DELETE", f"/threads/{thread_a}", None),
        (
            "POST",
            f"/threads/{thread_a}/runs",
            {"assistant_id": "agent", "input": None},
        ),
    ):
        status, _ = _json_request(
            method,
            f"{langgraph_base}{path}",
            token=token_b,
            body=body,
        )
        rejected_statuses = (
            {403, 404, 409}
            if path.endswith("/copy")
            else {403, 404}
        )
        if status not in rejected_statuses:
            raise SmokeError("cross-tenant thread operation was allowed")

    _mysql(
        context,
        (
            "UPDATE users SET role = 'admin' "
            f"WHERE id = {users[1][0]};"
        ),
        "tenant admin role update",
    )
    status, _ = _json_request(
        "GET",
        f"{langgraph_base}/threads/{thread_a}",
        token=token_b,
    )
    if status not in {403, 404}:
        raise SmokeError("administrator bypassed thread ownership")

    status, own_thread = _json_request(
        "GET",
        f"{langgraph_base}/threads/{thread_a}",
        token=token_a,
    )
    if (
        status != 200
        or not isinstance(own_thread, dict)
        or not isinstance(own_thread.get("metadata"), dict)
        or own_thread["metadata"].get("owner") != str(users[0][0])
        or own_thread["metadata"].get("changed") is not None
    ):
        raise SmokeError("cross-tenant rejection changed the owner thread")

    session_count = _mysql(
        context,
        (
            "SELECT COUNT(*) FROM sessions "
            f"WHERE user_id IN ({users[0][0]}, {users[1][0]});"
        ),
        "tenant MySQL session count",
    ).strip()
    if session_count != "0":
        raise SmokeError("Chat UI thread was double-written to MySQL")


def verify_revision(context: ComposeContext, expected_head: str) -> None:
    output = _mysql(context, REVISION_SQL, "migration revision query")
    revisions = [
        line.strip() for line in output.splitlines() if line.strip()
    ]
    if revisions != [expected_head]:
        raise SmokeError("database revision does not match the unique head")


def _verify_canary(
    context: ComposeContext,
    *,
    legacy_schema: bool,
) -> None:
    query = LEGACY_CANARY_SQL if legacy_schema else CANARY_SQL
    expected = LEGACY_CANARY_ROW if legacy_schema else CANARY_ROW
    output = _mysql(context, query, "canary query")
    rows = [line for line in output.splitlines() if line]
    if len(rows) != 1 or tuple(rows[0].split("\t")) != expected:
        raise SmokeError("database canary was not preserved")


def seed_head_canary(context: ComposeContext) -> None:
    _mysql(context, SEED_HEAD_SQL, "head canary seed")
    _verify_canary(context, legacy_schema=False)


def prepare_legacy_database(context: ComposeContext) -> None:
    table_count = _mysql(
        context,
        EMPTY_DATABASE_SQL,
        "legacy database emptiness check",
    ).strip()
    if table_count != "0":
        raise SmokeError("legacy fixture requires an empty database")

    _mysql(context, LEGACY_SCHEMA_SQL, "legacy fixture creation")
    shape = _mysql(
        context,
        LEGACY_SHAPE_SQL,
        "legacy fixture shape query",
    ).strip()
    if shape != "0\t0":
        raise SmokeError("legacy fixture shape is invalid")
    _verify_canary(context, legacy_schema=True)


def verify_runtime(
    context: ComposeContext,
    repository_root: Path,
    scenario: str,
    *,
    fastapi_url: str,
    langgraph_url: str,
    frontend_url: str,
) -> None:
    expected_head = resolve_migration_head(repository_root)
    verify_services(context)
    verify_http_endpoints(fastapi_url, langgraph_url, frontend_url)
    verify_revision(context, expected_head)
    if scenario == "empty":
        verify_tenant_isolation(
            context,
            fastapi_url=fastapi_url,
            langgraph_url=langgraph_url,
        )
    if scenario in {"head", "legacy"}:
        _verify_canary(context, legacy_schema=False)


def _redaction_values(env_file: Path) -> set[str]:
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return set()
    values: set[str] = set()
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in REDACTED_ENV_NAMES and value:
            values.add(value)
    return values


def _redact(text: str, values: set[str]) -> str:
    variants: set[str] = set()
    for value in values:
        variants.add(value)
        variants.add(parse.quote(value, safe=""))
        variants.add(parse.quote_plus(value, safe=""))
    for value in sorted(variants, key=len, reverse=True):
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def _bounded_output(text: str) -> str:
    lines = text.splitlines()[-DIAGNOSTIC_LINE_LIMIT:]
    bounded = [
        line[:DIAGNOSTIC_LINE_LENGTH]
        + ("...[truncated]" if len(line) > DIAGNOSTIC_LINE_LENGTH else "")
        for line in lines
    ]
    return "\n".join(bounded) if bounded else "<no output>"


def print_diagnostics(context: ComposeContext) -> None:
    """Print only bounded Compose status and redacted service log tails."""

    redactions = _redaction_values(context.env_file)
    commands = [
        ("docker compose ps --all", context.command("ps", "--all")),
        *[
            (
                f"{service} logs (tail 100)",
                context.command(
                    "logs",
                    "--no-color",
                    "--tail",
                    str(DIAGNOSTIC_LINE_LIMIT),
                    service,
                ),
            )
            for service in SERVICES
        ],
    ]
    for label, command in commands:
        print(f"== {label} ==")
        try:
            result = _run_command(
                command,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            combined = "\n".join(
                part for part in (result.stdout, result.stderr) if part
            )
            output = _bounded_output(_redact(combined, redactions))
            print(output)
            if result.returncode != 0:
                print("[diagnostic command failed]")
        except subprocess.TimeoutExpired:
            print("[diagnostic command timed out]")
        except OSError:
            print("[diagnostic command unavailable]")


def _build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Verify the isolated release Compose topology."
    )
    parser.add_argument(
        "--compose-file",
        dest="compose_files",
        type=Path,
        action="append",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=repository_root / ".env",
    )
    parser.add_argument("--project-name", required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=repository_root,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument(
        "--scenario",
        choices=("empty", "head", "legacy"),
        required=True,
    )
    verify.add_argument(
        "--fastapi-url",
        default="http://127.0.0.1:8000/api/health",
    )
    verify.add_argument(
        "--langgraph-url",
        default="http://127.0.0.1:2024/info",
    )
    verify.add_argument(
        "--frontend-url",
        default="http://127.0.0.1:3000/data_copilot/",
    )
    subparsers.add_parser("seed-head")
    subparsers.add_parser("prepare-legacy")
    subparsers.add_parser("diagnostics")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    compose_files = args.compose_files or [
        Path(__file__).resolve().parents[1]
        / "docker-config/docker-compose.yml"
    ]
    context = ComposeContext(
        compose_files=tuple(path.resolve() for path in compose_files),
        env_file=args.env_file.resolve(),
        project_name=args.project_name,
    )
    try:
        if args.command == "verify":
            verify_runtime(
                context,
                args.repository_root.resolve(),
                args.scenario,
                fastapi_url=args.fastapi_url,
                langgraph_url=args.langgraph_url,
                frontend_url=args.frontend_url,
            )
        elif args.command == "seed-head":
            seed_head_canary(context)
        elif args.command == "prepare-legacy":
            prepare_legacy_database(context)
        else:
            print_diagnostics(context)
            return 0
    except SmokeError as exc:
        print(f"Container smoke failed: {exc}", file=sys.stderr)
        return 1

    print(f"Container smoke {args.command} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
