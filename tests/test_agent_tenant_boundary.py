import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from data_agent import agent_server
from data_agent.models.user import User, UserRole
from data_agent.observability import rate_limit_middleware
from data_agent.services import agent_service
from data_agent.services.agent_service import AgentService
from data_agent.services.auth_service import get_current_user
from data_agent.services.authorization_service import AuthorizationDeniedError
from data_agent.services.rate_limit_service import RateLimitDecision


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_keys: list[str] = []
        self.set_keys: list[str] = []

    async def aget(self, key: str):
        self.get_keys.append(key)
        return self.values.get(key)

    async def aset(self, key: str, value: str, expire: int) -> bool:
        assert expire == 86400
        self.set_keys.append(key)
        self.values[key] = value
        return True


class _AllowLeaseManager:
    @asynccontextmanager
    async def hold_async(self, _subject):
        yield


def _actor(user_id: int, role: str = UserRole.USER.value) -> User:
    return User(id=user_id, role=role)


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=agent_server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def _set_healthy_rate_limiter(monkeypatch) -> None:
    decision = RateLimitDecision(
        allowed=True,
        limit=20,
        remaining=19,
        retry_after=0,
        window_seconds=60,
    )
    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        SimpleNamespace(check=Mock(return_value=decision)),
    )


def test_service_rejects_missing_or_unknown_actor_before_side_effects(
    monkeypatch,
) -> None:
    cache = _MemoryCache()
    graph = Mock()
    graph.ainvoke = AsyncMock()
    service = AgentService(
        agent=graph,
        lease_manager=_AllowLeaseManager(),
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    for actor in (None, _actor(1, "unknown")):
        with pytest.raises(AuthorizationDeniedError):
            asyncio.run(service.ainvoke("private query", actor=actor))

    assert cache.get_keys == []
    graph.ainvoke.assert_not_called()


def test_same_query_uses_distinct_tenant_cache_keys(monkeypatch) -> None:
    cache = _MemoryCache()
    graph = Mock()
    graph.ainvoke = AsyncMock(side_effect=[
        {"messages": [SimpleNamespace(content="answer-a")]},
        {"messages": [SimpleNamespace(content="answer-b")]},
    ])
    service = AgentService(
        agent=graph,
        lease_manager=_AllowLeaseManager(),
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    answer_a = asyncio.run(
        service.ainvoke("same query", actor=_actor(1))
    )
    answer_b = asyncio.run(
        service.ainvoke("same query", actor=_actor(2))
    )

    assert answer_a == "answer-a"
    assert answer_b == "answer-b"
    assert graph.ainvoke.call_count == 2
    assert len(set(cache.set_keys)) == 2
    assert all(key.startswith("agent:") for key in cache.set_keys)
    assert all("same query" not in key for key in cache.set_keys)


def test_same_user_can_reuse_own_cached_result(monkeypatch) -> None:
    cache = _MemoryCache()
    graph = Mock()
    graph.ainvoke = AsyncMock(
        return_value={"messages": [SimpleNamespace(content="answer")]}
    )
    service = AgentService(
        agent=graph,
        lease_manager=_AllowLeaseManager(),
    )
    monkeypatch.setattr(agent_service, "global_cache_service", cache)
    actor = _actor(7)

    first = asyncio.run(service.ainvoke("repeat", actor=actor))
    second = asyncio.run(service.ainvoke("repeat", actor=actor))

    assert first == second == "answer"
    graph.ainvoke.assert_awaited_once()
    assert cache.get_keys[0] == cache.get_keys[1]


def test_query_endpoint_rejects_anonymous_before_agent(monkeypatch) -> None:
    _set_healthy_rate_limiter(monkeypatch)
    invoke = AsyncMock(side_effect=AssertionError("agent must not run"))
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        invoke,
    )

    response = _request(
        "POST",
        "/api/query",
        json={"query": "anonymous"},
    )

    assert response.status_code == 401
    invoke.assert_not_called()


def test_query_endpoint_passes_authenticated_actor(monkeypatch) -> None:
    _set_healthy_rate_limiter(monkeypatch)
    actor = _actor(11)
    invoke = AsyncMock(return_value="ok")
    previous_overrides = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_current_user] = lambda: actor
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        invoke,
    )
    try:
        response = _request(
            "POST",
            "/api/query",
            json={"query": "authenticated"},
        )
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert invoke.call_args.kwargs["actor"] is actor
