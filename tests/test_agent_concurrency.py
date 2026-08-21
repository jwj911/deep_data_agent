import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException
from langchain.agents.middleware.model_call_limit import \
    ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import \
    ToolCallLimitExceededError
from langgraph.graph import END, START, StateGraph
from redis.exceptions import ConnectionError as RedisConnectionError
from typing_extensions import TypedDict

from data_agent import agent_server
from data_agent.config.config import config
from data_agent.models.user import User, UserRole
from data_agent.observability import rate_limit_middleware
from data_agent.observability.audit import audit_identity_ref
from data_agent.services import agent_lease, agent_service
from data_agent.services.agent_lease import (AGENT_BUSY, AgentBusyError,
                                             AgentIdentityError,
                                             AgentLeaseManager,
                                             AgentProtectionUnavailableError)
from data_agent.services.agent_service import (AGENT_CANCELLED,
                                               AGENT_MODEL_BUDGET_EXCEEDED,
                                               AGENT_RESPONSE_TOO_LARGE,
                                               AGENT_TIMEOUT,
                                               AGENT_TOOL_BUDGET_EXCEEDED,
                                               AgentInvocationError,
                                               AgentModelBudgetExceededError,
                                               AgentResponseTooLargeError,
                                               AgentService, AgentTimeoutError,
                                               AgentToolBudgetExceededError)
from data_agent.services.auth_service import get_current_user
from data_agent.services.rate_limit_service import RateLimitDecision
from data_agent.services.redis_recovery import AGENT_PROTECTION_UNAVAILABLE


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)


class _FakeLeaseRedis:
    """In-memory evaluator for the two Agent lease Lua scripts."""

    def __init__(self, *, online: bool = True) -> None:
        self.online = online
        self.clock = _Clock()
        self.zsets: dict[str, dict[str, int]] = {}
        self.ttl_ms: dict[str, int] = {}
        self.eval_calls: list[tuple[str, tuple[object, ...]]] = []

    def ping(self) -> bool:
        if not self.online:
            raise RedisConnectionError("private fake Redis detail")
        return True

    def eval(self, script: str, _key_count: int, *args):
        if not self.online:
            raise RedisConnectionError("private fake Redis detail")
        self.eval_calls.append((script, args))
        if "agent_lease_acquire_v1" in script:
            return self._acquire(*args)
        if "agent_lease_release_v1" in script:
            return self._release(*args)
        raise AssertionError("unexpected script")

    def _acquire(
        self,
        global_key,
        user_key,
        lease_id,
        global_limit,
        user_limit,
        ttl_ms,
    ):
        now_ms = int(self.clock() * 1000)
        global_limit = int(global_limit)
        user_limit = int(user_limit)
        ttl_ms = int(ttl_ms)
        expires_at_ms = now_ms + ttl_ms
        for key in (global_key, user_key):
            leases = self.zsets.get(key, {})
            for expired_id, score in list(leases.items()):
                if score <= now_ms:
                    del leases[expired_id]
            if not leases:
                self.zsets.pop(key, None)

        user_leases = self.zsets.get(user_key, {})
        global_leases = self.zsets.get(global_key, {})
        if len(user_leases) >= user_limit:
            retry_ms = min(user_leases.values()) - now_ms
            return [0, max(1, retry_ms), 0]
        if len(global_leases) >= global_limit:
            retry_ms = min(global_leases.values()) - now_ms
            return [-1, max(1, retry_ms), 0]

        self.zsets.setdefault(global_key, {})[
            lease_id
        ] = expires_at_ms
        self.zsets.setdefault(user_key, {})[lease_id] = expires_at_ms
        self.ttl_ms[global_key] = ttl_ms
        self.ttl_ms[user_key] = ttl_ms
        return [1, 0, expires_at_ms]

    def _release(self, global_key, user_key, lease_id):
        removed = 0
        for key in (global_key, user_key):
            leases = self.zsets.setdefault(key, {})
            removed += int(leases.pop(lease_id, None) is not None)
            if not leases:
                self.zsets.pop(key, None)
                self.ttl_ms.pop(key, None)
        return removed

    @property
    def active_count(self) -> int:
        return len(self.zsets.get("agent:lease:{agent}:global", {}))


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def aget(self, key: str):
        self.get_calls += 1
        return self.values.get(key)

    async def aset(self, key: str, value: str, expire: int) -> bool:
        self.set_calls += 1
        self.values[key] = value
        return True


class _BlockingCache:
    def __init__(
        self,
        *,
        cached_result: str | None = None,
        block_get: bool = False,
        block_set: bool = False,
    ) -> None:
        self.cached_result = cached_result
        self.block_get = block_get
        self.block_set = block_set
        self.get_started = asyncio.Event()
        self.set_started = asyncio.Event()
        self.get_cancelled = False
        self.set_cancelled = False
        self.set_completed = False

    async def aget(self, _key: str) -> str | None:
        self.get_started.set()
        if self.block_get:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.get_cancelled = True
                raise
        return self.cached_result

    async def aset(self, _key: str, _value: str, expire: int) -> bool:
        assert expire == 86400
        self.set_started.set()
        if self.block_set:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.set_cancelled = True
                raise
        self.set_completed = True
        return True


def _manager(
    client: _FakeLeaseRedis,
    clock: _Clock,
) -> AgentLeaseManager:
    counter = iter(range(1, 100))
    client.clock = clock
    return AgentLeaseManager(
        redis_url="redis://fake.test/0",
        client=client,
        clock=clock,
        sleeper=clock.advance,
        async_sleeper=clock.sleep,
        lease_id_factory=lambda: f"lease-{next(counter)}",
        poll_interval_seconds=0.25,
    )


def _actor(
    user_id: int,
    role: str = UserRole.USER.value,
) -> User:
    return User(id=user_id, role=role)


def test_atomic_leases_enforce_user_and_global_limits(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "AGENT_GLOBAL_CONCURRENCY_LIMIT", 4)
    monkeypatch.setattr(config, "AGENT_USER_CONCURRENCY_LIMIT", 1)
    monkeypatch.setattr(config, "AGENT_CONCURRENCY_WAIT_SECONDS", 1)
    client = _FakeLeaseRedis()
    clock = _Clock()
    manager = _manager(client, clock)

    first = manager.acquire("101")
    started_at = clock()
    with pytest.raises(AgentBusyError) as same_user:
        manager.acquire("101")
    assert clock() - started_at == pytest.approx(1)
    assert same_user.value.retry_after >= 1

    leases = [
        manager.acquire(subject)
        for subject in ("202", "303", "404")
    ]
    assert client.active_count == 4

    started_at = clock()
    with pytest.raises(AgentBusyError):
        manager.acquire("505")
    assert clock() - started_at == pytest.approx(1)
    assert client.active_count == 4

    user_keys = {
        key for key in client.zsets if ":user:" in key
    }
    assert user_keys == {
        "agent:lease:{agent}:user:"
        + audit_identity_ref(int(subject))
        for subject in ("101", "202", "303", "404")
    }
    assert all(
        f":user:{subject}" not in key
        for key in user_keys
        for subject in ("101", "202", "303", "404")
    )

    manager.release(first)
    for lease in leases:
        manager.release(lease)
    assert client.active_count == 0


def test_lease_hmac_key_and_events_omit_raw_subject(monkeypatch) -> None:
    subject = "987654321"
    events = []
    monkeypatch.setattr(
        agent_lease,
        "emit_event",
        lambda _logger, name, **fields: events.append((name, fields)),
    )
    client = _FakeLeaseRedis()
    manager = _manager(client, _Clock())

    lease = manager.acquire(subject)
    manager.release(lease)

    user_keys = [
        args[1]
        for script, args in client.eval_calls
        if "agent_lease_acquire_v1" in script
    ]
    assert user_keys == [
        "agent:lease:{agent}:user:"
        + audit_identity_ref(int(subject))
    ]
    assert f":user:{subject}" not in user_keys[0]
    assert subject not in repr(events)


def test_release_is_idempotent_and_ttl_reclaims_abandoned_lease() -> None:
    client = _FakeLeaseRedis()
    clock = _Clock()
    manager = _manager(client, clock)

    released = manager.acquire("7")
    expected_ttl_ms = config.AGENT_CONCURRENCY_LEASE_TTL_SECONDS * 1000
    assert released.expires_at_ms == expected_ttl_ms
    assert set(client.ttl_ms.values()) == {expected_ttl_ms}
    assert config.AGENT_CONCURRENCY_LEASE_TTL_SECONDS > (
        config.AGENT_RUN_TIMEOUT_SECONDS
    )
    assert manager.release(released) is True
    assert manager.release(released) is False

    abandoned = manager.acquire("7")
    clock.advance(config.AGENT_CONCURRENCY_LEASE_TTL_SECONDS)
    recovered = manager.acquire("7")

    assert recovered.lease_id != abandoned.lease_id
    assert client.active_count == 1
    manager.release(recovered)


def test_redis_failure_is_fail_closed_before_cache_or_graph(
    monkeypatch,
) -> None:
    client = _FakeLeaseRedis(online=False)
    manager = _manager(client, _Clock())

    with pytest.raises(
        AgentProtectionUnavailableError,
        match=AGENT_PROTECTION_UNAVAILABLE,
    ):
        manager.acquire("1")

    assert client.eval_calls == []
    assert client.active_count == 0

    cache = _MemoryCache()
    graph = SimpleNamespace(ainvoke=AsyncMock())
    service = AgentService(agent=graph, lease_manager=manager)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)
    with pytest.raises(AgentProtectionUnavailableError):
        asyncio.run(
            service.ainvoke("protected", actor=_actor(1))
        )
    assert cache.get_calls == 0
    assert cache.set_calls == 0
    graph.ainvoke.assert_not_awaited()


class _GraphState(TypedDict):
    count: int


def _compiled_test_graph(seen_configs: list[dict[str, object]]):
    def run_node(state, config):
        seen_configs.append(config)
        return {"count": state["count"] + 1}

    builder = StateGraph(_GraphState)
    builder.add_node("run_node", run_node)
    builder.add_edge(START, "run_node")
    builder.add_edge("run_node", END)
    return builder.compile()


def _auth_config(
    identity: str,
    *,
    forged_identity: str | None = None,
) -> dict[str, object]:
    configurable = {
        "langgraph_auth_user": SimpleNamespace(
            identity=identity,
            is_authenticated=True,
        ),
        "langgraph_auth_permissions": ["agent.invoke_own"],
        "recursion_limit": 999,
        "timeout": 999,
    }
    if forged_identity is not None:
        configurable["langgraph_auth_user_id"] = forged_identity
    return {
        "recursion_limit": 999,
        "timeout": 999,
        "configurable": configurable,
        "context": {
            "recursion_limit": 999,
            "timeout": 999,
            "langgraph_auth_user_id": forged_identity,
        },
    }


def test_shared_graph_uses_authenticated_subject_and_ignores_forgery() -> None:
    client = _FakeLeaseRedis()
    clock = _Clock()
    manager = _manager(client, clock)
    seen_configs: list[dict[str, object]] = []
    graph = agent_service._apply_graph_resource_bounds(
        _compiled_test_graph(seen_configs),
        lease_manager=manager,
    )

    result = asyncio.run(
        graph.ainvoke(
            {"count": 0},
            config=_auth_config("17", forged_identity="999"),
        )
    )

    assert result["count"] == 1
    runtime_config = seen_configs[0]
    assert runtime_config["configurable"][
        "langgraph_auth_user_id"
    ] == "17"
    assert "timeout" not in runtime_config["configurable"]
    assert client.active_count == 0
    keys = [
        args[1]
        for script, args in client.eval_calls
        if "agent_lease_acquire_v1" in script
    ]
    assert keys == [
        "agent:lease:{agent}:user:"
        + audit_identity_ref(17)
    ]
    assert ":user:17" not in keys[0]


def test_fastapi_service_and_shared_graph_use_same_hmac_user_key(
    monkeypatch,
) -> None:
    client = _FakeLeaseRedis()
    manager = _manager(client, _Clock())
    cache = _MemoryCache()
    service = AgentService(
        agent=SimpleNamespace(
            ainvoke=AsyncMock(
                return_value={
                    "messages": [SimpleNamespace(content="answer")]
                }
            )
        ),
        lease_manager=manager,
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    assert (
        asyncio.run(service.ainvoke("service", actor=_actor(17)))
        == "answer"
    )

    graph = agent_service._apply_graph_resource_bounds(
        _compiled_test_graph([]),
        lease_manager=manager,
    )
    asyncio.run(
        graph.ainvoke(
            {"count": 0},
            config=_auth_config("17"),
        )
    )

    user_keys = [
        args[1]
        for script, args in client.eval_calls
        if "agent_lease_acquire_v1" in script
    ]
    assert user_keys == [
        "agent:lease:{agent}:user:" + audit_identity_ref(17),
    ] * 2


def test_forged_subject_alone_is_rejected_before_graph() -> None:
    client = _FakeLeaseRedis()
    seen_configs: list[dict[str, object]] = []
    graph = agent_service._apply_graph_resource_bounds(
        _compiled_test_graph(seen_configs),
        lease_manager=_manager(client, _Clock()),
    )

    async def invoke():
        await graph.ainvoke(
            {"count": 0},
            config={
                "configurable": {
                    "langgraph_auth_user_id": "999",
                }
            },
        )

    with pytest.raises(AgentIdentityError):
        asyncio.run(invoke())

    assert seen_configs == []
    assert client.eval_calls == []


def test_shared_graph_rejects_busy_user_before_node() -> None:
    client = _FakeLeaseRedis()
    clock = _Clock()
    manager = _manager(client, clock)
    held = manager.acquire("17")
    seen_configs: list[dict[str, object]] = []
    graph = agent_service._apply_graph_resource_bounds(
        _compiled_test_graph(seen_configs),
        lease_manager=manager,
    )

    async def invoke():
        await graph.ainvoke(
            {"count": 0},
            config=_auth_config("17"),
        )

    with pytest.raises(AgentBusyError):
        asyncio.run(invoke())

    assert seen_configs == []
    manager.release(held)


def test_admin_does_not_bypass_user_lease(monkeypatch) -> None:
    client = _FakeLeaseRedis()
    manager = _manager(client, _Clock())
    held = manager.acquire("9")
    cache = _MemoryCache()
    graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "messages": [SimpleNamespace(content="unused")]
            }
        )
    )
    service = AgentService(agent=graph, lease_manager=manager)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    with pytest.raises(AgentBusyError):
        asyncio.run(
            service.ainvoke(
                "admin query",
                actor=_actor(9, UserRole.ADMIN.value),
            )
        )

    assert cache.get_calls == 0
    graph.ainvoke.assert_not_awaited()
    manager.release(held)


def test_cancellation_and_exception_release_without_cache_write(
    monkeypatch,
) -> None:
    async def run_cancelled() -> tuple[_FakeLeaseRedis, _MemoryCache]:
        client = _FakeLeaseRedis()
        manager = _manager(client, _Clock())
        cache = _MemoryCache()
        started = asyncio.Event()

        async def block(*_args, **_kwargs):
            started.set()
            await asyncio.Event().wait()

        graph = SimpleNamespace(ainvoke=block)
        service = AgentService(agent=graph, lease_manager=manager)
        monkeypatch.setattr(
            agent_service,
            "global_cache_service",
            cache,
        )
        task = asyncio.create_task(
            service.ainvoke("cancel me", actor=_actor(1))
        )
        await started.wait()
        assert client.active_count == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return client, cache

    events = []
    monkeypatch.setattr(
        agent_service,
        "emit_event",
        lambda _logger, name, **fields: events.append((name, fields)),
    )
    cancelled_client, cancelled_cache = asyncio.run(run_cancelled())
    assert cancelled_client.active_count == 0
    assert cancelled_cache.set_calls == 0
    assert any(
        fields.get("error_code") == AGENT_CANCELLED
        for _, fields in events
    )

    failed_client = _FakeLeaseRedis()
    failed_cache = _MemoryCache()
    failed_graph = SimpleNamespace(
        ainvoke=AsyncMock(side_effect=RuntimeError("private detail"))
    )
    failed_service = AgentService(
        agent=failed_graph,
        lease_manager=_manager(failed_client, _Clock()),
    )
    monkeypatch.setattr(
        agent_service,
        "global_cache_service",
        failed_cache,
    )
    with pytest.raises(AgentInvocationError):
        asyncio.run(
            failed_service.ainvoke("raise", actor=_actor(2))
        )
    assert failed_client.active_count == 0
    assert failed_cache.set_calls == 0


def test_timeout_and_oversized_response_release_without_cache_write(
    monkeypatch,
) -> None:
    timeout_client = _FakeLeaseRedis()
    timeout_cache = _MemoryCache()
    cancelled = False

    async def slow_graph(*_args, **_kwargs):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(config, "AGENT_RUN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        agent_service,
        "global_cache_service",
        timeout_cache,
    )
    timeout_service = AgentService(
        agent=SimpleNamespace(ainvoke=slow_graph),
        lease_manager=_manager(timeout_client, _Clock()),
    )

    with pytest.raises(AgentTimeoutError, match=AGENT_TIMEOUT):
        asyncio.run(
            timeout_service.ainvoke("slow", actor=_actor(3))
        )
    assert cancelled is True
    assert timeout_client.active_count == 0
    assert timeout_cache.set_calls == 0

    large_client = _FakeLeaseRedis()
    large_cache = _MemoryCache()
    large_graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "messages": [
                    SimpleNamespace(
                        content="x"
                        * (config.AGENT_RESPONSE_MAX_CHARS + 1)
                    )
                ]
            }
        )
    )
    large_service = AgentService(
        agent=large_graph,
        lease_manager=_manager(large_client, _Clock()),
    )
    monkeypatch.setattr(
        agent_service,
        "global_cache_service",
        large_cache,
    )

    with pytest.raises(
        AgentResponseTooLargeError,
        match=AGENT_RESPONSE_TOO_LARGE,
    ):
        asyncio.run(
            large_service.ainvoke("large", actor=_actor(4))
        )
    assert large_client.active_count == 0
    assert large_cache.set_calls == 0


@pytest.mark.parametrize("cached_result", ["cached answer", None])
def test_blocking_cache_lookup_cannot_outlive_agent_deadline(
    monkeypatch,
    cached_result,
) -> None:
    cache = _BlockingCache(
        cached_result=cached_result,
        block_get=True,
    )
    graph = SimpleNamespace(ainvoke=AsyncMock())
    client = _FakeLeaseRedis()
    service = AgentService(
        agent=graph,
        lease_manager=_manager(client, _Clock()),
    )
    monkeypatch.setattr(config, "AGENT_RUN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    with pytest.raises(AgentTimeoutError, match=AGENT_TIMEOUT):
        asyncio.run(service.ainvoke("blocked get", actor=_actor(21)))

    assert cache.get_started.is_set()
    assert cache.get_cancelled is True
    assert cache.set_completed is False
    assert client.active_count == 0
    graph.ainvoke.assert_not_awaited()


def test_blocking_cache_set_is_cancelled_at_agent_deadline(
    monkeypatch,
) -> None:
    cache = _BlockingCache(block_set=True)
    graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "messages": [SimpleNamespace(content="answer")]
            }
        )
    )
    client = _FakeLeaseRedis()
    service = AgentService(
        agent=graph,
        lease_manager=_manager(client, _Clock()),
    )
    monkeypatch.setattr(config, "AGENT_RUN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    with pytest.raises(AgentTimeoutError, match=AGENT_TIMEOUT):
        asyncio.run(service.ainvoke("blocked set", actor=_actor(22)))

    assert cache.set_started.is_set()
    assert cache.set_cancelled is True
    assert cache.set_completed is False
    assert client.active_count == 0
    graph.ainvoke.assert_awaited_once()


def test_cancellation_during_cache_set_does_not_complete_write(
    monkeypatch,
) -> None:
    async def cancel_during_set() -> tuple[_BlockingCache, _FakeLeaseRedis]:
        cache = _BlockingCache(block_set=True)
        client = _FakeLeaseRedis()
        service = AgentService(
            agent=SimpleNamespace(
                ainvoke=AsyncMock(
                    return_value={
                        "messages": [
                            SimpleNamespace(content="answer")
                        ]
                    }
                )
            ),
            lease_manager=_manager(client, _Clock()),
        )
        monkeypatch.setattr(
            agent_service,
            "global_cache_service",
            cache,
        )

        task = asyncio.create_task(
            service.ainvoke("cancel cache set", actor=_actor(23))
        )
        await cache.set_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return cache, client

    cache, client = asyncio.run(cancel_during_set())

    assert cache.set_cancelled is True
    assert cache.set_completed is False
    assert client.active_count == 0


@pytest.mark.parametrize(
    ("raw_error", "stable_error", "code"),
    (
        (
            ModelCallLimitExceededError(0, 9, None, 8),
            AgentModelBudgetExceededError,
            AGENT_MODEL_BUDGET_EXCEEDED,
        ),
        (
            ToolCallLimitExceededError(0, 13, None, 12),
            AgentToolBudgetExceededError,
            AGENT_TOOL_BUDGET_EXCEEDED,
        ),
    ),
)
def test_agent_service_maps_exact_budget_errors_without_cache_write(
    monkeypatch,
    raw_error,
    stable_error,
    code,
) -> None:
    cache = _MemoryCache()
    client = _FakeLeaseRedis()
    service = AgentService(
        agent=SimpleNamespace(
            ainvoke=AsyncMock(side_effect=raw_error)
        ),
        lease_manager=_manager(client, _Clock()),
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    with pytest.raises(stable_error, match=code):
        asyncio.run(service.ainvoke("budget", actor=_actor(24)))

    assert cache.set_calls == 0
    assert client.active_count == 0


@pytest.mark.parametrize(
    ("raw_error", "stable_error", "code"),
    (
        (
            ModelCallLimitExceededError(0, 9, None, 8),
            AgentModelBudgetExceededError,
            AGENT_MODEL_BUDGET_EXCEEDED,
        ),
        (
            ToolCallLimitExceededError(0, 13, None, 12),
            AgentToolBudgetExceededError,
            AGENT_TOOL_BUDGET_EXCEEDED,
        ),
    ),
)
def test_shared_graph_maps_exact_budget_errors(
    raw_error,
    stable_error,
    code,
) -> None:
    def reject_budget(_state):
        raise raw_error

    builder = StateGraph(_GraphState)
    builder.add_node("reject_budget", reject_budget)
    builder.add_edge(START, "reject_budget")
    builder.add_edge("reject_budget", END)
    graph = agent_service._apply_graph_resource_bounds(
        builder.compile(),
        lease_manager=_manager(_FakeLeaseRedis(), _Clock()),
    )

    async def invoke():
        await graph.ainvoke(
            {"count": 0},
            config=_auth_config("24"),
        )

    with pytest.raises(stable_error, match=code):
        asyncio.run(invoke())


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=agent_server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_query_rejects_blank_and_oversized_input_before_agent(
    monkeypatch,
) -> None:
    allowed = RateLimitDecision(
        allowed=True,
        limit=20,
        remaining=19,
        retry_after=0,
        window_seconds=60,
    )
    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        SimpleNamespace(check=Mock(return_value=allowed)),
    )
    invoke = AsyncMock(side_effect=AssertionError("Agent must not run"))
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        invoke,
    )
    previous_overrides = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_current_user] = lambda: _actor(
        1
    )
    try:
        responses = [
            _request("POST", "/api/query", json={"query": query})
            for query in (
                "",
                "   ",
                "x" * (config.AGENT_QUERY_MAX_CHARS + 1),
            )
        ]
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous_overrides)

    assert [response.status_code for response in responses] == [422] * 3
    invoke.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    (
        (AgentBusyError(2), 429, AGENT_BUSY),
        (
            AgentProtectionUnavailableError(3),
            503,
            AGENT_PROTECTION_UNAVAILABLE,
        ),
        (
            AgentModelBudgetExceededError(),
            429,
            AGENT_MODEL_BUDGET_EXCEEDED,
        ),
        (
            AgentToolBudgetExceededError(),
            429,
            AGENT_TOOL_BUDGET_EXCEEDED,
        ),
        (AgentTimeoutError(), 504, AGENT_TIMEOUT),
        (
            AgentResponseTooLargeError(),
            502,
            AGENT_RESPONSE_TOO_LARGE,
        ),
    ),
)
def test_query_maps_resource_errors_to_stable_codes(
    monkeypatch,
    error,
    status_code,
    code,
) -> None:
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            agent_server.query_agent(
                agent_server.QueryRequest(query="query"),
                current_user=_actor(1),
            )
        )

    assert caught.value.status_code == status_code
    assert caught.value.detail["code"] == code
    assert caught.value.detail["request_id"]
    if isinstance(error, (AgentBusyError, AgentProtectionUnavailableError)):
        assert caught.value.headers["Retry-After"] == str(
            error.retry_after
        )


def test_query_route_preserves_async_cancellation(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            agent_server.query_agent(
                agent_server.QueryRequest(query="query"),
                current_user=_actor(1),
            )
        )
