import asyncio
import importlib
import json
import logging
import sys
from pathlib import Path
from unittest.mock import Mock

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


def test_health_check_does_not_invoke_agent(monkeypatch) -> None:
    server = importlib.import_module("data_agent.agent_server")
    invoke = Mock(side_effect=AssertionError("agent invoked by health check"))
    monkeypatch.setattr(server.global_agent_service, "invoke", invoke)

    response = asyncio.run(server.health_check())

    assert response == {"status": "healthy"}
    invoke.assert_not_called()


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


def test_code_execution_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(config, "ENABLE_CODE_EXECUTION", False)

    assert "execute_python_code" not in ToolManager().get_tool_names()


def test_code_execution_requires_explicit_enable(monkeypatch, caplog) -> None:
    monkeypatch.setattr(config, "ENABLE_CODE_EXECUTION", True)
    monkeypatch.setattr(
        logging.getLogger("deep_data_agent"),
        "propagate",
        True,
    )

    tool_manager = ToolManager()

    assert "execute_python_code" in tool_manager.get_tool_names()
    assert "explicitly enabled" in caplog.text


def test_agent_service_propagates_configuration_error(monkeypatch) -> None:
    service = AgentService()
    monkeypatch.setattr(
        service,
        "_get_agent",
        Mock(side_effect=ConfigurationError("MOONSHOT_API_KEY missing")),
    )

    with pytest.raises(ConfigurationError):
        service.invoke(
            "query",
            actor=_actor(),
            request_id="request-1",
        )


def test_agent_service_wraps_upstream_error(monkeypatch) -> None:
    agent = Mock()
    agent.invoke.side_effect = RuntimeError("secret upstream detail")
    service = AgentService(agent=agent)

    with pytest.raises(
        AgentInvocationError, match="Agent upstream request failed"
    ):
        service.invoke(
            "query",
            actor=_actor(),
            request_id="request-2",
        )


def test_query_maps_configuration_error_to_stable_non_2xx(
    monkeypatch,
) -> None:
    server = importlib.import_module("data_agent.agent_server")
    monkeypatch.setattr(
        server.global_agent_service,
        "invoke",
        Mock(side_effect=ConfigurationError("MOONSHOT_API_KEY missing")),
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
        "invoke",
        Mock(side_effect=AgentInvocationError("private detail")),
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
