"""REST cache admission exercised through the real factory and offline SDK."""

import asyncio
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from starlette.datastructures import Headers, UploadFile
from test_agent_aggregate_budget import _tool, factory
from test_statistics_tool import _call, chat, files

from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import User, utc_now
from data_agent.services import agent_budget, agent_service
from data_agent.services.agent_lease import (get_active_agent_lease,
                                             get_active_agent_subject)
from data_agent.tools import file_statistics as statistics_tool
from data_agent.tools import search
from data_agent.tools.tool_manager import global_tool_manager


class MemoryCache:
    def __init__(self, ttl=86400):
        self.ttl = ttl
        self.values = {}
        self.reads = []
        self.writes = []

    async def aget(self, key):
        self.reads.append(key)
        return self.values.get(key)

    async def aset(self, key, value, expire):
        assert expire == self.ttl
        self.writes.append(key)
        self.values[key] = value
        return True


@pytest.fixture
def cache(monkeypatch):
    value = MemoryCache()
    monkeypatch.setattr(agent_service, "global_cache_service", value)
    return value


def invoke(service, query="ordinary question", owner=17):
    return asyncio.run(service.ainvoke(query, actor=User(id=owner, role="user")))


def assert_clean():
    assert get_active_agent_subject() is None
    assert get_active_agent_lease() is None
    assert agent_budget._answer_cache_observation.get() is None
    with pytest.raises(RuntimeError, match="agent_budget_context_missing"):
        agent_budget.active_run_budget()


def test_unknown_agent_cannot_self_report_cache_qualification(cache, factory):
    _, _, lease = factory("summary")
    fake = SimpleNamespace(ainvoke=AsyncMock(return_value={
        "messages": [AIMessage(content="unobserved", response_metadata={"finish_reason": "stop"})],
        "tool_calls": 0, "cacheable": True, "status": "success",
    }))
    service = agent_service.AgentService(agent=fake, lease_manager=lease)
    assert invoke(service) == invoke(service) == "unobserved"
    assert fake.ainvoke.await_count == 2
    assert not cache.writes
    assert_clean()


@pytest.mark.parametrize("variant", ["original", "copy", "with_config"])
def test_factory_zero_tool_success_is_cached_per_owner(cache, factory, variant):
    graph, provider, lease = factory("summary")
    if variant == "copy":
        graph = graph.copy()
    elif variant == "with_config":
        graph = graph.with_config({"configurable": {"cacheable": True}})
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    for owner in (17, 18, 17, 18):
        assert invoke(service, owner=owner) == "offline result"
    assert len(provider.requests) == 2
    assert len(set(cache.writes)) == 2
    assert all(b.tool_calls == 0 for b in provider.ledgers)
    assert len({id(b) for b in provider.ledgers}) == 2
    assert Counter(lease.events) == Counter({
        ("acquire", "17"): 2, ("release", "17"): 2,
        ("acquire", "18"): 2, ("release", "18"): 2,
    })
    assert_clean()


@pytest.mark.parametrize("query", [
    "sum __managed_file_v1__",
    'sum __managed_file_v1__{"file_id":"11111111-1111-4111-8111-111111111111"}',
    "sum file 11111111-1111-4111-8111-111111111111 amount",
])
def test_explicit_references_bypass_even_seeded_current_cache(cache, factory, query):
    graph, provider, lease = factory("summary")
    cache.values[agent_service._generate_cache_key(query, 17)] = "stale"
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service, query) == invoke(service, query) == "offline result"
    assert len(provider.requests) == 2
    assert not cache.reads and not cache.writes
    assert "stale" in cache.values.values()


def test_old_namespace_entries_are_not_read_or_cleared(cache, factory):
    graph, provider, lease = factory("summary")
    cfg = agent_service.config
    policy = ",".join(sorted(agent_service.global_tool_manager.get_tool_names()))
    material = "\n".join((
        "tenant:17", f"model:{cfg.MODEL_NAME}", f"base_url:{cfg.MODEL_BASE_URL}",
        f"temperature:{cfg.MODEL_TEMPERATURE}",
        f"tool_policy:{agent_service._TOOL_POLICY_VERSION}:{policy}",
        "query:ordinary question",
    ))
    old_key = "agent:" + hashlib.sha256(material.encode()).hexdigest()
    cache.values.update({old_key: "old answer", "search:sentinel": {"results": []}})
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service) == invoke(service) == "offline result"
    assert len(provider.requests) == 1
    assert old_key not in cache.reads
    assert cache.values[old_key] == "old answer"
    assert cache.values["search:sentinel"] == {"results": []}


@pytest.mark.parametrize("change", ["delete", "expire", "drift"])
@pytest.mark.parametrize("media", ["csv", "json"])
@pytest.mark.parametrize("explicit", [False, True])
def test_file_success_then_invalidation_rechecks_actual_source(
    cache, chat, files, change, media, explicit,
):
    db_factory, users, storage, _ = files
    graph, provider, lease = chat
    content = b"amount\n0.1\n0.2\n" if media == "csv" else b'[{"amount":0.1},{"amount":0.2}]'
    with db_factory() as db:
        record = asyncio.run(storage.upload_files(db, users[0], [
            UploadFile(file=BytesIO(content), filename=f"sample.{media}",
                       headers=Headers({"content-type": "text/csv" if media == "csv" else "application/json"})),
        ]))[0]
    query = f"sum __managed_file_v1__ {record.file_id}" if explicit else "calculate the selected amount"
    provider.plans[query] = [[_call(record)]]
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service, query, users[0].id) == "offline result"
    success = json.loads(next(m["content"] for m in provider.requests[-1]["messages"] if m["role"] == "tool"))
    assert success["status"] == "success"
    assert success["data"]["result"]["value"] == "0.3"
    with db_factory() as db:
        stored = db.query(ManagedFile).filter_by(file_id=record.file_id).one()
        if change == "delete":
            storage.delete_file(db, users[0], record.file_id)
        elif change == "expire":
            stored.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        else:
            (Path(agent_service.config.FILE_STORAGE_ROOT) / stored.storage_key).write_bytes(
                content.replace(b"0.2", b"9.2"),
            )
    assert invoke(service, query, users[0].id) == "offline result"
    assert len(provider.requests) == 4
    error = json.loads(next(m["content"] for m in provider.requests[-1]["messages"] if m["role"] == "tool"))
    assert error["status"] == "error" and "data" not in error
    assert error["error"]["code"] == (
        "file_storage_invalid" if change == "drift" else "managed_file_not_found"
    )
    assert not cache.writes
    assert len(cache.reads) == (0 if explicit else 2)
    assert_clean()


@pytest.mark.parametrize("scenario", ["child", "parallel", "builtin"])
def test_actual_tools_not_final_text_determine_admission(cache, chat, files, scenario):
    _, users, _, store = files
    graph, provider, lease = chat
    record = store()
    if scenario == "builtin":
        provider.plans["parent"] = [[_tool("ls", 0, {"path": "/"})]]
        expected_tools = 1
    else:
        count = 2 if scenario == "parallel" else 1
        provider.plans["parent"] = [[_tool("task", i, {
            "subagent_type": "general-purpose", "description": f"child-{i}",
        }) for i in range(count)]]
        for i in range(count):
            provider.plans[f"child-{i}"] = [[_call(record, i)]]
        expected_tools = count * 2
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    for _ in range(2):
        assert invoke(service, "parent", users[0].id) == "offline result"
    assert {b.tool_calls for b in provider.ledgers} == {expected_tools}
    assert len({id(b) for b in provider.ledgers}) == 2
    assert not cache.writes
    assert_clean()


@pytest.mark.parametrize("field", ["MODEL_NAME", "MODEL_BASE_URL", "MODEL_TEMPERATURE"])
def test_cache_key_keeps_model_configuration_isolation(cache, factory, monkeypatch, field):
    graph, provider, lease = factory("summary")
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service) == "offline result"
    old = getattr(agent_service.config, field)
    monkeypatch.setattr(agent_service.config, field, 0.123 if field == "MODEL_TEMPERATURE" else f"{old}-changed")
    assert invoke(service) == "offline result"
    assert len(provider.requests) == 2
    assert len(set(cache.writes)) == 2


@pytest.mark.parametrize("failure", [False, True])
def test_search_execution_bypasses_answer_cache_but_retains_search_cache(
    cache, chat, files, monkeypatch, failure,
):
    graph, provider, lease = chat
    _, users, _, _ = files
    search_cache = MemoryCache(ttl=3600)
    search_client = SimpleNamespace(search=AsyncMock(
        side_effect=RuntimeError("offline failure") if failure else None,
        return_value={"results": [{"title": "public", "content": "offline"}]},
    ))
    monkeypatch.setattr(search, "global_cache_service", search_cache)
    monkeypatch.setattr(search, "_get_tavily_client", lambda: search_client)
    monkeypatch.setattr(agent_service.config, "TAVILY_API_KEY", "offline-search-key")
    provider.plans["parent"] = [[_tool("internet_search", 0, {"query": "public query"})]]
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert len(provider.requests) == 4
    assert {b.tool_calls for b in provider.ledgers} == {1}
    assert not cache.writes
    assert search_client.search.await_count == (2 if failure else 1)
    assert len(search_cache.writes) == (0 if failure else 1)
    assert len(search_cache.reads) == 2


@pytest.mark.parametrize("owner", [0, 1, 2])
def test_implicit_file_tool_owner_and_failure_are_never_cached(cache, chat, files, owner):
    _, users, _, store = files
    graph, provider, lease = chat
    provider.plans["parent"] = [[_call(store())]]
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service, "parent", users[owner].id) == "offline result"
    assert invoke(service, "parent", users[owner].id) == "offline result"
    result = json.loads(next(m["content"] for m in provider.requests[-1]["messages"] if m["role"] == "tool"))
    assert result["status"] == ("success" if owner == 0 else "error")
    if owner:
        assert result["error"]["code"] == "managed_file_not_found"
        assert "data" not in result
    assert len(provider.requests) == 4
    assert not cache.writes


@pytest.mark.parametrize("mode", ["invoke", "stream", "astream"])
@pytest.mark.parametrize("tools", [False, True])
def test_observation_survives_sync_workers_and_cross_task_streams(
    cache, chat, files, mode, tools, monkeypatch,
):
    _, users, storage, store = files
    graph, provider, lease = chat
    record = store()
    if tools:
        provider.plans["parent"] = [[_call(record)]]
    worker_evidence = []
    original = storage.file_statistics
    main_thread = get_ident()

    def calculate(*args):
        worker_evidence.append((
            get_ident(), agent_budget.active_run_budget(), get_active_agent_subject(),
        ))
        return original(*args)

    monkeypatch.setattr(storage, "file_statistics", calculate)

    async def run(value, config):
        if mode == "invoke":
            return await asyncio.to_thread(graph.invoke, value, config=config)
        if mode == "stream":
            return await asyncio.to_thread(
                lambda: list(graph.stream(value, config=config, stream_mode="values"))[-1],
            )
        chunks = graph.astream(value, config=config, stream_mode="values")
        result = None
        try:
            while True:
                result = await asyncio.create_task(anext(chunks))
        except StopAsyncIteration:
            return result
        finally:
            await asyncio.create_task(chunks.aclose())

    service = agent_service.AgentService(
        agent=SimpleNamespace(ainvoke=run), lease_manager=lease,
    )
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert len(provider.requests) == (4 if tools else 1)
    assert len(cache.writes) == (0 if tools else 1)
    if tools:
        assert len(worker_evidence) == 2
        assert all(t != main_thread and b in provider.ledgers and b.tool_calls == 1
                   and s == str(users[0].id) for t, b, s in worker_evidence)
    assert_clean()


@pytest.mark.parametrize("finish_reason", ["length", "content_filter", None])
def test_partial_or_unknown_model_completion_not_cached(
    cache, factory, monkeypatch, finish_reason,
):
    graph, provider, lease = factory("summary")
    original = type(provider).__call__

    def respond(self, request):
        response = original(self, request)
        payload = response.json()
        payload["choices"][0]["finish_reason"] = finish_reason
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(type(provider), "__call__", respond)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service) == invoke(service) == "offline result"
    assert len(provider.requests) == 2
    assert not cache.writes


def test_bounded_graph_without_tool_observer_is_unknown(cache, factory):
    _, _, lease = factory("summary")
    builder = StateGraph(MessagesState)
    builder.add_node("unobserved", lambda _state: {
        "messages": [AIMessage(content="unobserved", response_metadata={"finish_reason": "stop"})],
    })
    builder.add_edge(START, "unobserved")
    builder.add_edge("unobserved", END)
    graph = agent_service._apply_graph_resource_bounds(builder.compile(), lease_manager=lease)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service) == invoke(service) == "unobserved"
    assert not cache.writes


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("interrupt", ["configured", "argument"])
def test_real_graph_interrupt_after_model_is_not_success_cache(cache, factory, mode, interrupt):
    graph, provider, lease = factory("summary")
    kwargs = {}
    if interrupt == "configured":
        graph = graph.copy(update={"interrupt_after_nodes": ["model"]})
    else:
        kwargs["interrupt_after"] = ["model"]

    async def run(value, config):
        if mode == "sync":
            return await asyncio.to_thread(graph.invoke, value, config=config, **kwargs)
        return await graph.ainvoke(value, config=config, **kwargs)

    service = agent_service.AgentService(agent=SimpleNamespace(ainvoke=run), lease_manager=lease)
    assert invoke(service) == invoke(service) == "offline result"
    assert len(provider.requests) == 2
    assert not cache.writes


@pytest.mark.parametrize("scenario", ["model", "tool"])
def test_real_budget_refusal_never_writes_cache(cache, factory, scenario):
    graph, provider, lease = factory(scenario)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    error = (agent_budget.AgentModelBudgetExceededError if scenario == "model"
             else agent_budget.AgentToolBudgetExceededError)
    for _ in range(2):
        with pytest.raises(error):
            invoke(service, "parent")
    assert len({id(b) for b in provider.ledgers}) == 2
    assert not cache.writes
    assert lease.events == [("acquire", "17"), ("release", "17")] * 2
    assert_clean()


@pytest.mark.parametrize("outcome", ["cancel", "timeout"])
def test_late_successful_file_work_after_abort_cannot_cache_and_retry_is_fresh(
    cache, chat, files, monkeypatch, outcome,
):
    _, users, storage, store = files
    graph, provider, lease = chat
    provider.plans["parent"] = [[_call(store())]]
    entered, finish, ended = Event(), Event(), Event()
    original = storage.file_statistics
    worker_futures = []
    submit = statistics_tool._executor.submit

    def record_submit(*args, **kwargs):
        future = submit(*args, **kwargs)
        worker_futures.append(future)
        return future

    monkeypatch.setattr(statistics_tool._executor, "submit", record_submit)

    def calculate(*args):
        result = original(*args)
        entered.set()
        try:
            assert finish.wait(5), "test must release worker"
            return result
        finally:
            ended.set()

    monkeypatch.setattr(storage, "file_statistics", calculate)
    monkeypatch.setattr(agent_service.config, "AGENT_RUN_TIMEOUT_SECONDS", 0.5 if outcome == "timeout" else 5)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)

    async def abort_and_retry():
        actor = users[0]
        task = asyncio.create_task(service.ainvoke("parent", actor=actor))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            if outcome == "cancel":
                task.cancel()
            with pytest.raises(
                asyncio.CancelledError if outcome == "cancel" else agent_service.AgentTimeoutError,
            ):
                await task
        finally:
            finish.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(ended.wait, 3)
        # Waiting for the read/compute gate alone is insufficient: join the
        # actual _calculate Future, including its successful result wrapper.
        assert len(worker_futures) == 1
        late_result = await asyncio.to_thread(worker_futures[0].result, timeout=3)
        assert worker_futures[0].done() and late_result["status"] == "success"
        await asyncio.sleep(0)
        assert not cache.writes
        assert len(provider.requests) == 1
        assert await service.ainvoke("parent", actor=actor) == "offline result"

    asyncio.run(abort_and_retry())
    assert len(provider.requests) == 3
    assert len({id(b) for b in provider.ledgers}) == 2
    assert not cache.writes
    assert lease.events == [("acquire", str(users[0].id)), ("release", str(users[0].id))] * 2
    assert_clean()


def test_concurrent_owners_do_not_share_cache_observation(cache, chat, files):
    _, users, _, store = files
    graph, provider, lease = chat
    provider.plans["with tools"] = [[_call(store())]]
    service = agent_service.AgentService(agent=graph, lease_manager=lease)

    async def run():
        for _ in range(2):
            assert await asyncio.gather(
                service.ainvoke("with tools", actor=users[0]),
                service.ainvoke("without tools", actor=users[1]),
            ) == ["offline result"] * 2

    asyncio.run(run())
    assert len(provider.requests) == 5
    assert cache.writes == [agent_service._generate_cache_key("without tools", users[1].id)]
    assert len({id(b) for b in provider.ledgers}) == 3
    assert_clean()


@pytest.mark.parametrize("child_work", ["none", "tool", "refusal"])
def test_nested_graph_scope_cannot_hide_child_evidence(
    cache, factory, monkeypatch, child_work,
):
    child, child_provider, _ = factory("summary", tool_limit=1)
    parent, provider, lease = factory("summary")

    def child_calls(payload):
        if child_work == "none" or any(m["role"] == "tool" for m in payload["messages"]):
            return []
        return [_tool("ls", i, {"path": "/"}) for i in range(2 if child_work == "refusal" else 1)]

    def parent_calls(_payload):
        parent_budget = agent_budget.active_run_budget()
        try:
            child.invoke({"messages": [HumanMessage(content="child")]})
        except agent_budget.AgentToolBudgetExceededError:
            assert child_work == "refusal"
        assert agent_budget.active_run_budget() is parent_budget
        assert get_active_agent_subject() == "17"
        return []

    monkeypatch.setattr(child_provider, "_calls", child_calls)
    monkeypatch.setattr(provider, "_calls", parent_calls)
    service = agent_service.AgentService(agent=parent, lease_manager=lease)
    assert invoke(service) == invoke(service) == "offline result"
    assert {b.tool_calls for b in provider.ledgers} == {0}
    assert len(provider.requests) == (1 if child_work == "none" else 2)
    assert len(cache.writes) == (1 if child_work == "none" else 0)
    assert all(b not in provider.ledgers for b in child_provider.ledgers)
    assert lease.events == [("acquire", "17"), ("release", "17")] * 2
    assert_clean()


def test_closing_real_stream_after_ai_text_is_not_complete_run(cache, factory):
    graph, provider, lease = factory("summary")

    def partial(value, config):
        stream = graph.stream(value, config=config, stream_mode="values")
        try:
            for state in stream:
                if isinstance(state["messages"][-1], AIMessage):
                    return state
        finally:
            stream.close()

    async def run(value, config):
        return await asyncio.to_thread(partial, value, config)

    service = agent_service.AgentService(agent=SimpleNamespace(ainvoke=run), lease_manager=lease)
    assert invoke(service) == invoke(service) == "offline result"
    assert len(provider.requests) == 2
    assert not cache.writes
    assert_clean()


def test_worker_tool_execution_is_counted_without_any_model_tool_messages(
    cache, chat, files, monkeypatch,
):
    graph, provider, lease = chat
    _, users, _, store = files
    record = store()
    tool = global_tool_manager.get_tool("analyze_file_statistics")
    middleware = agent_budget.AggregateToolBudgetMiddleware()
    executed = []

    def hidden_tools(_payload):
        def execute():
            result = middleware.wrap_tool_call(None, lambda _request: tool.invoke({
                "file_id": record.file_id, "column": "amount",
            }))
            executed.append(result)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(copy_context().run, execute) for _ in range(2)]
            for task in tasks:
                task.result()
        return []

    monkeypatch.setattr(provider, "_calls", hidden_tools)
    service = agent_service.AgentService(agent=graph, lease_manager=lease)
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert invoke(service, "parent", users[0].id) == "offline result"
    assert len(executed) == 4
    assert all(result["status"] == "success" for result in executed)
    assert len(provider.requests) == 2
    assert all(m["role"] != "tool" and not m.get("tool_calls")
               for p in provider.requests for m in p["messages"])
    assert {b.tool_calls for b in provider.ledgers} == {2}
    assert not cache.writes
    assert_clean()
