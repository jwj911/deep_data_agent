import json
import subprocess
from pathlib import Path

import pytest

from scripts import verify_container_smoke as smoke


def _write_migration(
    root: Path,
    filename: str,
    revision: str,
    down_revision: str | None,
) -> None:
    parent = "None" if down_revision is None else repr(down_revision)
    path = root / smoke.MIGRATIONS_VERSIONS_PATH / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"revision: str = {revision!r}\n"
        f"down_revision: str | None = {parent}\n",
        encoding="utf-8",
    )


def _context(tmp_path: Path) -> smoke.ComposeContext:
    return smoke.ComposeContext(
        compose_files=(tmp_path / "docker-compose.yml",),
        env_file=tmp_path / ".env",
        project_name="container-smoke-test",
    )


def _result(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_compose_context_preserves_multiple_file_order(tmp_path):
    context = smoke.ComposeContext(
        compose_files=(
            tmp_path / "docker-compose.yml",
            tmp_path / "docker-compose.override.yml",
        ),
        env_file=tmp_path / "smoke.env",
        project_name="container-smoke-test",
    )

    assert context.command("ps") == [
        "docker",
        "compose",
        "--env-file",
        str(context.env_file),
        "-f",
        str(context.compose_files[0]),
        "-f",
        str(context.compose_files[1]),
        "-p",
        context.project_name,
        "ps",
    ]


def test_mysql_password_is_not_passed_in_the_client_arguments(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_compose(context, *arguments, **kwargs):
        calls.append((arguments, kwargs))
        return ""

    monkeypatch.setattr(smoke, "_compose_output", fake_compose)

    smoke._mysql(_context(tmp_path), "SELECT 1;", "test query")

    arguments, kwargs = calls[0]
    assert arguments == (
        "exec",
        "-T",
        "mysql",
        "sh",
        "-ec",
        smoke.MYSQL_SHELL_COMMAND,
    )
    assert "--password" not in smoke.MYSQL_SHELL_COMMAND
    assert 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"' in (
        smoke.MYSQL_SHELL_COMMAND
    )
    assert kwargs["input_text"] == "SELECT 1;"


def test_resolve_migration_head_returns_the_static_unique_head(tmp_path):
    _write_migration(tmp_path, "0001_initial.py", "0001", None)
    _write_migration(tmp_path, "0002_role.py", "0002", "0001")

    assert smoke.resolve_migration_head(tmp_path) == "0002"


def test_resolve_migration_head_rejects_multiple_heads(tmp_path):
    _write_migration(tmp_path, "0001_initial.py", "0001", None)
    _write_migration(tmp_path, "0002_branch.py", "0002", "0001")
    _write_migration(tmp_path, "0003_branch.py", "0003", "0001")

    with pytest.raises(smoke.SmokeError, match="not unique"):
        smoke.resolve_migration_head(tmp_path)


def test_verify_services_requires_exactly_five_healthy_services(
    tmp_path,
    monkeypatch,
):
    rows = [
        {"Service": service, "State": "running", "Health": "healthy"}
        for service in smoke.SERVICES
    ]
    calls = []

    def fake_compose(context, *arguments, **kwargs):
        calls.append(arguments)
        return json.dumps(rows)

    monkeypatch.setattr(smoke, "_compose_output", fake_compose)

    smoke.verify_services(_context(tmp_path))

    assert calls == [("ps", "--all", "--format", "json")]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows.pop(),
        lambda rows: rows[-1].update(Health="unhealthy"),
    ],
    ids=["missing-service", "unhealthy-service"],
)
def test_verify_services_rejects_incomplete_or_unhealthy_topology(
    tmp_path,
    monkeypatch,
    mutate,
):
    rows = [
        {"Service": service, "State": "running", "Health": "healthy"}
        for service in smoke.SERVICES
    ]
    mutate(rows)
    monkeypatch.setattr(
        smoke,
        "_compose_output",
        lambda *args, **kwargs: "\n".join(
            json.dumps(row) for row in rows
        ),
    )

    with pytest.raises(smoke.SmokeError):
        smoke.verify_services(_context(tmp_path))


def test_verify_http_endpoints_checks_all_three_non_business_routes(
    monkeypatch,
):
    calls = []

    class Response:
        def __init__(self, body):
            self.status = 200
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit):
            assert limit == 4096
            return self.body

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        body = b'{"status":"healthy"}' if url.endswith("/api/health") else b"ok"
        return Response(body)

    monkeypatch.setattr(smoke.request, "urlopen", fake_urlopen)

    smoke.verify_http_endpoints(
        "http://127.0.0.1:8000/api/health",
        "http://127.0.0.1:2024/info",
        "http://127.0.0.1:3000/data_copilot/",
    )

    assert calls == [
        (
            "http://127.0.0.1:8000/api/health",
            smoke.HTTP_TIMEOUT_SECONDS,
        ),
        ("http://127.0.0.1:2024/info", smoke.HTTP_TIMEOUT_SECONDS),
        (
            "http://127.0.0.1:3000/data_copilot/",
            smoke.HTTP_TIMEOUT_SECONDS,
        ),
    ]


def test_tenant_isolation_covers_auth_owner_and_no_double_write(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []
    user_ids = {
        smoke.TENANT_USERS[0][0]: 101,
        smoke.TENANT_USERS[1][0]: 202,
    }
    tokens = {"token-a": 101, "token-b": 202}
    thread_ids = {101: "thread-a", 202: "thread-b"}
    file_ids = {"token-a": "file-a", "token-b": "file-b"}

    def fake_json_request(
        method,
        url,
        *,
        body=None,
        token=None,
        form=None,
    ):
        calls.append((method, url, body, token, form))
        if url.endswith("/api/auth/register"):
            return 200, {"id": user_ids[body["username"]]}
        if url.endswith("/api/auth/login"):
            suffix = "a" if form["username"].endswith("-a") else "b"
            return 200, {"access_token": f"token-{suffix}"}
        if url.endswith("/api/query"):
            return 401, {"detail": "invalid"}
        if url.endswith("/threads/search") and token is None:
            return 403, {"detail": "invalid"}
        if url.endswith("/api/files"):
            return 200, [{"file_id": file_ids[token]}]
        if "/api/files/file-a" in url and token == "token-b":
            return 404, {"detail": "not found"}
        if url.endswith("/api/files/file-a/analysis"):
            return 200, {"content": "managed smoke a"}
        if url.endswith("/api/files/file-b/analysis"):
            return 200, {"content": "managed smoke b"}
        if url.endswith("/api/files/file-a") and method == "DELETE":
            return 204, None
        if url.endswith("/assistants/search"):
            if body["graph_id"] == "forged":
                return 404, {"detail": "not found"}
            return 200, [
                {
                    "assistant_id": "assistant-agent",
                    "graph_id": "agent",
                }
            ]
        if url.endswith("/assistants/assistant-agent"):
            return 200, {
                "assistant_id": "assistant-agent",
                "graph_id": "agent",
            }
        if url.endswith("/assistants") and method == "POST":
            return 403, {"detail": "forbidden"}
        if url.endswith("/threads") and method == "POST":
            user_id = tokens[token]
            return 200, {
                "thread_id": thread_ids[user_id],
                "metadata": {
                    "graph_id": "agent",
                    "owner": str(user_id),
                },
            }
        if url.endswith("/threads/search"):
            user_id = tokens[token]
            return 200, [{"thread_id": thread_ids[user_id]}]
        if token == "token-b" and url.endswith("/threads/thread-a/copy"):
            return 409, {"detail": "conflict"}
        if token == "token-b" and "/threads/thread-a" in url:
            return 404, {"detail": "not found"}
        if token == "token-a" and url.endswith("/threads/thread-a"):
            return 200, {
                "thread_id": "thread-a",
                "metadata": {"owner": "101"},
            }
        raise AssertionError((method, url, token))

    mysql_calls = []

    def fake_mysql(context, sql, operation):
        mysql_calls.append((sql, operation))
        if operation == "tenant MySQL session count":
            return "0\n"
        if operation == "tenant managed file count":
            return "1\n"
        return ""

    multipart_calls = []

    def fake_multipart(url, *, token, filename, content, content_type):
        multipart_calls.append(
            (url, token, filename, len(content), content_type)
        )
        if filename == "invalid.json":
            return 400, {"detail": "invalid"}
        if filename == "oversized.txt":
            return 413, {"detail": "too large"}
        return 201, [{"file_id": file_ids[token]}]

    tool_calls = []

    monkeypatch.setattr(smoke, "_json_request", fake_json_request)
    monkeypatch.setattr(smoke, "_multipart_file_request", fake_multipart)
    monkeypatch.setattr(smoke, "_mysql", fake_mysql)
    monkeypatch.setattr(
        smoke,
        "_verify_langgraph_managed_file",
        lambda context, **kwargs: tool_calls.append(kwargs),
    )

    smoke.verify_tenant_isolation(
        _context(tmp_path),
        fastapi_url="http://127.0.0.1:8000/api/health",
        langgraph_url="http://127.0.0.1:2024/info",
    )

    assert any(
        url.endswith("/threads/thread-a/runs") and token == "token-b"
        for _, url, _, token, _ in calls
    )
    assert any(
        url.endswith("/threads/thread-a/history") and token == "token-b"
        for _, url, _, token, _ in calls
    )
    assert any(
        url.endswith("/threads/thread-a/state")
        and method == "POST"
        and token == "token-b"
        for method, url, _, token, _ in calls
    )
    assert any(
        url.endswith("/threads/thread-a/copy") and token == "token-b"
        for _, url, _, token, _ in calls
    )
    assert sum(
        url.endswith("/threads/search") and token in tokens
        for _, url, _, token, _ in calls
    ) == 4
    assert any(
        url.endswith("/assistants")
        and method == "POST"
        and token == "token-a"
        for method, url, _, token, _ in calls
    )
    assert any(
        operation == "tenant admin role update"
        for _, operation in mysql_calls
    )
    assert any(
        operation == "tenant MySQL session count"
        for _, operation in mysql_calls
    )
    assert any(
        operation == "tenant managed file count"
        for _, operation in mysql_calls
    )
    assert len(tool_calls) == 2
    assert any(
        filename == "oversized.txt"
        and size == smoke.MANAGED_FILE_MAX_BYTES + 1
        for _, _, filename, size, _ in multipart_calls
    )


@pytest.mark.parametrize(
    "output",
    ["", "0001\n0002\n", "unexpected\n"],
    ids=["missing", "multiple", "mismatch"],
)
def test_verify_revision_requires_one_exact_static_head(
    tmp_path,
    monkeypatch,
    output,
):
    monkeypatch.setattr(
        smoke,
        "_mysql",
        lambda context, sql, operation: output,
    )

    with pytest.raises(smoke.SmokeError, match="unique head"):
        smoke.verify_revision(_context(tmp_path), "0002")


def test_seed_head_canary_writes_and_reads_the_full_invariant(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_mysql(context, sql, operation):
        calls.append((sql, operation))
        if operation == "canary query":
            return "\t".join(smoke.CANARY_ROW) + "\n"
        return ""

    monkeypatch.setattr(smoke, "_mysql", fake_mysql)

    smoke.seed_head_canary(_context(tmp_path))

    assert calls[0] == (smoke.SEED_HEAD_SQL, "head canary seed")
    assert calls[1] == (smoke.CANARY_SQL, "canary query")


def test_prepare_legacy_database_builds_unversioned_baseline_and_canary(
    tmp_path,
    monkeypatch,
):
    calls = []
    outputs = {
        "legacy database emptiness check": "0\n",
        "legacy fixture creation": "",
        "legacy fixture shape query": "0\t0\n",
        "canary query": "\t".join(smoke.LEGACY_CANARY_ROW) + "\n",
    }

    def fake_mysql(context, sql, operation):
        calls.append((sql, operation))
        return outputs[operation]

    monkeypatch.setattr(smoke, "_mysql", fake_mysql)

    smoke.prepare_legacy_database(_context(tmp_path))

    users_ddl = smoke.LEGACY_SCHEMA_SQL.split("CREATE TABLE sessions", 1)[0]
    assert "\n    role " not in users_ddl
    assert "alembic_version" not in smoke.LEGACY_SCHEMA_SQL
    assert [operation for _, operation in calls] == [
        "legacy database emptiness check",
        "legacy fixture creation",
        "legacy fixture shape query",
        "canary query",
    ]


def test_canary_comparison_rejects_changed_role(tmp_path, monkeypatch):
    changed = list(smoke.CANARY_ROW)
    changed[4] = "admin"
    monkeypatch.setattr(
        smoke,
        "_mysql",
        lambda context, sql, operation: "\t".join(changed) + "\n",
    )

    with pytest.raises(smoke.SmokeError, match="not preserved"):
        smoke._verify_canary(_context(tmp_path), legacy_schema=False)


def test_diagnostics_are_bounded_and_replace_known_fake_values(
    tmp_path,
    monkeypatch,
    capsys,
):
    context = _context(tmp_path)
    fake_values = {
        "MOONSHOT_API_KEY": "runtime-model-fake-value",
        "TAVILY_API_KEY": "runtime-search-fake-value",
        "JWT_SECRET_KEY": "runtime-jwt-fake-value-with-32-characters",
        "MYSQL_ROOT_PASSWORD": "runtime-database-fake-value",
        "COMPOSE_DATABASE_URL": (
            "mysql+pymysql://root:runtime-database-fake-value"
            "@mysql:3306/smoke"
        ),
    }
    context.env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in fake_values.items()),
        encoding="utf-8",
    )
    calls = []
    long_lines = "\n".join(f"line-{index}" for index in range(120))
    raw_values = tuple(fake_values.values())
    encoded_database_url = smoke.parse.quote(
        fake_values["COMPOSE_DATABASE_URL"],
        safe="",
    )

    def fake_run(command, *, input_text=None, timeout):
        calls.append((command, input_text, timeout))
        secrets = "\n".join(raw_values)
        return _result(
            stdout=(
                f"{long_lines}\n{secrets}\n"
                f"{encoded_database_url}\n"
            )
        )

    monkeypatch.setattr(smoke, "_run_command", fake_run)

    smoke.print_diagnostics(context)

    captured = capsys.readouterr().out
    assert all(value not in captured for value in raw_values)
    assert encoded_database_url not in captured
    assert "[REDACTED]" in captured
    assert "line-0\n" not in captured
    assert len(calls) == 1 + len(smoke.SERVICES)
    assert calls[0][0][-2:] == ["ps", "--all"]
    assert all(call[2] == smoke.COMMAND_TIMEOUT_SECONDS for call in calls)
    for service, call in zip(smoke.SERVICES, calls[1:]):
        assert call[0][-5:] == [
            "logs",
            "--no-color",
            "--tail",
            "100",
            service,
        ]
