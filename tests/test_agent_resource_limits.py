import asyncio
import logging
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.agents.middleware import (ModelCallLimitMiddleware,
                                         ToolCallLimitMiddleware)
from langchain.agents.middleware.model_call_limit import \
    ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import \
    ToolCallLimitExceededError
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from data_agent.config.config import Config, ConfigurationError, config
from data_agent.services import agent_service
from data_agent.tools import search
from data_agent.tools.tool_manager import ToolManager

RESOURCE_DEFAULTS = {
    "MODEL_REQUEST_TIMEOUT_SECONDS": 45,
    "MODEL_MAX_RETRIES": 1,
    "MODEL_MAX_OUTPUT_TOKENS": 4096,
    "AGENT_QUERY_MAX_CHARS": 8000,
    "AGENT_RESPONSE_MAX_CHARS": 32000,
    "AGENT_RUN_TIMEOUT_SECONDS": 60,
    "AGENT_RECURSION_LIMIT": 25,
    "AGENT_MODEL_CALL_LIMIT": 8,
    "AGENT_TOOL_CALL_LIMIT": 12,
    "AGENT_GLOBAL_CONCURRENCY_LIMIT": 4,
    "AGENT_USER_CONCURRENCY_LIMIT": 1,
    "AGENT_CONCURRENCY_WAIT_SECONDS": 1,
    "AGENT_CONCURRENCY_LEASE_TTL_SECONDS": 75,
    "SEARCH_QUERY_MAX_CHARS": 2000,
    "SEARCH_MAX_RESULTS": 5,
    "SEARCH_TIMEOUT_SECONDS": 15,
    "SEARCH_MAX_OUTPUT_BYTES": 65536,
    "REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS": 1,
    "REDIS_RECOVERY_MAX_BACKOFF_SECONDS": 30,
    "REDIS_RECOVERY_JITTER_RATIO": 0.2,
}


class _AllowGraphLeaseManager:
    @contextmanager
    def hold(self, _subject):
        yield

    @asynccontextmanager
    async def hold_async(self, _subject):
        yield


def _clear_resource_environment(monkeypatch) -> None:
    for name in RESOURCE_DEFAULTS:
        monkeypatch.delenv(name, raising=False)


def test_resource_config_defaults_are_safe(monkeypatch) -> None:
    _clear_resource_environment(monkeypatch)

    runtime = Config()

    for name, expected in RESOURCE_DEFAULTS.items():
        assert getattr(runtime, name) == expected
    assert runtime.FILE_ANALYSIS_MAX_CHARS == 20000


@pytest.mark.parametrize("name", sorted(RESOURCE_DEFAULTS))
def test_resource_config_requires_positive_values(monkeypatch, name) -> None:
    _clear_resource_environment(monkeypatch)
    monkeypatch.setenv(name, "0")

    with pytest.raises(ConfigurationError):
        Config()


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "AGENT_GLOBAL_CONCURRENCY_LIMIT": "1",
                "AGENT_USER_CONCURRENCY_LIMIT": "2",
            },
            "AGENT_USER_CONCURRENCY_LIMIT",
        ),
        (
            {
                "AGENT_RUN_TIMEOUT_SECONDS": "60",
                "AGENT_CONCURRENCY_WAIT_SECONDS": "60",
            },
            "AGENT_CONCURRENCY_WAIT_SECONDS",
        ),
        (
            {
                "AGENT_RUN_TIMEOUT_SECONDS": "60",
                "AGENT_CONCURRENCY_LEASE_TTL_SECONDS": "60",
            },
            "AGENT_CONCURRENCY_LEASE_TTL_SECONDS",
        ),
        (
            {
                "AGENT_RUN_TIMEOUT_SECONDS": "40",
                "MODEL_REQUEST_TIMEOUT_SECONDS": "41",
            },
            "MODEL_REQUEST_TIMEOUT_SECONDS",
        ),
        (
            {
                "AGENT_RUN_TIMEOUT_SECONDS": "10",
                "MODEL_REQUEST_TIMEOUT_SECONDS": "10",
                "SEARCH_TIMEOUT_SECONDS": "15",
            },
            "SEARCH_TIMEOUT_SECONDS",
        ),
        (
            {
                "AGENT_QUERY_MAX_CHARS": "1000",
                "SEARCH_QUERY_MAX_CHARS": "2000",
            },
            "SEARCH_QUERY_MAX_CHARS",
        ),
        (
            {
                "AGENT_RESPONSE_MAX_CHARS": "19999",
                "FILE_ANALYSIS_MAX_CHARS": "20000",
            },
            "FILE_ANALYSIS_MAX_CHARS",
        ),
        (
            {
                "REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS": "2",
                "REDIS_RECOVERY_MAX_BACKOFF_SECONDS": "1",
            },
            "REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS",
        ),
    ],
)
def test_resource_config_relationships(
    monkeypatch,
    values,
    message,
) -> None:
    _clear_resource_environment(monkeypatch)
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        Config()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MODEL_REQUEST_TIMEOUT_SECONDS", "46"),
        ("MODEL_MAX_RETRIES", "2"),
        ("MODEL_MAX_OUTPUT_TOKENS", "4097"),
        ("SEARCH_QUERY_MAX_CHARS", "2001"),
        ("SEARCH_MAX_RESULTS", "6"),
        ("SEARCH_TIMEOUT_SECONDS", "16"),
        ("SEARCH_MAX_OUTPUT_BYTES", "65537"),
        ("FILE_ANALYSIS_MAX_CHARS", "20001"),
        ("REDIS_RECOVERY_MAX_BACKOFF_SECONDS", "31"),
        ("REDIS_RECOVERY_JITTER_RATIO", "1.1"),
    ],
)
def test_fixed_external_limits_cannot_be_increased(
    monkeypatch,
    name,
    value,
) -> None:
    _clear_resource_environment(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=name):
        Config()


def test_create_agent_graph_uses_fixed_model_and_call_limits(
    monkeypatch,
) -> None:
    model = object()
    compiled_graph = object()
    bounded_graph = object()
    model_factory = Mock(return_value=model)
    graph_factory = Mock(return_value=compiled_graph)
    apply_bounds = Mock(return_value=bounded_graph)
    monkeypatch.setattr(agent_service, "ChatOpenAI", model_factory)
    monkeypatch.setattr(agent_service, "create_deep_agent", graph_factory)
    monkeypatch.setattr(
        agent_service,
        "_apply_graph_resource_bounds",
        apply_bounds,
    )
    monkeypatch.setattr(config, "MOONSHOT_API_KEY", "fake-model-key")

    result = agent_service.create_agent_graph()

    assert result is bounded_graph
    model_factory.assert_called_once_with(
        model=config.MODEL_NAME,
        api_key="fake-model-key",
        base_url=config.MODEL_BASE_URL,
        temperature=config.MODEL_TEMPERATURE,
        timeout=config.MODEL_REQUEST_TIMEOUT_SECONDS,
        max_retries=config.MODEL_MAX_RETRIES,
        max_tokens=config.MODEL_MAX_OUTPUT_TOKENS,
    )
    call = graph_factory.call_args
    assert call.kwargs["model"] is model
    middleware = call.kwargs["middleware"]
    assert len(middleware) == 2
    assert isinstance(middleware[0], ModelCallLimitMiddleware)
    assert middleware[0].run_limit == config.AGENT_MODEL_CALL_LIMIT
    assert middleware[0].exit_behavior == "error"
    assert isinstance(middleware[1], ToolCallLimitMiddleware)
    assert middleware[1].tool_name is None
    assert middleware[1].run_limit == config.AGENT_TOOL_CALL_LIMIT
    assert middleware[1].exit_behavior == "error"
    apply_bounds.assert_called_once_with(compiled_graph)


class _CounterState(TypedDict):
    count: int


def test_graph_overrides_client_recursion_and_model_budget_config() -> None:
    def increment(state):
        return {"count": state["count"] + 1}

    builder = StateGraph(_CounterState)
    builder.add_node("increment", increment)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", "increment")
    graph = agent_service._apply_graph_resource_bounds(
        builder.compile(),
        lease_manager=_AllowGraphLeaseManager(),
    )
    client_config = {
        "recursion_limit": 999,
        "max_tokens": 999999,
        "max_retries": 99,
        "configurable": {
            "request_id": "a" * 32,
            "recursion_limit": 999,
            "max_tokens": 999999,
            "langgraph_auth_user": SimpleNamespace(
                identity="1",
                is_authenticated=True,
            ),
            "langgraph_auth_permissions": ["agent.invoke_own"],
        },
    }

    bounded = agent_service._bounded_run_config(client_config)
    assert bounded["recursion_limit"] == config.AGENT_RECURSION_LIMIT
    assert "max_tokens" not in bounded
    assert "max_retries" not in bounded
    assert "recursion_limit" not in bounded["configurable"]
    assert "max_tokens" not in bounded["configurable"]
    assert bounded["configurable"]["request_id"] == "a" * 32

    with pytest.raises(
        GraphRecursionError,
        match=f"Recursion limit of {config.AGENT_RECURSION_LIMIT}",
    ):
        graph.invoke({"count": 0}, config=client_config)

    async def invoke_async():
        await graph.ainvoke({"count": 0}, config=client_config)

    with pytest.raises(
        GraphRecursionError,
        match=f"Recursion limit of {config.AGENT_RECURSION_LIMIT}",
    ):
        asyncio.run(invoke_async())


def test_installed_middlewares_reject_ninth_model_and_thirteenth_tool() -> None:
    model_limit = ModelCallLimitMiddleware(
        run_limit=8,
        exit_behavior="error",
    )
    with pytest.raises(ModelCallLimitExceededError):
        model_limit.before_model(
            {"run_model_call_count": 8},
            runtime=None,
        )

    document_calls = [
        {
            "name": "analyze_document",
            "args": {"file_id": f"00000000-0000-0000-0000-{index:012d}"},
            "id": f"call-{index}",
            "type": "tool_call",
        }
        for index in range(13)
    ]
    tool_limit = ToolCallLimitMiddleware(
        run_limit=12,
        exit_behavior="error",
    )
    with pytest.raises(ToolCallLimitExceededError):
        tool_limit.after_model(
            {
                "messages": [
                    AIMessage(content="", tool_calls=document_calls),
                ]
            },
            runtime=None,
        )


def test_residual_code_execution_environment_is_ignored(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENABLE_CODE_EXECUTION", "true")

    runtime = Config()
    tools = ToolManager()

    assert not hasattr(runtime, "ENABLE_CODE_EXECUTION")
    assert "execute_python_code" not in tools.get_tool_names()
    assert not Path("data_agent/tools/code_execution.py").exists()


class _FakeSearchClient:
    def __init__(
        self,
        result=None,
        *,
        delay: float = 0,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.delay = delay
        self.error = error
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


def _disable_search_cache(monkeypatch):
    get = AsyncMock(return_value=None)
    set_ = AsyncMock(return_value=True)
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "fake-search-key")
    monkeypatch.setattr(search.global_cache_service, "aget", get)
    monkeypatch.setattr(search.global_cache_service, "aset", set_)
    monkeypatch.setattr(search.global_cache_service, "adelete", delete)
    return get, set_, delete


def test_search_schema_and_upstream_request_are_bounded(monkeypatch) -> None:
    _, cache_set, _ = _disable_search_cache(monkeypatch)
    client = _FakeSearchClient(
        {
            "images": ["not-exposed"],
            "raw_content": "not-exposed",
            "results": [
                {
                    "title": f"title-{index}",
                    "url": f"https://example.test/{index}",
                    "content": "summary",
                    "raw_content": "private raw content",
                }
                for index in range(7)
            ],
        }
    )
    monkeypatch.setattr(search, "_get_tavily_client", lambda: client)
    tool = StructuredTool.from_function(coroutine=search.internet_search)

    schema = tool.args_schema.model_json_schema()["properties"]
    assert schema["query"]["maxLength"] == 2000
    assert schema["max_results"]["maximum"] == 5
    assert set(schema["topic"]["enum"]) == {"general", "news"}
    assert "include_raw_content" not in schema

    result = asyncio.run(
        search.internet_search(
            "bounded query",
            max_results=5,
            topic="news",
        )
    )

    assert len(result["results"]) == 5
    assert "images" not in result
    assert "raw_content" not in str(result)
    assert client.calls == [
        (
            "bounded query",
            {
                "max_results": 5,
                "include_answer": False,
                "include_images": False,
                "include_raw_content": False,
                "topic": "news",
            },
        )
    ]
    cache_set.assert_awaited_once()
    assert cache_set.call_args.args[1] == result


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"query": "x" * 2001}, "search_invalid_query"),
        (
            {"query": "query", "max_results": 6},
            "search_invalid_max_results",
        ),
        (
            {"query": "query", "topic": "images"},
            "search_invalid_topic",
        ),
    ],
)
def test_invalid_search_request_stops_before_cache_and_network(
    monkeypatch,
    kwargs,
    code,
) -> None:
    cache_get, cache_set, _ = _disable_search_cache(monkeypatch)
    client = _FakeSearchClient({"results": []})
    monkeypatch.setattr(search, "_get_tavily_client", lambda: client)

    result = asyncio.run(search.internet_search(**kwargs))

    assert result["code"] == code
    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()
    assert client.calls == []


def test_search_timeout_does_not_cache(monkeypatch) -> None:
    _, cache_set, _ = _disable_search_cache(monkeypatch)
    client = _FakeSearchClient({"results": []}, delay=0.05)
    monkeypatch.setattr(search, "_get_tavily_client", lambda: client)
    monkeypatch.setattr(config, "SEARCH_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(search.internet_search("slow query"))

    assert result["code"] == "search_timeout"
    cache_set.assert_not_awaited()


def test_oversized_search_output_is_not_cached_or_logged(
    monkeypatch,
    caplog,
) -> None:
    _, cache_set, _ = _disable_search_cache(monkeypatch)
    private_content = "private-search-content-" * 20
    client = _FakeSearchClient(
        {"results": [{"content": private_content}]}
    )
    monkeypatch.setattr(search, "_get_tavily_client", lambda: client)
    monkeypatch.setattr(config, "SEARCH_MAX_OUTPUT_BYTES", 64)
    monkeypatch.setattr(
        logging.getLogger("deep_data_agent"),
        "propagate",
        True,
    )

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(search.internet_search("oversized query"))

    assert result["code"] == "search_response_too_large"
    cache_set.assert_not_awaited()
    assert private_content not in caplog.text


def test_missing_search_configuration_does_not_call_network(
    monkeypatch,
) -> None:
    cache_get, cache_set, _ = _disable_search_cache(monkeypatch)
    search._get_tavily_client.cache_clear()
    monkeypatch.setattr(config, "TAVILY_API_KEY", None)

    result = asyncio.run(search.internet_search("query"))

    assert result["code"] == "configuration_error"
    cache_get.assert_not_awaited()
    cache_set.assert_not_awaited()
