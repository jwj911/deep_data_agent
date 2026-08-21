import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from data_agent.config.logger import cache_logger
from data_agent.services.cache_service import CacheService
from data_agent.services.redis_recovery import (AGENT_PROTECTION_UNAVAILABLE,
                                                REDIS_AVAILABLE,
                                                REDIS_AVAILABLE_REASON,
                                                REDIS_UNAVAILABLE,
                                                REDIS_UNAVAILABLE_REASON,
                                                RedisRecoveryState)


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def set(self, now: float) -> None:
        self.now = now


class _FakeRedis:
    def __init__(self, *, online: bool) -> None:
        self.online = online
        self.ping_calls = 0
        self.values: dict[str, str] = {}

    def _require_online(self) -> None:
        if not self.online:
            raise RedisConnectionError("sensitive fake connection detail")

    def ping(self) -> bool:
        self.ping_calls += 1
        self._require_online()
        return True

    def get(self, key: str) -> str | None:
        self._require_online()
        return self.values.get(key)

    def setex(self, key: str, _expire, value: str) -> bool:
        self._require_online()
        self.values[key] = value
        return True

    def delete(self, key: str) -> int:
        self._require_online()
        return int(self.values.pop(key, None) is not None)

    def flushdb(self) -> bool:
        self._require_online()
        self.values.clear()
        return True


class _AsyncFakeRedis:
    def __init__(self, *, block_set: bool = False) -> None:
        self.block_set = block_set
        self.values: dict[str, str] = {}
        self.set_started = asyncio.Event()
        self.set_cancelled = False

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, _expire, value: str) -> bool:
        self.set_started.set()
        if self.block_set:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.set_cancelled = True
                raise
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def flushdb(self) -> bool:
        self.values.clear()
        return True


def test_reconnect_uses_exponential_backoff_without_early_probes() -> None:
    clock = _Clock()
    offline = _FakeRedis(online=False)
    factory_urls: list[str] = []

    def factory(redis_url: str) -> _FakeRedis:
        factory_urls.append(redis_url)
        return offline

    state = RedisRecoveryState(
        redis_url="redis://private.example:6379/0",
        client_factory=factory,
        initial_client=offline,
        clock=clock,
        random_source=lambda: 0.5,
    )

    assert state.failure_count == 1
    assert state.protection_state.retry_after == 1

    due_times = (1.0, 3.0, 7.0, 15.0, 31.0, 61.0)
    next_delays = (2, 4, 8, 16, 30, 30)
    for index, (due_at, next_delay) in enumerate(
        zip(due_times, next_delays),
        start=1,
    ):
        clock.set(due_at - 0.01)
        assert state.get_client() is None
        assert len(factory_urls) == index - 1

        clock.set(due_at)
        assert state.get_client() is None
        assert len(factory_urls) == index
        assert state.protection_state.retry_after == next_delay

    assert state.failure_count == 7
    assert set(factory_urls) == {"redis://private.example:6379/0"}


@pytest.mark.parametrize("random_value", [-10.0, 10.0])
def test_reconnect_jitter_is_bounded(random_value: float) -> None:
    clock = _Clock()
    offline = _FakeRedis(online=False)
    state = RedisRecoveryState(
        redis_url="redis://offline.test/0",
        client_factory=lambda _url: offline,
        initial_client=offline,
        clock=clock,
        random_source=lambda: random_value,
    )

    for _ in range(8):
        retry_after = state.protection_state.retry_after
        assert 1 <= retry_after <= 30
        clock.set(clock.now + retry_after)
        assert state.get_client() is None


def test_due_reconnect_probe_is_single_flight() -> None:
    clock = _Clock()
    offline = _FakeRedis(online=False)
    probe_started = Event()
    release_probe = Event()
    factory_lock = Lock()
    factory_calls = 0
    transitions: list[tuple[str, str]] = []

    class _BlockingRedis(_FakeRedis):
        def ping(self) -> bool:
            self.ping_calls += 1
            probe_started.set()
            assert release_probe.wait(timeout=5)
            return True

    recovered = _BlockingRedis(online=True)

    def factory(_redis_url: str) -> _BlockingRedis:
        nonlocal factory_calls
        with factory_lock:
            factory_calls += 1
        return recovered

    state = RedisRecoveryState(
        redis_url="redis://offline.test/0",
        client_factory=factory,
        initial_client=offline,
        clock=clock,
        random_source=lambda: 0.5,
        on_state_change=lambda status, operation: transitions.append(
            (status, operation)
        ),
    )
    clock.set(1.0)

    with ThreadPoolExecutor(max_workers=9) as executor:
        probe = executor.submit(state.get_client)
        assert probe_started.wait(timeout=5)
        followers = [executor.submit(state.get_client) for _ in range(8)]
        assert [future.result(timeout=5) for future in followers] == [
            None
        ] * 8
        assert factory_calls == 1
        release_probe.set()
        assert probe.result(timeout=5) is recovered

    assert state.available is True
    assert recovered.ping_calls == 1
    assert transitions == [
        (REDIS_UNAVAILABLE, "connect"),
        (REDIS_AVAILABLE, "probe"),
    ]


def test_cache_recovers_and_resets_backoff_after_a_second_failure() -> None:
    clock = _Clock()
    initial = _FakeRedis(online=False)
    recovered = _FakeRedis(online=True)
    state = RedisRecoveryState(
        redis_url="redis://offline.test/0",
        client_factory=lambda _url: recovered,
        initial_client=initial,
        clock=clock,
        random_source=lambda: 0.5,
        on_state_change=CacheService._on_redis_state_change,
    )
    cache = CacheService(recovery_state=state)

    assert cache.get("key") is None
    assert cache.set("key", {"value": 1}) is False
    assert cache.delete("key") is False
    assert cache.clear() is False
    assert initial.ping_calls == 1

    clock.set(1.0)
    assert cache.set("key", {"value": 1}) is True
    assert cache.get("key") == {"value": 1}
    assert state.failure_count == 0

    recovered.online = False
    assert cache.get("key") is None
    assert cache.available is False
    assert state.failure_count == 1
    assert state.protection_state.retry_after == 1
    assert cache.set("other", "value") is False

    recovered.online = True
    clock.set(2.0)
    assert cache.get("key") == {"value": 1}
    assert cache.available is True


def test_async_cache_interface_uses_async_client_io() -> None:
    async_client = _AsyncFakeRedis()
    cache = CacheService(
        client=_FakeRedis(online=True),
        async_client=async_client,
    )

    async def exercise_cache() -> None:
        assert await cache.aset("key", {"value": 1}) is True
        assert await cache.aget("key") == {"value": 1}
        assert await cache.adelete("key") is True
        assert await cache.aget("key") is None
        assert await cache.aset("other", "value") is True
        assert await cache.aclear() is True

    asyncio.run(exercise_cache())

    assert async_client.values == {}


def test_async_cache_cancellation_does_not_finish_blocked_write() -> None:
    async_client = _AsyncFakeRedis(block_set=True)
    cache = CacheService(
        client=_FakeRedis(online=True),
        async_client=async_client,
    )

    async def cancel_write() -> None:
        task = asyncio.create_task(cache.aset("key", "value"))
        await async_client.set_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_write())

    assert async_client.set_cancelled is True
    assert async_client.values == {}


def test_protection_state_has_stable_agent_error_contract() -> None:
    clock = _Clock()
    fake = _FakeRedis(online=False)
    state = RedisRecoveryState(
        redis_url="redis://offline.test/0",
        client_factory=lambda _url: fake,
        initial_client=fake,
        clock=clock,
        random_source=lambda: 0.5,
    )

    unavailable = state.protection_state
    assert unavailable.status == REDIS_UNAVAILABLE
    assert unavailable.reason == REDIS_UNAVAILABLE_REASON
    assert unavailable.error_code == AGENT_PROTECTION_UNAVAILABLE
    assert unavailable.available is False

    fake.online = True
    clock.set(1.0)
    assert state.get_client() is fake

    available = state.protection_state
    assert available.status == REDIS_AVAILABLE
    assert available.reason == REDIS_AVAILABLE_REASON
    assert available.error_code is None
    assert available.available is True


def test_recovery_events_do_not_expose_url_key_or_exception(
    caplog,
    monkeypatch,
) -> None:
    secret_url = "redis://secret-user:secret-pass@private.example/0"
    secret_key = "user:12345:private-query"
    fake = _FakeRedis(online=False)
    monkeypatch.setattr(cache_logger, "propagate", True)
    caplog.set_level(logging.INFO)

    cache = CacheService(redis_url=secret_url, client=fake)
    assert cache.get(secret_key) is None

    rendered = caplog.text
    for forbidden in (
        secret_url,
        "secret-user",
        "secret-pass",
        secret_key,
        "12345",
        "private-query",
        "sensitive fake connection detail",
    ):
        assert forbidden not in rendered
