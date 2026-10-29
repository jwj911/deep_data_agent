import asyncio
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace

import pytest
from langchain.agents.middleware.model_call_limit import \
    ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import \
    ToolCallLimitExceededError
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from typing_extensions import TypedDict

from data_agent.services import agent_service
from data_agent.services.agent_lease import (AgentBusyError,
                                             AgentIdentityError,
                                             AgentProtectionUnavailableError)

_COPY_VARIANTS = ["copy", "with_config", "copy_chain", "get_graph"]
_INVOCATIONS = ["invoke", "ainvoke", "stream", "astream"]


class _CopyState(TypedDict):
    count: int


class _RecordingLeaseManager:
    def __init__(self, error: Exception | None = None) -> None:
        self.events: list[tuple[str, str]] = []
        self.error = error

    @contextmanager
    def hold(self, subject):
        if self.error is not None:
            raise self.error
        self.events.append(("acquire", subject))
        try:
            yield
        finally:
            self.events.append(("release", subject))

    @asynccontextmanager
    async def hold_async(self, subject):
        with self.hold(subject):
            yield


def _authenticated_config(subject: str = "17"):
    return {
        "configurable": {
            "langgraph_auth_user": SimpleNamespace(
                identity=subject,
                is_authenticated=True,
            ),
            "langgraph_auth_permissions": ["agent.invoke_own"],
        }
    }


def _build_graph(manager, node=None, *, loop=False):
    builder = StateGraph(_CopyState)
    builder.add_node(
        "increment",
        node
        if node is not None
        else lambda state: {"count": state["count"] + 1},
    )
    builder.add_edge(START, "increment")
    builder.add_edge("increment", "increment" if loop else END)
    return agent_service._apply_graph_resource_bounds(
        builder.compile(),
        lease_manager=manager,
    )


def _variant(graph, variant):
    if variant == "copy":
        return graph.copy(update={"name": "copied-agent"})
    if variant == "with_config":
        return graph.with_config({"tags": ["copied-agent"]})
    if variant == "copy_chain":
        return graph.copy().with_config(
            {"tags": ["copied-agent"]}
        ).copy(update={"name": "recopied-agent"})
    return graph


async def _invoke(graph, invocation, run_config, value=None):
    value = {"count": 0} if value is None else value
    if invocation == "invoke":
        return graph.invoke(value, config=run_config)
    if invocation == "ainvoke":
        return await graph.ainvoke(value, config=run_config)
    if invocation == "stream":
        return list(
            graph.stream(
                value, config=run_config, stream_mode="values"
            )
        )[-1]
    return [
        chunk
        async for chunk in graph.astream(
            value, config=run_config, stream_mode="values"
        )
    ][-1]


@pytest.mark.parametrize(
    "variant", ["original", "copy", "with_config", "copy_chain"]
)
@pytest.mark.parametrize("invocation", _INVOCATIONS)
def test_copied_graph_executes_with_one_owner_lease(variant, invocation):
    manager = _RecordingLeaseManager()
    graph = _variant(_build_graph(manager), variant)

    result = asyncio.run(_invoke(graph, invocation, _authenticated_config()))

    assert isinstance(graph, CompiledStateGraph)
    assert result == {"count": 1}
    assert manager.events == [("acquire", "17"), ("release", "17")]


@pytest.fixture
def api_graphs(monkeypatch):
    monkeypatch.setenv("DATABASE_URI", ":memory:")
    monkeypatch.setenv("REDIS_URI", "redis://127.0.0.1:1/0")
    from langgraph_api import graph as api_graph

    return api_graph


@asynccontextmanager
async def _loaded_graph(original, variant, monkeypatch, api_graphs, **storage):
    if variant == "get_graph":
        graph_id = "copy-regression-agent"
        monkeypatch.setitem(api_graphs.GRAPHS, graph_id, original)
        storage.setdefault("store", None)
        async with api_graphs.get_graph(
            graph_id, {}, access_context="threads.create_run", **storage,
        ) as graph:
            yield graph
    else:
        yield _variant(original, variant)


@pytest.mark.parametrize("invocation", _INVOCATIONS)
def test_api_get_graph_preserves_lease_and_injected_storage(
    monkeypatch, api_graphs, invocation
):
    manager = _RecordingLeaseManager()

    def remember(state, runtime: Runtime):
        runtime.store.put(
            ("copy-regression",), "result",
            {"count": state["count"] + 1},
        )
        return runtime.store.get(("copy-regression",), "result").value

    original = _build_graph(manager, remember)
    checkpointer = InMemorySaver()
    store = InMemoryStore()
    run_config = _authenticated_config()
    run_config["configurable"]["thread_id"] = "copy-regression-thread"

    async def invoke_loaded_graph():
        async with _loaded_graph(
            original, "get_graph", monkeypatch, api_graphs,
            checkpointer=checkpointer, store=store,
        ) as copied:
            assert copied.checkpointer is checkpointer
            assert copied.store is store
            assert copied is not original
            result = await _invoke(copied, invocation, run_config)
            assert (await copied.aget_state(run_config)).values == result
            return result

    assert asyncio.run(invoke_loaded_graph()) == {"count": 1}
    assert original.checkpointer is None
    assert original.store is None
    assert manager.events == [("acquire", "17"), ("release", "17")]
    assert store.get(("copy-regression",), "result").value == {"count": 1}


class _OfflineChatModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class _RecordingModelCalls(BaseCallbackHandler):
    def __init__(self):
        self.calls = 0

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.calls += 1


@pytest.mark.parametrize("variant", ["original", *_COPY_VARIANTS])
@pytest.mark.parametrize("invocation", _INVOCATIONS)
def test_real_agent_factory_survives_copy(
    monkeypatch, api_graphs, variant, invocation
):
    manager = _RecordingLeaseManager()
    model_calls = _RecordingModelCalls()
    monkeypatch.setattr(agent_service, "global_agent_lease_manager", manager)
    monkeypatch.setattr(
        agent_service, "ChatOpenAI",
        lambda **kwargs: _OfflineChatModel(
            responses=["done"], callbacks=[model_calls]
        ),
    )
    monkeypatch.setattr(
        agent_service.config, "MOONSHOT_API_KEY", "fake-model-key"
    )
    original = agent_service.create_agent_graph()

    async def run_factory_graph():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            assert isinstance(graph, CompiledStateGraph)
            return await _invoke(
                graph, invocation, _authenticated_config(),
                {"messages": [HumanMessage(content="offline copy regression")]},
            )

    result = asyncio.run(run_factory_graph())
    assert result["messages"][-1].content == "done"
    assert model_calls.calls == 1
    assert manager.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", _INVOCATIONS)
def test_copy_preserves_subject_and_server_config(
    monkeypatch, api_graphs, variant, invocation
):
    seen = []
    manager = _RecordingLeaseManager()

    def inspect_config(state, config):
        seen.append(config)
        return {"count": state["count"] + 1}

    original = _build_graph(manager, inspect_config)

    async def run_two_owners():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            for subject in ("17", "18"):
                run_config = _authenticated_config(subject)
                run_config["recursion_limit"] = 999
                run_config["timeout"] = 999
                run_config["configurable"].update(
                    request_id="a" * 32,
                    langgraph_auth_user_id="999",
                    recursion_limit=999,
                    timeout=999,
                )
                await _invoke(graph, invocation, run_config)

    asyncio.run(run_two_owners())
    assert [
        cfg["configurable"]["langgraph_auth_user_id"] for cfg in seen
    ] == ["17", "18"]
    for cfg in seen:
        assert cfg["recursion_limit"] == (
            agent_service.config.AGENT_RECURSION_LIMIT
        )
        assert cfg["configurable"]["request_id"] == "a" * 32
        assert "timeout" not in cfg["configurable"]
        assert "timeout" not in cfg
    assert manager.events == [
        ("acquire", "17"), ("release", "17"),
        ("acquire", "18"), ("release", "18"),
    ]


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", _INVOCATIONS)
def test_copy_rejects_forged_identity_before_lease(
    monkeypatch, api_graphs, variant, invocation
):
    manager = _RecordingLeaseManager()
    original = _build_graph(manager)

    async def run_denied():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            await _invoke(
                graph, invocation,
                {"configurable": {"langgraph_auth_user_id": "999"}},
            )

    with pytest.raises(AgentIdentityError):
        asyncio.run(run_denied())
    assert manager.events == []


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize(
    "error_type", [AgentBusyError, AgentProtectionUnavailableError]
)
def test_copy_preserves_lease_rejection(
    monkeypatch, api_graphs, variant, error_type
):
    seen = []
    manager = _RecordingLeaseManager(error_type(retry_after=1))
    original = _build_graph(manager, lambda state: seen.append(state))

    async def run_denied():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            await _invoke(graph, "ainvoke", _authenticated_config())

    with pytest.raises(error_type):
        asyncio.run(run_denied())
    assert seen == []
    assert manager.events == []


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", _INVOCATIONS)
@pytest.mark.parametrize(
    ("raw_error", "stable_error"),
    [
        (
            ModelCallLimitExceededError(0, 9, None, 8),
            agent_service.AgentModelBudgetExceededError,
        ),
        (
            ToolCallLimitExceededError(0, 13, None, 12),
            agent_service.AgentToolBudgetExceededError,
        ),
    ],
)
def test_copy_maps_budget_errors_and_releases(
    monkeypatch, api_graphs, variant, invocation, raw_error, stable_error
):
    manager = _RecordingLeaseManager()

    def reject_budget(state):
        raise raw_error

    original = _build_graph(manager, reject_budget)

    async def run_over_budget():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            await _invoke(graph, invocation, _authenticated_config())

    with pytest.raises(stable_error):
        asyncio.run(run_over_budget())
    assert manager.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
def test_copy_enforces_recursion(monkeypatch, api_graphs, variant):
    manager = _RecordingLeaseManager()
    original = _build_graph(manager, loop=True)
    monkeypatch.setattr(agent_service.config, "AGENT_RECURSION_LIMIT", 2)

    async def run_loop():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            run_config = _authenticated_config()
            run_config["recursion_limit"] = 999
            await _invoke(graph, "ainvoke", run_config)

    with pytest.raises(GraphRecursionError, match="Recursion limit of 2"):
        asyncio.run(run_loop())
    assert manager.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", ["ainvoke", "astream"])
@pytest.mark.parametrize("completion", ["timeout", "cancel"])
def test_copy_timeout_and_cancel_release_lease(
    monkeypatch, api_graphs, variant, invocation, completion
):
    manager = _RecordingLeaseManager()
    started = asyncio.Event()
    finished = []

    async def block(state):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(True)

    original = _build_graph(manager, block)
    if completion == "timeout":
        monkeypatch.setattr(
            agent_service.config, "AGENT_RUN_TIMEOUT_SECONDS", 0.02
        )

    async def run_blocking_graph():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            task = asyncio.create_task(
                _invoke(graph, invocation, _authenticated_config())
            )
            if completion == "cancel":
                await asyncio.wait_for(started.wait(), timeout=2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(agent_service.AgentTimeoutError):
                    await task

    asyncio.run(run_blocking_graph())
    assert finished == [True]
    assert manager.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", ["stream", "astream"])
def test_copy_closing_stream_releases_lease(
    monkeypatch, api_graphs, variant, invocation
):
    manager = _RecordingLeaseManager()
    original = _build_graph(manager)

    async def close_stream():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            if invocation == "stream":
                stream = graph.stream(
                    {"count": 0},
                    config=_authenticated_config(),
                    stream_mode="values",
                )
                assert next(stream) == {"count": 0}
                stream.close()
            else:
                stream = graph.astream(
                    {"count": 0},
                    config=_authenticated_config(),
                    stream_mode="values",
                )
                assert await anext(stream) == {"count": 0}
                await stream.aclose()
            assert manager.events == [("acquire", "17"), ("release", "17")]

    asyncio.run(close_stream())


@pytest.mark.parametrize("variant", _COPY_VARIANTS)
@pytest.mark.parametrize("invocation", ["invoke", "stream"])
def test_copy_sync_deadline_releases_lease(
    monkeypatch, api_graphs, variant, invocation
):
    manager = _RecordingLeaseManager()
    now = [0.0]

    def over_deadline(state):
        now[0] += agent_service.config.AGENT_RUN_TIMEOUT_SECONDS + 1
        return {"count": state["count"] + 1}

    monkeypatch.setattr(agent_service, "perf_counter", lambda: now[0])
    original = _build_graph(manager, over_deadline)

    async def run_past_deadline():
        async with _loaded_graph(
            original, variant, monkeypatch, api_graphs
        ) as graph:
            await _invoke(graph, invocation, _authenticated_config())

    with pytest.raises(agent_service.AgentTimeoutError):
        asyncio.run(run_past_deadline())
    assert manager.events == [("acquire", "17"), ("release", "17")]


def test_falsey_injected_lease_manager_is_not_replaced():
    class _FalseyLeaseManager(_RecordingLeaseManager):
        def __bool__(self):
            return False

    manager = _FalseyLeaseManager()
    graph = _build_graph(manager).copy()

    assert graph.invoke(
        {"count": 0}, config=_authenticated_config()
    ) == {"count": 1}
    assert manager.events == [("acquire", "17"), ("release", "17")]
