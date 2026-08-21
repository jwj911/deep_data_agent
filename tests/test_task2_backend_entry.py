import asyncio
import importlib
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from data_agent.config.config import Config, ConfigurationError, config
from data_agent.models.user import User, UserRole
from data_agent.services.agent_service import (AgentInvocationError,
                                               AgentService)
from data_agent.services.cache_service import CacheService
from data_agent.tools.tool_manager import ToolManager


def _actor(user_id: int = 1) -> User:
    return User(id=user_id, role=UserRole.USER.value)


class _AllowLeaseManager:
    @asynccontextmanager
    async def hold_async(self, _subject):
        yield


def test_langgraph_config_exports_dedicated_agent_module() -> None:
    langgraph_config = json.loads(Path("langgraph.json").read_text())

    assert (
        langgraph_config["graphs"]["agent"]
        == "./data_agent/agent_graph.py:agent"
    )


def test_langgraph_entry_does_not_import_database(monkeypatch) -> None:
    sys.modules.pop("data_agent.agent_graph", None)
    sys.modules.pop("data_agent.config.database", None)
    agent_service = importlib.import_module(
        "data_agent.services.agent_service"
    )
    graph = object()
    create_agent_graph = Mock(return_value=graph)
    monkeypatch.setattr(
        agent_service, "create_agent_graph", create_agent_graph
    )

    graph_module = importlib.import_module("data_agent.agent_graph")

    assert graph_module.agent is graph
    create_agent_graph.assert_called_once_with()
    assert "data_agent.config.database" not in sys.modules


def test_fastapi_import_does_not_initialize_database(monkeypatch) -> None:
    database = importlib.import_module("data_agent.config.database")
    monkeypatch.setattr(
        database,
        "init_db",
        Mock(side_effect=AssertionError("DB initialized during import")),
    )

    server = importlib.import_module("data_agent.agent_server")
    importlib.reload(server)

    assert server.app is not None


def test_fastapi_lifespan_initializes_database(monkeypatch) -> None:
    server = importlib.import_module("data_agent.agent_server")
    init_db = Mock()
    monkeypatch.setattr(server, "init_db", init_db)

    async def run_lifespan() -> None:
        async with server.lifespan(server.app):
            init_db.assert_called_once_with()

    asyncio.run(run_lifespan())


@pytest.mark.parametrize("path", ["/api/live", "/api/health"])
def test_liveness_endpoints_do_not_touch_dependencies(
    monkeypatch,
    path,
) -> None:
    server = importlib.import_module("data_agent.agent_server")
    database = importlib.import_module("data_agent.config.database")
    rate_limit = importlib.import_module(
        "data_agent.observability.rate_limit_middleware"
    )
    file_service = importlib.import_module(
        "data_agent.services.managed_file_service"
    )

    def fail(name):
        return Mock(
            side_effect=AssertionError(
                f"{name} touched by liveness endpoint"
            )
        )

    dependency_calls = {
        "database_init": fail("database init"),
        "database_session": fail("database session"),
        "redis_rate_limit": fail("Redis rate limit"),
        "agent_invoke": AsyncMock(side_effect=fail("Agent")),
        "agent_graph": fail("Agent graph/model/search"),
        "file_storage": fail("file storage"),
    }
    limiter = Mock()
    limiter.check = dependency_calls["redis_rate_limit"]
    monkeypatch.setattr(server, "init_db", dependency_calls["database_init"])
    monkeypatch.setattr(
        database,
        "get_session_factory",
        dependency_calls["database_session"],
    )
    monkeypatch.setattr(rate_limit, "global_rate_limit_service", limiter)
    monkeypatch.setattr(
        server.global_agent_service,
        "ainvoke",
        dependency_calls["agent_invoke"],
    )
    monkeypatch.setattr(
        server.global_agent_service,
        "_get_agent",
        dependency_calls["agent_graph"],
    )
    monkeypatch.setattr(
        file_service.global_managed_file_service,
        "_storage_root",
        dependency_calls["file_storage"],
    )

    async def request_liveness():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    response = asyncio.run(request_liveness())

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert "X-RateLimit-Limit" not in response.headers
    for dependency in dependency_calls.values():
        dependency.assert_not_called()


def test_placeholder_model_key_is_reported_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "your_moonshot_api_key_here")

    runtime_config = Config()

    with pytest.raises(
        ConfigurationError, match="Missing required model configuration"
    ):
        runtime_config.require_model_api_key()


def test_redis_connection_failure_degrades_to_cache_miss(
    caplog,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging.getLogger("deep_data_agent"),
        "propagate",
        True,
    )
    client = Mock()
    client.ping.side_effect = RedisConnectionError("connection refused")

    cache = CacheService(client=client)

    assert cache.available is False
    assert cache.get("key") is None
    assert cache.set("key", "value") is False
    assert "Redis unavailable; cache disabled" in caplog.text


def test_code_execution_cannot_be_enabled_by_residual_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENABLE_CODE_EXECUTION", "true")

    runtime = Config()

    assert not hasattr(runtime, "ENABLE_CODE_EXECUTION")
    assert "execute_python_code" not in ToolManager().get_tool_names()


def test_agent_service_propagates_configuration_error(monkeypatch) -> None:
    service = AgentService(lease_manager=_AllowLeaseManager())
    monkeypatch.setattr(
        service,
        "_get_agent",
        Mock(side_effect=ConfigurationError("MOONSHOT_API_KEY missing")),
    )

    with pytest.raises(ConfigurationError):
        asyncio.run(
            service.ainvoke(
                "query",
                actor=_actor(),
                request_id="request-1",
            )
        )


def test_agent_service_wraps_upstream_error(monkeypatch) -> None:
    agent = Mock()
    agent.ainvoke = AsyncMock(
        side_effect=RuntimeError("secret upstream detail")
    )
    service = AgentService(
        agent=agent,
        lease_manager=_AllowLeaseManager(),
    )

    with pytest.raises(
        AgentInvocationError, match="Agent upstream request failed"
    ):
        asyncio.run(
            service.ainvoke(
                "query",
                actor=_actor(),
                request_id="request-2",
            )
        )


def test_query_maps_configuration_error_to_stable_non_2xx(
    monkeypatch,
) -> None:
    server = importlib.import_module("data_agent.agent_server")
    monkeypatch.setattr(
        server.global_agent_service,
        "ainvoke",
        AsyncMock(
            side_effect=ConfigurationError("MOONSHOT_API_KEY missing")
        ),
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            server.query_agent(
                server.QueryRequest(query="query"),
                current_user=_actor(),
            )
        )

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "agent_not_configured"
    assert caught.value.detail["request_id"]


def test_query_maps_upstream_error_to_stable_non_2xx(monkeypatch) -> None:
    server = importlib.import_module("data_agent.agent_server")
    monkeypatch.setattr(
        server.global_agent_service,
        "ainvoke",
        AsyncMock(side_effect=AgentInvocationError("private detail")),
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            server.query_agent(
                server.QueryRequest(query="query"),
                current_user=_actor(),
            )
        )

    assert caught.value.status_code == 502
    assert caught.value.detail["code"] == "agent_upstream_error"
    assert "private detail" not in str(caught.value.detail)
