from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from data_agent.services import rate_limit_service
from data_agent.services.rate_limit_service import (PROTECTION_DEGRADED,
                                                    PROTECTION_ENFORCED,
                                                    PROTECTION_LIMIT_EXCEEDED,
                                                    PROTECTION_UNAVAILABLE,
                                                    PROTECTION_WITHIN_LIMIT,
                                                    RateLimitDecision,
                                                    RateLimitService)
from data_agent.services.redis_recovery import (REDIS_UNAVAILABLE_REASON,
                                                RedisRecoveryState)


class _FakeRedis:
    """In-memory Redis stand-in for deterministic fixed-window counting.

    It never touches a network; ``incr`` counts per key, ``expire`` records
    each call and ``ttl`` returns the configured window so retry-after stays
    predictable.
    """

    def __init__(self, *, window_seconds: int = 60, ping_ok: bool = True):
        self.counts: dict[str, int] = {}
        self.expire_calls: list[tuple[str, int]] = []
        self.ttl_value = window_seconds
        self._ping_ok = ping_ok

    def ping(self) -> bool:
        if not self._ping_ok:
            raise RedisConnectionError("offline redis stub")
        return True

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expire_calls.append((key, seconds))
        return True

    def ttl(self, key: str) -> int:
        return self.ttl_value


class _Clock:
    """Deterministic monotonic-ish clock injected into the module's ``time``."""

    def __init__(self, now: float):
        self._now = now

    def time(self) -> float:
        return self._now

    def __call__(self) -> float:
        return self._now

    def set(self, now: float) -> None:
        self._now = now


def test_check_allows_until_limit_then_rejects(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit_service, "time", _Clock(1000.0))
    fake = _FakeRedis(window_seconds=60)
    service = RateLimitService(client=fake)

    assert service.available is True

    decisions = [
        service.check(
            scope="query",
            identity_key="user:1",
            limit=3,
            window_seconds=60,
        )
        for _ in range(3)
    ]

    assert [decision.allowed for decision in decisions] == [True, True, True]
    assert [decision.remaining for decision in decisions] == [2, 1, 0]
    assert all(decision.retry_after == 0 for decision in decisions)
    assert all(
        decision.protection_status == PROTECTION_ENFORCED
        for decision in decisions
    )
    assert all(
        decision.protection_reason == PROTECTION_WITHIN_LIMIT
        for decision in decisions
    )

    rejected = service.check(
        scope="query",
        identity_key="user:1",
        limit=3,
        window_seconds=60,
    )

    assert rejected.allowed is False
    assert rejected.remaining == 0
    assert rejected.retry_after > 0
    assert rejected.limit == 3
    assert rejected.window_seconds == 60
    assert rejected.protection_status == PROTECTION_ENFORCED
    assert rejected.protection_reason == PROTECTION_LIMIT_EXCEEDED

    # EXPIRE 仅在窗口首次计数（count == 1）时被调用一次。
    assert len(fake.expire_calls) == 1
    assert fake.expire_calls[0][1] == 60


def test_check_resets_counter_on_next_window(monkeypatch) -> None:
    clock = _Clock(1000.0)
    monkeypatch.setattr(rate_limit_service, "time", clock)
    fake = _FakeRedis(window_seconds=60)
    service = RateLimitService(client=fake)

    for _ in range(2):
        service.check(
            scope="query",
            identity_key="user:1",
            limit=2,
            window_seconds=60,
        )
    blocked = service.check(
        scope="query",
        identity_key="user:1",
        limit=2,
        window_seconds=60,
    )

    assert blocked.allowed is False

    first_window_keys = set(fake.counts)

    # 推进到下一个固定窗口 index，计数键随之变化并重新放行。
    clock.set(1000.0 + 60)
    allowed_again = service.check(
        scope="query",
        identity_key="user:1",
        limit=2,
        window_seconds=60,
    )

    assert allowed_again.allowed is True
    assert allowed_again.remaining == 1

    new_keys = set(fake.counts) - first_window_keys
    assert new_keys  # 新窗口使用了此前未出现过的计数键


@pytest.mark.parametrize(
    ("scope", "allowed", "protection_status"),
    (
        ("auth", True, PROTECTION_DEGRADED),
        ("session", True, PROTECTION_DEGRADED),
        ("default", True, PROTECTION_DEGRADED),
        ("query", False, PROTECTION_UNAVAILABLE),
    ),
)
def test_unavailable_redis_uses_scope_policy_matrix(
    monkeypatch,
    scope: str,
    allowed: bool,
    protection_status: str,
) -> None:
    monkeypatch.setattr(rate_limit_service, "time", _Clock(1000.0))
    fake = _FakeRedis(ping_ok=False)
    service = RateLimitService(client=fake)

    assert service.available is False

    decision = service.check(
        scope=scope,
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )

    assert decision.allowed is allowed
    assert decision.remaining == (5 if allowed else 0)
    if allowed:
        assert decision.retry_after == 0
    else:
        assert decision.retry_after > 0
    assert decision.protection_status == protection_status
    assert decision.protection_reason == REDIS_UNAVAILABLE_REASON
    assert isinstance(decision, RateLimitDecision)
    assert fake.counts == {}


def test_query_fails_closed_on_redis_error_and_disables(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit_service, "time", _Clock(1000.0))
    fake = _FakeRedis()
    fake.incr = Mock(side_effect=RedisError("boom"))
    service = RateLimitService(client=fake)

    assert service.available is True

    decision = service.check(
        scope="query",
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after > 0
    assert decision.protection_status == PROTECTION_UNAVAILABLE
    assert decision.protection_reason == REDIS_UNAVAILABLE_REASON
    assert service.available is False


def test_rate_limit_recovers_without_restart_after_backoff(
    monkeypatch,
) -> None:
    clock = _Clock(1000.0)
    monkeypatch.setattr(rate_limit_service, "time", clock)
    initial = _FakeRedis(ping_ok=False)
    recovered = _FakeRedis()
    state = RedisRecoveryState(
        redis_url="redis://offline.test/0",
        client_factory=lambda _url: recovered,
        initial_client=initial,
        clock=clock,
        random_source=lambda: 0.5,
    )
    service = RateLimitService(recovery_state=state)

    unavailable = service.check(
        scope="query",
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )
    assert unavailable.protection_status == PROTECTION_UNAVAILABLE

    clock.set(1001.0)
    recovered_decision = service.check(
        scope="query",
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )

    assert recovered_decision.allowed is True
    assert recovered_decision.protection_status == PROTECTION_ENFORCED
    assert service.available is True

    original_incr = recovered.incr
    recovered.incr = Mock(side_effect=RedisError("disconnected"))
    failed_again = service.check(
        scope="query",
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )
    assert failed_again.protection_status == PROTECTION_UNAVAILABLE

    recovered.incr = original_incr
    clock.set(1002.0)
    recovered_again = service.check(
        scope="query",
        identity_key="user:1",
        limit=5,
        window_seconds=60,
    )
    assert recovered_again.allowed is True
    assert recovered_again.protection_status == PROTECTION_ENFORCED


def test_check_uses_irreversible_digest_key(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit_service, "time", _Clock(1000.0))
    fake = _FakeRedis()
    service = RateLimitService(client=fake)

    service.check(
        scope="query",
        identity_key="user:12345",
        limit=5,
        window_seconds=60,
    )

    assert fake.counts  # 已经产生计数键
    for key in fake.counts:
        assert "12345" not in key
        assert "user:12345" not in key
    for key, _ in fake.expire_calls:
        assert "12345" not in key
