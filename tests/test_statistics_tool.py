"""Real factory/SDK tool dispatch with offline provider and managed files."""

import asyncio
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from threading import Barrier, BoundedSemaphore, Event, Lock, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import test_agent_aggregate_budget as budget_tests
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.config import get_stream_writer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers, UploadFile
from test_agent_aggregate_budget import _auth, _run, _tool, factory
from test_file_statistics import api

from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import Base, User, utc_now
from data_agent.services import (agent_budget, agent_service,
                                 authorization_service)
from data_agent.services.agent_lease import (get_active_agent_lease,
                                             get_active_agent_subject)
from data_agent.services.managed_file_service import ManagedFileService
from data_agent.tools import file_statistics as tool_module
from data_agent.tools.tool_manager import global_tool_manager

TOOL = "analyze_file_statistics"
MODES = ["invoke", "ainvoke", "stream", "astream"]
VARIANTS = ["original", "copy", "with_config"]


@pytest.fixture
def files(tmp_path, monkeypatch):
    # Parallel graph branches need independent connections, not StaticPool's
    # single shared in-memory SQLite connection.
    engine = create_engine(f"sqlite:///{(tmp_path / 'files.db').as_posix()}")
    db_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(agent_service.config, "FILE_STORAGE_ROOT", str(tmp_path / "files"))
    with db_factory() as db:
        users = [
            User(username=f"stat-{i}", email=f"stat-{i}@example.test",
                 hashed_password="test-hash", role=role)
            for i, role in enumerate(["user", "user", "admin"])
        ]
        db.add_all(users)
        db.commit()
        for user in users:
            db.expunge(user)
    service = ManagedFileService()

    def store(content=b"amount,label\n0.1,a\n0.2,b\n"):
        with db_factory() as db:
            return asyncio.run(service.upload_files(db, users[0], [
                UploadFile(file=BytesIO(content), filename="sample.csv",
                           headers=Headers({"content-type": "text/csv"})),
            ]))[0]

    try:
        yield db_factory, users, service, store
    finally:
        engine.dispose()


class _StatisticsProvider(budget_tests._Provider):
    def _calls(self, payload):
        messages = payload["messages"]
        user = next(m["content"] for m in messages if m["role"] == "user")
        step = sum(bool(m.get("tool_calls")) for m in messages)
        batches = self.plans.get(user, [])
        return batches[step] if step < len(batches) else []


@pytest.fixture
def chat(files, factory, monkeypatch):
    db_factory, users, service, store = files
    monkeypatch.setattr(budget_tests, "_Provider", _StatisticsProvider)
    monkeypatch.setattr(tool_module, "get_session_factory", lambda: db_factory)
    monkeypatch.setattr(tool_module, "global_managed_file_service", service)
    # Each test owns its pool and waits for abandoned synchronous work.
    pool = ThreadPoolExecutor(max_workers=4)
    monkeypatch.setattr(tool_module, "_executor", pool)
    monkeypatch.setattr(tool_module, "_slots", BoundedSemaphore(4))
    graph, provider, lease = factory("statistics")
    provider.plans = {}
    try:
        yield graph, provider, lease
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _call(record, index=0, **overrides):
    return _tool(TOOL, index, {
        "file_id": record.file_id, "column": "amount", **overrides,
    })


def _variant(graph, variant):
    if variant == "copy":
        return graph.copy()
    if variant == "with_config":
        return graph.with_config({
            "recursion_limit": 9999,
            "configurable": {"langgraph_auth_user_id": "999", "tool_call_limit": 999},
        })
    return graph


def _result(state):
    messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert messages
    message = messages[-1]
    assert message.name == TOOL
    assert message.tool_call_id
    return message, json.loads(message.content)


def _run_chat(chat, users, mode="ainvoke", *, variant="original", subject=None):
    graph, _, _ = chat
    auth = _auth(str(users[0].id) if subject is None else str(subject))
    auth["configurable"]["langgraph_auth_user_id"] = str(users[0].id)
    return _run(_variant(graph, variant), mode, auth=auth)


def _assert_clean():
    assert get_active_agent_subject() is None
    assert get_active_agent_lease() is None
    with pytest.raises(RuntimeError, match="agent_budget_context_missing"):
        agent_budget.active_run_budget()


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("media", ["csv", "json"])
def test_full_file_factory_rest_and_independent_reference(
    chat, files, api, media, mode, variant,
):
    db_factory, users, service, _ = files
    graph, provider, lease = chat
    values = ["0.1", "0.2"] * 6000 + ["999.123456789012345678"]
    if media == "csv":
        content = ("amount\n" + "\n".join(values)).encode()
        mime = "text/csv"
    else:
        content = ("[" + ",".join('{"amount":' + v + "}" for v in values) + "]").encode()
        mime = "application/json"
    assert len(content) > 20_000
    with db_factory() as db:
        record = asyncio.run(service.upload_files(db, users[0], [
            UploadFile(file=BytesIO(content), filename=f"sample.{media}",
                       headers=Headers({"content-type": mime})),
        ]))[0]
    provider.plans["parent"] = [[_call(record)]]
    message, wrapper = _result(_run_chat(chat, users, mode, variant=variant))
    assert message.status == "success"
    assert set(wrapper) == {"type", "version", "status", "data"}
    assert wrapper["type"] == "managed_file_statistics"
    assert type(wrapper["version"]) is int and wrapper["version"] == 1
    assert wrapper["status"] == "success"
    _, request = api
    response = request(f"/api/files/{record.file_id}/statistics")
    assert response.status_code == 200
    payload = wrapper["data"]
    assert payload == response.json()
    assert Fraction(payload["result"]["value"]) == sum(map(Fraction, values))
    assert payload["row_count"] == len(values)
    canonical = {k: v for k, v in payload.items() if k != "result_sha256"}
    assert payload["result_sha256"] == hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()
    assert len(provider.requests) == 2
    assert provider.ledgers[0].tool_calls == 1
    assert lease.events == [("acquire", str(users[0].id)), ("release", str(users[0].id))]
    _assert_clean()


@pytest.mark.parametrize("extra", [
    "owner", "user_id", "path", "expression", "metric", "tool_call_limit",
    "config", "context", "langgraph_auth_user_id",
])
def test_model_schema_rejects_extra_keys_before_read(chat, files, monkeypatch, extra):
    _, users, service, store = files
    _, provider, _ = chat
    record = store()
    provider.plans["parent"] = [[_call(record, **{extra: "untrusted"})]]
    monkeypatch.setattr(service, "_read_bytes", lambda _record: pytest.fail("read"))
    message, wrapper = _result(_run_chat(chat, users))
    assert message.status == "error"
    assert wrapper["error"]["code"] == "analysis_invalid_arguments"
    assert "data" not in wrapper
    schema = next(t["function"]["parameters"] for t in provider.requests[0]["tools"]
                  if t["function"]["name"] == TOOL)
    assert set(schema["properties"]) == set(schema["required"]) == {"file_id", "column"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["column"]["minLength"] == 1
    assert schema["properties"]["column"]["maxLength"] == 128
    assert provider.ledgers[0].tool_calls == 1


@pytest.mark.parametrize("overrides", [
    {"file_id": "ABCDEFAB-1111-4111-8111-111111111111"},
    {"file_id": "11111111111141118111111111111111"},
    {"file_id": "../outside"}, {"file_id": 1},
    {"column": ""}, {"column": "x" * 129}, {"column": 1},
])
def test_strict_parameters(chat, files, overrides):
    _, users, _, store = files
    _, provider, _ = chat
    provider.plans["parent"] = [[_call(store(), **overrides)]]
    message, wrapper = _result(_run_chat(chat, users))
    assert message.status == "error"
    assert wrapper["error"]["code"] == "analysis_invalid_arguments"
    assert "data" not in wrapper


@pytest.mark.parametrize("identity", ["owner", "other", "admin", "deleted", "role"])
def test_current_identity_and_owner_are_revalidated(chat, files, monkeypatch, identity):
    db_factory, users, _, store = files
    _, provider, lease = chat
    record = store()
    provider.plans["parent"] = [[_call(record)]]
    subject = users[0].id
    if identity in {"other", "admin", "deleted"}:
        subject = users[2 if identity == "admin" else 1].id
    if identity in {"deleted", "role"}:
        with db_factory() as db:
            actor = db.get(User, subject)
            if identity == "deleted":
                db.delete(actor)
            else:
                actor.role = "admin"
                # Both real roles normally grant file reads. Revoke one only
                # in this test to make a stale-role read observably unsafe.
                monkeypatch.setitem(
                    authorization_service.ROLE_PERMISSIONS, "admin", frozenset(),
                )
            db.commit()
    message, wrapper = _result(_run_chat(chat, users, subject=subject))
    if identity == "owner":
        assert wrapper["status"] == "success"
    else:
        assert message.status == "error"
        assert wrapper["error"]["code"] == "managed_file_not_found"
        assert "data" not in wrapper
        assert record.file_id not in json.dumps(wrapper)
    assert lease.events == [("acquire", str(subject)), ("release", str(subject))]
    _assert_clean()


def test_config_alone_cannot_supply_tool_subject(chat, files):
    _, users, _, store = files
    record = store()
    tool = global_tool_manager.get_tool(TOOL)
    result = tool.invoke(
        {"file_id": record.file_id, "column": "amount"}, config=_auth(str(users[0].id)),
    )
    assert json.loads(result)["error"]["code"] == "managed_file_auth_required"


def test_unavailable_worker_pool_returns_safe_error(chat, files, monkeypatch):
    _, users, _, store = files
    _, provider, _ = chat
    provider.plans["parent"] = [[_call(store())]]

    def fail(*args):
        raise RuntimeError("private executor detail")

    monkeypatch.setattr(tool_module._executor, "submit", fail)
    message, wrapper = _result(_run_chat(chat, users))
    assert message.status == "error"
    assert wrapper["error"]["code"] == "analysis_error"
    assert "data" not in wrapper and "private" not in message.content


@pytest.mark.parametrize(("change", "code"), [
    ("column", "analysis_column_not_found"),
    ("numeric", "analysis_non_numeric"),
    ("delete", "managed_file_not_found"),
    ("expire", "managed_file_not_found"),
    ("tamper", "file_storage_invalid"),
    ("unknown", "analysis_error"),
])
def test_stable_failure_no_payload_or_sensitive_details(chat, files, monkeypatch, change, code):
    db_factory, users, service, store = files
    _, provider, _ = chat
    record = store(b"amount\nprivate-cell\n" if change == "numeric" else b"amount\n1\n")
    provider.plans["parent"] = [[_call(record, column="absent" if change == "column" else "amount")]]
    if change in {"delete", "expire", "tamper"}:
        with db_factory() as db:
            stored = db.query(ManagedFile).filter_by(file_id=record.file_id).one()
            if change == "delete":
                service.delete_file(db, users[0], record.file_id)
            elif change == "expire":
                stored.expires_at = utc_now() - timedelta(seconds=1)
                db.commit()
            else:
                (Path(agent_service.config.FILE_STORAGE_ROOT) / stored.storage_key).write_bytes(
                    b"amount\n9\n",
                )
    if change == "unknown":
        def fail(*args):
            raise RuntimeError("private-cell D:/private/source.csv")
        monkeypatch.setattr(service, "file_statistics", fail)
    message, wrapper = _result(_run_chat(chat, users))
    assert message.status == wrapper["status"] == "error"
    assert wrapper["error"]["code"] == code
    assert "data" not in wrapper
    assert "private" not in message.content


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("child", [False, True])
def test_thirteenth_call_refused_before_file_read(chat, files, monkeypatch, mode, variant, child):
    _, users, service, store = files
    _, provider, lease = chat
    record = store()
    reads = []
    original = service._read_bytes

    def read(record):
        reads.append((get_active_agent_subject(), agent_budget.active_run_budget()))
        return original(record)

    monkeypatch.setattr(service, "_read_bytes", read)
    # One inline task costs one unit, leaving exactly eleven statistics calls.
    counts = [3, 3, 3, 2, 1] if child else [3, 3, 3, 3, 1]
    batches = [[_call(record, f"{step}-{i}") for i in range(count)]
               for step, count in enumerate(counts)]
    provider.plans["child"] = batches
    provider.plans["parent"] = [[_tool("task", 0, {
        "subagent_type": "general-purpose", "description": "child",
    })]] if child else batches
    with pytest.raises(agent_budget.AgentToolBudgetExceededError):
        _run_chat(chat, users, mode, variant=variant)
    budget = provider.ledgers[0]
    assert len(reads) == (11 if child else 12)
    assert budget.tool_calls == 12 and budget.model_limit == 8
    assert budget.tool_limit == 12 and len(provider.requests) <= 8
    assert all(subject == str(users[0].id) and ledger is budget for subject, ledger in reads)
    assert all(b is budget for b in provider.ledgers)
    assert lease.events == [("acquire", str(users[0].id)), ("release", str(users[0].id))]
    _assert_clean()


def test_failed_calls_also_exhaust_budget(chat, files):
    _, users, _, store = files
    _, provider, _ = chat
    record = store()
    provider.plans["parent"] = [
        [_call(record, f"{step}-{i}", column="missing") for i in range(count)]
        for step, count in enumerate([3, 3, 3, 3, 1])
    ]
    with pytest.raises(agent_budget.AgentToolBudgetExceededError):
        _run_chat(chat, users)
    errors = [m for m in provider.requests[-1]["messages"] if m["role"] == "tool"]
    assert len(errors) == 12
    assert all(json.loads(m["content"])["status"] == "error" for m in errors)
    assert provider.ledgers[0].tool_calls == 12


def test_parent_and_children_parallel_share_context_and_prompt(chat, files, monkeypatch):
    _, users, service, store = files
    _, provider, _ = chat
    record = store()
    provider.plans["parent"] = [[
        _call(record, "parent"),
        *[_tool("task", i, {"subagent_type": "general-purpose", "description": f"child-{i}"})
          for i in range(2)],
    ]]
    for i in range(2):
        provider.plans[f"child-{i}"] = [[_call(record, f"child-{i}")]]
    barrier = Barrier(3)
    seen = []
    original = service._read_bytes

    def read(record):
        seen.append((get_active_agent_subject(), agent_budget.active_run_budget(), get_ident()))
        barrier.wait(timeout=5)
        return original(record)

    monkeypatch.setattr(service, "_read_bytes", read)
    _run_chat(chat, users)
    assert len(seen) == len({thread for _, _, thread in seen}) == 3
    assert all(subject == str(users[0].id) and budget is provider.ledgers[0]
               for subject, budget, _ in seen)
    assert provider.ledgers[0].tool_calls == 5
    for request in provider.requests:
        prompt = str([m for m in request["messages"] if m["role"] == "system"])
        assert "ask the user to clarify" in prompt
        assert "Never default to" in prompt
        assert "analyze_document" in prompt
    _assert_clean()


def test_parallel_runs_isolate_owners_and_budgets(chat, files):
    db_factory, users, service, store = files
    graph, provider, lease = chat
    first = store()
    with db_factory() as db:
        second = asyncio.run(service.upload_files(db, users[1], [
            UploadFile(file=BytesIO(b"amount\n8\n"), filename="other.csv",
                       headers=Headers({"content-type": "text/csv"})),
        ]))[0]
    for i, record in enumerate([first, second]):
        provider.plans[f"owner-{i}"] = [[_call(record, i)]]

    async def run():
        return await asyncio.gather(*[
            graph.ainvoke({"messages": [HumanMessage(content=f"owner-{i}")]},
                          config=_auth(str(users[i].id)))
            for i in range(2)
        ])

    results = asyncio.run(run())
    assert [_result(r)[1]["data"]["result"]["value"] for r in results] == ["0.3", "8"]
    assert sorted(Counter(id(b) for b in provider.ledgers).values()) == [2, 2]
    assert Counter(lease.events) == Counter(
        (event, str(u.id)) for u in users[:2] for event in ["acquire", "release"]
    )
    _assert_clean()


async def _wait(event):
    assert await asyncio.to_thread(event.wait, 5), "worker event did not arrive"


class _StatisticsToolEvents(BaseCallbackHandler):
    run_inline = True
    raise_error = True

    def __init__(self):
        self.started = []
        self.ended = []

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self.started.append(run_id)

    def on_tool_end(self, output, *, run_id, **kwargs):
        self.ended.append((run_id, output))

def _assert_statistics_slots(available):
    slots = tool_module._slots
    acquired = [slots.acquire(blocking=False) for _ in range(5)]
    try:
        assert sum(acquired) == available
    finally:
        for held in acquired:
            if held:
                slots.release()


@pytest.mark.parametrize("outcome", ["cancel", "timeout", "close"])
@pytest.mark.parametrize("variant", VARIANTS)
def test_actual_slow_read_lifecycle_has_no_late_delivery(
    chat, files, monkeypatch, outcome, variant,
):
    _, users, service, store = files
    graph, provider, lease = chat
    graph = _variant(graph, variant)
    record = store()
    provider.plans["parent"] = [[_call(record)]]
    entered, release = Event(), Event()
    calculated, finish_worker = Event(), Event()
    original = service._read_bytes
    statistics = service.file_statistics
    threads = []

    def read(record):
        threads.append(get_ident())
        entered.set()
        assert release.wait(5), "test must release the real file read"
        return original(record)

    def calculate(*args):
        payload = statistics(*args)
        calculated.set()
        # BCV-01: reading is not worker completion. Hold the real payload
        # before _calculate closes its DB session and builds the tool wrapper.
        assert finish_worker.wait(5), "test must release the complete worker"
        return payload

    monkeypatch.setattr(service, "_read_bytes", read)
    monkeypatch.setattr(service, "file_statistics", calculate)
    monkeypatch.setattr(agent_service.config, "AGENT_RUN_TIMEOUT_SECONDS",
                        0.3 if outcome == "timeout" else 10)
    cache = SimpleNamespace(aget=AsyncMock(return_value=None), aset=AsyncMock())
    monkeypatch.setattr(agent_service, "global_cache_service", cache)
    service_entry = agent_service.AgentService(agent=graph, lease_manager=lease)
    delivered = []
    events = _StatisticsToolEvents()
    monkeypatch.setattr(global_tool_manager.get_tool(TOOL), "callbacks", [events])
    workers = []
    submit = tool_module._submit

    def observe_submission(*args):
        future = submit(*args)
        callbacks_done = Event()
        # Registered after the real slot-release callback, not at read exit.
        future.add_done_callback(lambda _: callbacks_done.set())
        workers.append((future, callbacks_done))
        if outcome == "close":
            get_stream_writer()({"statistics_submitted": True})
        return future

    monkeypatch.setattr(tool_module, "_submit", observe_submission)

    async def join_workers():
        results = []
        for future, callbacks_done in workers:
            await _wait(callbacks_done)
            assert future.done() and not future.cancelled()
            # Join the actual concurrent Future on the still-live event loop,
            # including its result/exception and queued asyncio bridge callback.
            results.append(await asyncio.wait_for(asyncio.wrap_future(future), 5))
        return results

    async def run():
        stream = None
        task = None
        try:
            if outcome == "close":
                stream = graph.astream(
                    {"messages": [HumanMessage(content="parent")]},
                    config=_auth(str(users[0].id)), stream_mode=["values", "custom"],
                )
                # Drain middleware updates too, then close while real work is
                # running, not while the producer is blocked by stream backpressure.
                async with asyncio.timeout(5):
                    while True:
                        mode, state = await asyncio.create_task(anext(stream))
                        if mode == "custom":
                            assert state == {"statistics_submitted": True}
                            break
                        delivered.append(state)
                await _wait(entered)
                await asyncio.wait_for(asyncio.create_task(stream.aclose()), 5)
            else:
                task = asyncio.create_task(service_entry.ainvoke("parent", users[0]))
                await _wait(entered)
                if outcome == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 5)
                else:
                    with pytest.raises(agent_service.AgentTimeoutError):
                        await asyncio.wait_for(task, 5)
                cache.aget.assert_awaited_once()
            assert len(threads) == 1 and threads[0] != get_ident()
            assert len(workers) == 1 and not workers[0][0].done()
            assert not calculated.is_set()
            assert len(provider.requests) == 1
            assert provider.ledgers[0].tool_calls == 1
            assert lease.events == [
                ("acquire", str(users[0].id)), ("release", str(users[0].id)),
            ]
            cache.aset.assert_not_awaited()
            _assert_clean()
            _assert_statistics_slots(3)
            release.set()
            await _wait(calculated)
            assert not workers[0][0].done()
            _assert_statistics_slots(3)
        finally:
            release.set()
            finish_worker.set()
            try:
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.wait_for(
                        asyncio.gather(task, return_exceptions=True), 5,
                    )
                if stream is not None:
                    await asyncio.wait_for(stream.aclose(), 5)
            finally:
                # Join even on assertion failure, before SQLite/pool teardown.
                worker_results = await join_workers()
        assert len(worker_results) == 1
        assert worker_results[0]["status"] == "success"
        assert worker_results[0]["data"]["result"]["value"] == "0.3"
        assert len(events.started) == 1
        assert events.ended == []
        aborted_run = events.started[0]
        cache.aset.assert_not_called()
        assert lease.events == [
            ("acquire", str(users[0].id)), ("release", str(users[0].id)),
        ]
        _assert_statistics_slots(4)
        _assert_clean()
        assert len(provider.requests) == 1
        assert not any(isinstance(m, ToolMessage)
                       for state in delivered for m in state["messages"])
        if stream is not None:
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(anext(stream), 5)
        elif outcome == "cancel":
            assert task.cancelled()
        else:
            assert task.done()
            assert isinstance(task.exception(), agent_service.AgentTimeoutError)
        # A real retry also proves the callback observes successful ToolMessages;
        # cancel/timeout do not rely on the empty stream-only delivered list.
        try:
            result = await asyncio.wait_for(graph.ainvoke(
                {"messages": [HumanMessage(content="parent")]},
                config=_auth(str(users[0].id)),
            ), 5)
        finally:
            await join_workers()
        message, wrapper = _result(result)
        assert wrapper["status"] == "success"
        assert len(workers) == len(events.started) == 2
        assert events.started[1] != aborted_run
        assert events.ended == [(events.started[1], message)]
        assert len(provider.requests) == 3
        assert provider.ledgers[0] is not provider.ledgers[-1]
        cache.aset.assert_not_called()
        _assert_statistics_slots(4)

    asyncio.run(run())
    assert lease.events == [
        ("acquire", str(users[0].id)), ("release", str(users[0].id)),
    ] * 2
    _assert_clean()


def test_cancelled_workers_keep_capacity_and_reject_without_queueing(chat, files, monkeypatch):
    _, users, service, store = files
    graph, provider, lease = chat
    record = store()
    provider.plans["parent"] = [[_call(record)]]
    release = Event()
    lock = Lock()
    started = []
    original = service._read_bytes

    def read(record):
        with lock:
            started.append(get_ident())
        assert release.wait(5)
        return original(record)

    monkeypatch.setattr(service, "_read_bytes", read)

    async def run():
        try:
            for count in range(1, 5):
                task = asyncio.create_task(graph.ainvoke(
                    {"messages": [HumanMessage(content="parent")]},
                    config=_auth(str(users[0].id)),
                ))
                async with asyncio.timeout(5):
                    while len(started) < count:
                        await asyncio.sleep(0.001)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            for _ in range(8):
                result = await graph.ainvoke(
                    {"messages": [HumanMessage(content="parent")]},
                    config=_auth(str(users[0].id)),
                )
                message, wrapper = _result(result)
                assert message.status == "error"
                assert wrapper["error"]["code"] == "analysis_busy"
                assert "data" not in wrapper
            assert len(started) == len(set(started)) == 4
        finally:
            release.set()

    asyncio.run(run())
    assert len(lease.events) == 24
    assert all(b.tool_calls == 1 for b in provider.ledgers)
    _assert_clean()
