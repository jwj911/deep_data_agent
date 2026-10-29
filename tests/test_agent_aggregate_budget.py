"""Actual factory + HTTP SDK regressions; provider work stays offline."""

import asyncio
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from deepagents import create_deep_agent
from langchain.agents.middleware import (ModelCallLimitMiddleware,
                                         ToolCallLimitMiddleware)
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from data_agent.models.user import User
from data_agent.services import agent_budget, agent_service
from data_agent.services.agent_lease import AgentLease, AgentLeaseManager


class _Lease(AgentLeaseManager):
    def __init__(self):
        super().__init__(client=SimpleNamespace(ping=lambda: None))
        self.events = []
        self.subjects = {}

    def acquire(self, subject):
        self.events.append(("acquire", subject))
        lease_id = f"offline-lease-{len(self.subjects)}"
        self.subjects[lease_id] = subject
        return AgentLease(lease_id, self.subject_digest(subject), 75000)

    async def acquire_async(self, subject):
        return self.acquire(subject)

    def release(self, lease):
        self.events.append(("release", self.subjects[lease.lease_id]))
        return True


def _auth(subject="17"):
    return {
        "configurable": {
            "langgraph_auth_user": SimpleNamespace(
                identity=subject, is_authenticated=True,
            ),
            "langgraph_auth_permissions": ["agent.invoke_own"],
            "model_call_limit": 999,
            "tool_call_limit": 999,
        },
        "recursion_limit": 9999,
    }


def _tool(name, index, args):
    return {
        "id": f"call-{name}-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class _Provider:
    def __init__(self, scenario, *, bounded=True):
        self.scenario = scenario
        self.bounded = bounded
        self.requests = []
        self.ledgers = []
        self._lock = Lock()

    def __call__(self, request):
        payload = json.loads(request.content)
        with self._lock:
            self.requests.append(payload)
            if self.bounded:
                self.ledgers.append(agent_budget.active_run_budget())
            attempt = len(self.requests)
        if self.scenario == "retry" and attempt % 2:
            return httpx.Response(
                500, json={"error": {"message": "offline retry control"}},
                headers={"retry-after-ms": "1"},
            )
        messages = payload["messages"]
        user = next(m["content"] for m in messages if m["role"] == "user")
        tool_results = sum(m["role"] == "tool" for m in messages)
        calls = []
        if self.scenario not in {"retry", "summary"}:
            if user.startswith("parent") and not tool_results:
                count = 2 if self.scenario == "parallel" else 1
                calls = [
                    _tool("task", i, {
                        "subagent_type": "general-purpose",
                        "description": f"child-{i}",
                    })
                    for i in range(count)
                ]
            elif user.startswith("child"):
                if self.scenario == "tool" and not tool_results:
                    calls = [
                        _tool("ls", i, {"path": "/"}) for i in range(19)
                    ]
                elif self.scenario in {"model", "parallel", "recursion"}:
                    steps = {"model": 7, "parallel": 3, "recursion": 30}
                    if tool_results < steps[self.scenario]:
                        calls = [_tool("ls", tool_results, {"path": "/"})]
        message = {"role": "assistant", "content": "offline result"}
        if calls:
            message.update(content="", tool_calls=calls)
        completion = {
            "id": f"completion-{attempt}",
            "object": "chat.completion",
            "model": "offline-model",
            "created": 1,
            "choices": [{
                "index": 0, "message": message,
                "finish_reason": "tool_calls" if calls else "stop",
            }],
            "usage": {
                "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
            },
        }
        if payload.get("stream"):
            delta = dict(message)
            if calls:
                delta["tool_calls"] = [
                    {"index": i, **call} for i, call in enumerate(calls)
                ]
            chunk = {
                **completion, "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0, "delta": delta, "finish_reason": None,
                }],
            }
            return httpx.Response(
                200, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=completion)


@pytest.fixture
def factory(monkeypatch):
    created = []

    def build(scenario, *, model_limit=8, tool_limit=12, bounded=True):
        provider = _Provider(scenario, bounded=bounded)
        transport = httpx.MockTransport(provider)
        if bounded:
            clients = agent_budget.budget_http_clients(transport)
        else:
            clients = (
                httpx.Client(transport=transport),
                httpx.AsyncClient(transport=transport),
            )
        created.extend(clients)
        lease = _Lease()
        monkeypatch.setattr(
            agent_service.config, "MOONSHOT_API_KEY", "offline-model-key",
        )
        monkeypatch.setattr(
            agent_service.config, "MODEL_BASE_URL",
            "https://model.invalid/v1",
        )
        monkeypatch.setattr(
            agent_service.config, "AGENT_MODEL_CALL_LIMIT", model_limit,
        )
        monkeypatch.setattr(
            agent_service.config, "AGENT_TOOL_CALL_LIMIT", tool_limit,
        )
        monkeypatch.setattr(
            agent_service, "budget_http_clients", lambda: clients,
        )
        monkeypatch.setattr(
            agent_service, "global_agent_lease_manager", lease,
        )
        if bounded:
            graph = agent_service.create_agent_graph()
        else:
            # Independent negative control: old default factory with only
            # the root-local limits, not an artificially flattened graph.
            graph = create_deep_agent(
                model=ChatOpenAI(
                    model="offline-model", api_key="offline-model-key",
                    base_url="https://model.invalid/v1",
                    http_client=clients[0], http_async_client=clients[1],
                ),
                middleware=[
                    ModelCallLimitMiddleware(run_limit=8, exit_behavior="error"),
                    ToolCallLimitMiddleware(run_limit=12, exit_behavior="error"),
                ],
            )
        return graph, provider, lease

    yield build
    for client in created:
        if isinstance(client, httpx.Client):
            client.close()
        else:
            asyncio.run(client.aclose())


def _run(graph, mode, value=None, auth=None):
    value = value or {"messages": [HumanMessage(content="parent")]}
    auth = auth or _auth()
    if mode == "invoke":
        return graph.invoke(value, config=auth)
    if mode == "stream":
        return list(graph.stream(value, config=auth, stream_mode="values"))[-1]

    async def run():
        if mode == "ainvoke":
            return await graph.ainvoke(value, config=auth)
        stream = graph.astream(value, config=auth, stream_mode="values")
        result = None
        try:
            while True:
                result = await asyncio.create_task(anext(stream))
        except StopAsyncIteration:
            return result
        finally:
            await asyncio.create_task(stream.aclose())

    return asyncio.run(run())


@pytest.mark.parametrize("scenario", ["model", "tool"])
def test_default_root_limits_are_a_real_negative_control(factory, scenario):
    graph, provider, _ = factory(scenario, bounded=False)
    _run(graph, "ainvoke")
    assert len(provider.requests) == (10 if scenario == "model" else 4)
    calls = sum(
        len(m.get("tool_calls", []))
        for payload in provider.requests
        for m in payload["messages"]
        if m["role"] == "assistant"
    )
    if scenario == "tool":
        # Parent task + 19 child calls are present in actual request history.
        assert calls == 20


@pytest.mark.parametrize("mode", ["invoke", "ainvoke", "stream", "astream"])
@pytest.mark.parametrize("variant", ["original", "copy", "with_config"])
@pytest.mark.parametrize(
    ("scenario", "error", "requests", "tools"),
    [
        ("model", agent_budget.AgentModelBudgetExceededError, 8, 8),
        ("tool", agent_budget.AgentToolBudgetExceededError, 2, 12),
    ],
)
def test_parent_child_hard_refusal_before_side_effect(
    factory, scenario, error, requests, tools, mode, variant,
):
    graph, provider, lease = factory(scenario)
    if variant == "copy":
        graph = graph.copy()
    elif variant == "with_config":
        graph = graph.with_config({"recursion_limit": 9999})
    with pytest.raises(error):
        _run(graph, mode)
    assert len(provider.requests) == requests
    assert {id(b) for b in provider.ledgers} == {id(provider.ledgers[0])}
    budget = provider.ledgers[0]
    assert (budget.model_requests, budget.tool_calls) == (requests, tools)
    assert lease.events == [("acquire", "17"), ("release", "17")]
    with pytest.raises(RuntimeError, match="agent_budget_context_missing"):
        agent_budget.active_run_budget()


@pytest.mark.parametrize("mode", ["invoke", "ainvoke", "stream", "astream"])
@pytest.mark.parametrize("limit", [1, 2])
def test_actual_sdk_retry_is_charged_before_send(factory, mode, limit):
    graph, provider, lease = factory("retry", model_limit=limit)
    if limit == 1:
        with pytest.raises(agent_budget.AgentModelBudgetExceededError):
            _run(graph, mode)
    else:
        assert _run(graph, mode)["messages"][-1].content == "offline result"
    assert len(provider.requests) == limit
    assert provider.ledgers[0].model_requests == limit
    assert lease.events == [("acquire", "17"), ("release", "17")]


def test_parallel_children_and_two_owners_never_share_ledger(factory):
    graph, provider, lease = factory("parallel")

    async def run():
        return await asyncio.gather(
            *(graph.ainvoke(
                {"messages": [HumanMessage(content=f"parent-{subject}")]},
                config=_auth(subject),
            ) for subject in ("17", "18")),
            return_exceptions=True,
        )

    results = asyncio.run(run())
    assert all(isinstance(r, agent_budget.AgentModelBudgetExceededError)
               for r in results)
    counts = Counter(id(b) for b in provider.ledgers)
    assert sorted(counts.values()) == [8, 8]
    assert Counter(lease.events) == Counter([
        ("acquire", "17"), ("release", "17"),
        ("acquire", "18"), ("release", "18"),
    ])


def test_atomic_preallocation_cannot_overshoot_in_worker_threads():
    with (
        pytest.raises(agent_budget.AgentToolBudgetExceededError),
        agent_budget.hold_run_budget(8, 12) as budget,
    ):
        def attempt():
            try:
                agent_budget.active_run_budget().reserve("tool")
                return True
            except agent_budget.AgentToolBudgetExceededError:
                return False

        with ThreadPoolExecutor(max_workers=16) as pool:
            tasks = [pool.submit(copy_context().run, attempt) for _ in range(64)]
            assert sum(task.result() for task in tasks) == 12
        assert budget.tool_calls == 12
        # A swallowed branch refusal must still fail the enclosing run.


def test_cancelled_request_keeps_its_reservation_before_tcp_send():
    received = []
    transport = httpx.MockTransport(lambda request: received.append(request))
    sync, client = agent_budget.budget_http_clients(transport)

    async def run():
        reserved = asyncio.Event()

        async def pause_after_reservation(request):
            reserved.set()
            await asyncio.Event().wait()

        client.event_hooks["request"].append(pause_after_reservation)
        try:
            with pytest.raises(agent_budget.AgentModelBudgetExceededError):
                with agent_budget.hold_run_budget(1, 12) as budget:
                    task = asyncio.create_task(client.get("https://model.invalid"))
                    await reserved.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert budget.model_requests == 1
                    assert not received
                    await client.get("https://model.invalid")
        finally:
            await client.aclose()

    try:
        asyncio.run(run())
    finally:
        sync.close()


@pytest.mark.parametrize("mode", ["invoke", "ainvoke", "stream", "astream"])
@pytest.mark.parametrize("limit", [1, 2])
def test_default_summary_and_main_request_share_budget(factory, mode, limit):
    graph, provider, lease = factory("summary", model_limit=limit)
    # Exercise the real default 170k-token trigger, with enough history for
    # its default six-message tail. No summary middleware is removed/replaced.
    value = {
        "messages": [
            HumanMessage(content=f"history-{i}: " + "x" * 100000)
            for i in range(8)
        ],
    }
    if limit == 1:
        with pytest.raises(agent_budget.AgentModelBudgetExceededError):
            _run(graph, mode, value)
    else:
        assert _run(graph, mode, value)["messages"][-1].content == "offline result"
    assert len(provider.requests) == limit
    assert provider.ledgers[0].model_requests == limit
    assert "Messages to summarize" in str(provider.requests[0]["messages"])
    assert lease.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("mode", ["invoke", "ainvoke"])
def test_child_recursion_is_bounded_even_with_client_override(
    factory, monkeypatch, mode,
):
    graph, provider, lease = factory("recursion")
    monkeypatch.setattr(agent_service.config, "AGENT_RECURSION_LIMIT", 4)
    with pytest.raises(GraphRecursionError, match="Recursion limit of 4"):
        _run(graph, mode)
    assert len(provider.requests) <= 4
    assert lease.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize(
    ("scenario", "error"),
    [
        ("model", agent_budget.AgentModelBudgetExceededError),
        ("tool", agent_budget.AgentToolBudgetExceededError),
    ],
)
def test_actual_service_refusal_is_not_cached_and_reuses_single_lease(
    factory, monkeypatch, scenario, error,
):
    graph, provider, lease = factory(scenario)
    cache = SimpleNamespace(
        aget=AsyncMock(return_value=None), aset=AsyncMock(),
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    with pytest.raises(error):
        asyncio.run(service.ainvoke("parent", actor=User(id=17, role="user")))
    cache.aget.assert_awaited_once()
    cache.aset.assert_not_awaited()
    assert provider.ledgers[0].model_requests == len(provider.requests)
    assert lease.events == [("acquire", "17"), ("release", "17")]


def test_aggregate_usage_event_matches_real_requests_without_payload(
    factory, caplog,
):
    graph, provider, lease = factory("success")
    _run(graph, "ainvoke")
    records = [
        r for r in caplog.records
        if getattr(r, "event_name", None) == "agent.budget.completed"
    ]
    assert len(records) == 1
    assert records[0].event_fields == {
        "outcome": "success", "model_requests": 3, "tool_calls": 1,
        "model_limit": 8, "tool_limit": 12,
    }
    assert len(provider.requests) == 3
    assert lease.events == [("acquire", "17"), ("release", "17")]


@pytest.mark.parametrize("outcome", ["close", "cancel", "timeout"])
def test_budget_lifecycle_survives_cross_task_close_and_cancellation(
    factory, monkeypatch, outcome,
):
    graph, _, lease = factory("success")
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    held = []

    async def source(self, input, config, **kwargs):
        budget = agent_budget.active_run_budget()
        held.append(budget)
        budget.reserve("model")
        try:
            entered.set()
            yield {"messages": []}
            await asyncio.Event().wait()
        finally:
            assert agent_budget.active_run_budget() is budget
            cleaned.set()

    monkeypatch.setattr(agent_service.CompiledStateGraph, "astream", source)
    monkeypatch.setattr(
        agent_service.config, "AGENT_RUN_TIMEOUT_SECONDS",
        0.02 if outcome == "timeout" else 2,
    )

    async def run():
        stream = graph.astream({}, config=_auth())
        assert await asyncio.create_task(anext(stream)) == {"messages": []}
        assert entered.is_set()
        if outcome == "close":
            await asyncio.create_task(stream.aclose())
        else:
            consumer = asyncio.create_task(anext(stream))
            if outcome == "cancel":
                await asyncio.sleep(0)
                consumer.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await consumer
                await stream.aclose()
            else:
                with pytest.raises(agent_service.AgentTimeoutError):
                    await consumer
                await stream.aclose()
        assert cleaned.is_set()
        with pytest.raises(RuntimeError, match="agent_budget_context_missing"):
            agent_budget.active_run_budget()

    asyncio.run(run())
    assert held[0].model_requests == 1
    assert lease.events == [("acquire", "17"), ("release", "17")]
