import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from data_agent import agent_server
from data_agent.models.user import User, UserRole
from data_agent.services import agent_service
from data_agent.services.agent_service import AgentService
from data_agent.services.auth_service import get_current_user
from data_agent.services.authorization_service import AuthorizationDeniedError


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_keys: list[str] = []
        self.set_keys: list[str] = []

    def get(self, key: str):
        self.get_keys.append(key)
        return self.values.get(key)

    def set(self, key: str, value: str, expire: int) -> bool:
        assert expire == 86400
        self.set_keys.append(key)
        self.values[key] = value
        return True


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


def test_service_rejects_missing_or_unknown_actor_before_side_effects(
    monkeypatch,
) -> None:
    cache = _MemoryCache()
    graph = Mock()
    service = AgentService(agent=graph)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    for actor in (None, _actor(1, "unknown")):
        with pytest.raises(AuthorizationDeniedError):
            service.invoke("private query", actor=actor)

    assert cache.get_keys == []
    graph.invoke.assert_not_called()


def test_same_query_uses_distinct_tenant_cache_keys(monkeypatch) -> None:
    cache = _MemoryCache()
    graph = Mock()
    graph.invoke.side_effect = [
        {"messages": [SimpleNamespace(content="answer-a")]},
        {"messages": [SimpleNamespace(content="answer-b")]},
    ]
    service = AgentService(agent=graph)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)

    answer_a = service.invoke("same query", actor=_actor(1))
    answer_b = service.invoke("same query", actor=_actor(2))

    assert answer_a == "answer-a"
    assert answer_b == "answer-b"
    assert graph.invoke.call_count == 2
    assert len(set(cache.set_keys)) == 2
    assert all(key.startswith("agent:") for key in cache.set_keys)
    assert all("same query" not in key for key in cache.set_keys)


def test_same_user_can_reuse_own_cached_result(monkeypatch) -> None:
    cache = _MemoryCache()
    graph = Mock(
        return_value={
            "messages": [SimpleNamespace(content="answer")]
        }
    )
    graph.invoke.return_value = {
        "messages": [SimpleNamespace(content="answer")]
    }
    service = AgentService(agent=graph)
    monkeypatch.setattr(agent_service, "global_cache_service", cache)
    actor = _actor(7)

    first = service.invoke("repeat", actor=actor)
    second = service.invoke("repeat", actor=actor)

    assert first == second == "answer"
    graph.invoke.assert_called_once()
    assert cache.get_keys[0] == cache.get_keys[1]


def test_query_endpoint_rejects_anonymous_before_agent(monkeypatch) -> None:
    invoke = Mock(side_effect=AssertionError("agent must not run"))
    monkeypatch.setattr(agent_server.global_agent_service, "invoke", invoke)

    response = _request(
        "POST",
        "/api/query",
        json={"query": "anonymous"},
    )

    assert response.status_code == 401
    invoke.assert_not_called()


def test_query_endpoint_passes_authenticated_actor(monkeypatch) -> None:
    actor = _actor(11)
    invoke = Mock(return_value="ok")
    previous_overrides = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_current_user] = lambda: actor
    monkeypatch.setattr(agent_server.global_agent_service, "invoke", invoke)
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
