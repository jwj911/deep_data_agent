import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from data_agent import readiness
from data_agent.observability import rate_limit_middleware


def _patch_ready_checks(monkeypatch) -> None:
    for name in (
        "_check_model_configuration",
        "_check_database",
        "_check_migration",
        "_check_redis",
        "_check_managed_files",
    ):
        monkeypatch.setattr(readiness, name, Mock())


def _component_statuses(result) -> dict[str, tuple[str, str]]:
    return {
        name: (component.status, component.code)
        for name, component in result.components.items()
    }


def test_readiness_runs_every_shallow_component(monkeypatch) -> None:
    _patch_ready_checks(monkeypatch)

    result = readiness.check_readiness()

    assert result.ready is True
    assert _component_statuses(result) == {
        "model": ("ready", "ready"),
        "database": ("ready", "ready"),
        "migration": ("ready", "ready"),
        "redis": ("ready", "ready"),
        "managed_files": ("ready", "ready"),
    }
    for name in (
        "_check_model_configuration",
        "_check_database",
        "_check_migration",
        "_check_redis",
        "_check_managed_files",
    ):
        getattr(readiness, name).assert_called_once_with()


@pytest.mark.parametrize(
    ("component", "check_name", "failure_code"),
    [
        (
            "model",
            "_check_model_configuration",
            "model_configuration_invalid",
        ),
        ("database", "_check_database", "database_unavailable"),
        ("migration", "_check_migration", "migration_not_ready"),
        ("redis", "_check_redis", "redis_unavailable"),
        (
            "managed_files",
            "_check_managed_files",
            "managed_file_storage_unavailable",
        ),
    ],
)
def test_readiness_failure_is_fixed_and_recovers_on_next_check(
    monkeypatch,
    caplog,
    component,
    check_name,
    failure_code,
) -> None:
    _patch_ready_checks(monkeypatch)
    secret = "mysql://user:password@private/schema SELECT secret"
    check = Mock(side_effect=[RuntimeError(secret), None])
    monkeypatch.setattr(readiness, check_name, check)

    failed = readiness.check_readiness()
    recovered = readiness.check_readiness()

    assert failed.ready is False
    assert _component_statuses(failed)[component] == (
        "unavailable",
        failure_code,
    )
    assert recovered.ready is True
    serialized = json.dumps(failed.response_payload("a" * 32))
    assert secret not in serialized
    assert "password" not in serialized
    assert "SELECT secret" not in serialized
    assert secret not in caplog.text
    assert check.call_count == 2


def test_database_probe_executes_only_select_one(monkeypatch) -> None:
    scalar_result = Mock()
    scalar_result.scalar_one.return_value = 1
    connection = Mock()
    connection.execute.return_value = scalar_result
    connection_context = Mock()
    connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=None)
    engine = Mock()
    engine.connect.return_value = connection_context
    monkeypatch.setattr(readiness, "get_engine", Mock(return_value=engine))

    readiness._check_database()

    statement = connection.execute.call_args.args[0]
    assert str(statement) == "SELECT 1"


def test_migration_probe_requires_unique_current_head(monkeypatch) -> None:
    script = Mock()
    script.get_heads.return_value = ["head-revision"]
    monkeypatch.setattr(
        readiness.ScriptDirectory,
        "from_config",
        Mock(return_value=script),
    )
    monkeypatch.setattr(readiness, "_alembic_config", Mock())

    migration_context = Mock()
    migration_context.get_current_heads.return_value = ["head-revision"]
    monkeypatch.setattr(
        readiness.MigrationContext,
        "configure",
        Mock(return_value=migration_context),
    )
    connection_context = Mock()
    connection_context.__enter__ = Mock(return_value=object())
    connection_context.__exit__ = Mock(return_value=None)
    engine = Mock()
    engine.connect.return_value = connection_context
    monkeypatch.setattr(readiness, "get_engine", Mock(return_value=engine))

    readiness._check_migration()

    script.get_heads.assert_called_once_with()
    migration_context.get_current_heads.assert_called_once_with()


@pytest.mark.parametrize(
    ("source_heads", "current_heads"),
    [
        (["head-a", "head-b"], ["head-a"]),
        (["head-a"], []),
        (["head-a"], ["head-b"]),
    ],
)
def test_migration_probe_rejects_non_unique_or_non_current_revision(
    monkeypatch,
    source_heads,
    current_heads,
) -> None:
    script = Mock()
    script.get_heads.return_value = source_heads
    monkeypatch.setattr(
        readiness.ScriptDirectory,
        "from_config",
        Mock(return_value=script),
    )
    monkeypatch.setattr(readiness, "_alembic_config", Mock())
    migration_context = Mock()
    migration_context.get_current_heads.return_value = current_heads
    monkeypatch.setattr(
        readiness.MigrationContext,
        "configure",
        Mock(return_value=migration_context),
    )
    connection_context = Mock()
    connection_context.__enter__ = Mock(return_value=object())
    connection_context.__exit__ = Mock(return_value=None)
    engine = Mock()
    engine.connect.return_value = connection_context
    monkeypatch.setattr(readiness, "get_engine", Mock(return_value=engine))

    with pytest.raises(RuntimeError):
        readiness._check_migration()


def test_managed_file_probe_uses_an_ephemeral_file(
    monkeypatch,
    tmp_path,
) -> None:
    storage_root = Mock(return_value=tmp_path)
    monkeypatch.setattr(
        readiness.global_managed_file_service,
        "_storage_root",
        storage_root,
    )

    readiness._check_managed_files()

    storage_root.assert_called_once_with(create=True)
    assert list(tmp_path.iterdir()) == []


def test_async_readiness_runs_sync_checks_in_worker_thread(
    monkeypatch,
) -> None:
    expected = object()
    sync_check = Mock(return_value=expected)
    monkeypatch.setattr(readiness, "check_readiness", sync_check)

    result = asyncio.run(readiness.check_readiness_async())

    assert result is expected
    sync_check.assert_called_once_with()


@pytest.mark.parametrize(("ready", "exit_code"), [(True, 0), (False, 1)])
def test_local_readiness_helper_is_silent(
    monkeypatch,
    capsys,
    ready,
    exit_code,
) -> None:
    result = SimpleNamespace(ready=ready)
    monkeypatch.setattr(
        readiness,
        "check_readiness",
        Mock(return_value=result),
    )

    assert readiness.main() == exit_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    ("ready", "expected_status"),
    [(True, 200), (False, 503)],
)
def test_ready_endpoint_has_fixed_body_and_bypasses_rate_limit(
    monkeypatch,
    ready,
    expected_status,
) -> None:
    from data_agent import agent_server

    components = {
        name: readiness.ComponentReadiness(
            status=(
                readiness.READY
                if ready or name != readiness.REDIS_COMPONENT
                else "unavailable"
            ),
            code=(
                readiness.READY
                if ready or name != readiness.REDIS_COMPONENT
                else "redis_unavailable"
            ),
        )
        for name in (
            readiness.MODEL_COMPONENT,
            readiness.DATABASE_COMPONENT,
            readiness.MIGRATION_COMPONENT,
            readiness.REDIS_COMPONENT,
            readiness.MANAGED_FILES_COMPONENT,
        )
    }
    result = readiness.ReadinessResult(components=components)
    monkeypatch.setattr(
        agent_server,
        "check_readiness_async",
        AsyncMock(return_value=result),
    )

    def fail_rate_limit(**kwargs):
        raise AssertionError("readiness must bypass request rate limiting")

    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        SimpleNamespace(check=fail_rate_limit),
    )

    async def request_ready():
        transport = httpx.ASGITransport(app=agent_server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/api/ready",
                headers={"X-Request-ID": "a" * 32},
            )

    response = asyncio.run(request_ready())

    assert response.status_code == expected_status
    assert response.headers["X-Request-ID"] == "a" * 32
    assert response.json() == result.response_payload("a" * 32)
    assert "X-RateLimit-Limit" not in response.headers
