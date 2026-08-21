import asyncio
import math
import random
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable
from weakref import WeakKeyDictionary

from redis.exceptions import RedisError

REDIS_AVAILABLE = "available"
REDIS_UNAVAILABLE = "unavailable"
REDIS_AVAILABLE_REASON = "redis_available"
REDIS_UNAVAILABLE_REASON = "redis_unavailable"
AGENT_PROTECTION_UNAVAILABLE = "agent_protection_unavailable"

RedisClientFactory = Callable[[str], Any]
AsyncRedisClientFactory = Callable[[str], Any]
RecoveryEventCallback = Callable[[str, str], None]

_RECOVERABLE_ERRORS = (RedisError, OSError, ValueError)


@dataclass(frozen=True)
class RedisProtectionState:
    """Stable Redis state consumed by fail-open and fail-closed callers."""

    status: str
    reason: str
    error_code: str | None
    retry_after: int

    @property
    def available(self) -> bool:
        return self.status == REDIS_AVAILABLE


class RedisRecoveryState:
    """Thread-safe single-flight Redis reconnect state with bounded backoff."""

    def __init__(
        self,
        *,
        redis_url: str,
        client_factory: RedisClientFactory,
        initial_client: Any | None = None,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        jitter_ratio: float = 0.2,
        clock: Callable[[], float] = time.monotonic,
        random_source: Callable[[], float] = random.random,
        on_state_change: RecoveryEventCallback | None = None,
    ) -> None:
        if not 1.0 <= initial_backoff_seconds <= max_backoff_seconds:
            raise ValueError(
                "Redis reconnect backoff must start at or above 1 second"
            )
        if max_backoff_seconds > 30.0:
            raise ValueError(
                "Redis reconnect backoff must not exceed 30 seconds"
            )
        if not 0.0 <= jitter_ratio <= 1.0:
            raise ValueError("Redis reconnect jitter ratio must be in [0, 1]")

        self._redis_url = redis_url
        self._client_factory = client_factory
        self._initial_backoff_seconds = initial_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._jitter_ratio = jitter_ratio
        self._clock = clock
        self._random_source = random_source
        self._on_state_change = on_state_change

        self._lock = Lock()
        self._client: Any | None = None
        self._available = False
        self._probe_in_progress = False
        self._failure_count = 0
        self._next_probe_at = 0.0

        self._connect_initial(initial_client)

    def _notify(self, status: str, operation: str) -> None:
        if self._on_state_change is not None:
            self._on_state_change(status, operation)

    def _next_delay_locked(self) -> float:
        exponent = min(self._failure_count - 1, 16)
        base_delay = min(
            self._initial_backoff_seconds * (2**exponent),
            self._max_backoff_seconds,
        )
        sample = min(max(float(self._random_source()), 0.0), 1.0)
        jitter = (sample * 2.0 - 1.0) * base_delay * self._jitter_ratio
        return min(
            max(base_delay + jitter, self._initial_backoff_seconds),
            self._max_backoff_seconds,
        )

    def _record_failure_locked(self, now: float) -> None:
        self._available = False
        self._client = None
        self._failure_count += 1
        self._next_probe_at = now + self._next_delay_locked()

    def _connect_initial(self, initial_client: Any | None) -> None:
        try:
            client = (
                initial_client
                if initial_client is not None
                else self._client_factory(self._redis_url)
            )
            client.ping()
        except _RECOVERABLE_ERRORS:
            with self._lock:
                self._record_failure_locked(self._clock())
            self._notify(REDIS_UNAVAILABLE, "connect")
            return

        with self._lock:
            self._client = client
            self._available = True

    @property
    def available(self) -> bool:
        with self._lock:
            return self._available

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def protection_state(self) -> RedisProtectionState:
        with self._lock:
            if self._available:
                return RedisProtectionState(
                    status=REDIS_AVAILABLE,
                    reason=REDIS_AVAILABLE_REASON,
                    error_code=None,
                    retry_after=0,
                )
            wait_seconds = self._next_probe_at - self._clock()

        return RedisProtectionState(
            status=REDIS_UNAVAILABLE,
            reason=REDIS_UNAVAILABLE_REASON,
            error_code=AGENT_PROTECTION_UNAVAILABLE,
            retry_after=max(1, math.ceil(wait_seconds)),
        )

    def get_client(self) -> Any | None:
        """Return a usable client, running at most one due reconnect probe."""
        with self._lock:
            if self._available:
                return self._client
            now = self._clock()
            if self._probe_in_progress or now < self._next_probe_at:
                return None
            self._probe_in_progress = True

        try:
            candidate = self._client_factory(self._redis_url)
            candidate.ping()
        except _RECOVERABLE_ERRORS:
            with self._lock:
                self._probe_in_progress = False
                self._record_failure_locked(self._clock())
            self._notify(REDIS_UNAVAILABLE, "probe")
            return None

        with self._lock:
            self._client = candidate
            self._available = True
            self._probe_in_progress = False
            self._failure_count = 0
            self._next_probe_at = 0.0
        self._notify(REDIS_AVAILABLE, "probe")
        return candidate

    def mark_unavailable(self, client: Any, operation: str) -> None:
        """Degrade once for the active client and ignore stale failures."""
        with self._lock:
            if not self._available or client is not self._client:
                return
            self._record_failure_locked(self._clock())
        self._notify(REDIS_UNAVAILABLE, operation)


class AsyncRedisRecoveryState:
    """Async Redis reconnect state using cancellable client I/O."""

    def __init__(
        self,
        *,
        redis_url: str,
        client_factory: AsyncRedisClientFactory,
        initial_client: Any | None = None,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        jitter_ratio: float = 0.2,
        clock: Callable[[], float] = time.monotonic,
        random_source: Callable[[], float] = random.random,
        on_state_change: RecoveryEventCallback | None = None,
    ) -> None:
        if not 1.0 <= initial_backoff_seconds <= max_backoff_seconds:
            raise ValueError(
                "Redis reconnect backoff must start at or above 1 second"
            )
        if max_backoff_seconds > 30.0:
            raise ValueError(
                "Redis reconnect backoff must not exceed 30 seconds"
            )
        if not 0.0 <= jitter_ratio <= 1.0:
            raise ValueError("Redis reconnect jitter ratio must be in [0, 1]")

        self._redis_url = redis_url
        self._client_factory = client_factory
        self._initial_client = initial_client
        self._initial_backoff_seconds = initial_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._jitter_ratio = jitter_ratio
        self._clock = clock
        self._random_source = random_source
        self._on_state_change = on_state_change

        self._lock = Lock()
        self._probe_locks_guard = Lock()
        self._probe_locks: WeakKeyDictionary[
            asyncio.AbstractEventLoop, asyncio.Lock
        ] = WeakKeyDictionary()
        self._client: Any | None = None
        self._available = False
        self._failure_count = 0
        self._next_probe_at = 0.0

    def _notify(self, status: str, operation: str) -> None:
        if self._on_state_change is not None:
            self._on_state_change(status, operation)

    def _next_delay_locked(self) -> float:
        exponent = min(self._failure_count - 1, 16)
        base_delay = min(
            self._initial_backoff_seconds * (2**exponent),
            self._max_backoff_seconds,
        )
        sample = min(max(float(self._random_source()), 0.0), 1.0)
        jitter = (sample * 2.0 - 1.0) * base_delay * self._jitter_ratio
        return min(
            max(base_delay + jitter, self._initial_backoff_seconds),
            self._max_backoff_seconds,
        )

    def _record_failure_locked(self, now: float) -> None:
        self._available = False
        self._client = None
        self._failure_count += 1
        self._next_probe_at = now + self._next_delay_locked()

    def _probe_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._probe_locks_guard:
            lock = self._probe_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._probe_locks[loop] = lock
            return lock

    @property
    def available(self) -> bool:
        with self._lock:
            return self._available

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def protection_state(self) -> RedisProtectionState:
        with self._lock:
            if self._available:
                return RedisProtectionState(
                    status=REDIS_AVAILABLE,
                    reason=REDIS_AVAILABLE_REASON,
                    error_code=None,
                    retry_after=0,
                )
            wait_seconds = self._next_probe_at - self._clock()

        return RedisProtectionState(
            status=REDIS_UNAVAILABLE,
            reason=REDIS_UNAVAILABLE_REASON,
            error_code=AGENT_PROTECTION_UNAVAILABLE,
            retry_after=max(1, math.ceil(wait_seconds)),
        )

    async def get_client(self) -> Any | None:
        """Return a usable async client after at most one due probe per loop."""
        with self._lock:
            if self._available:
                return self._client
            if self._clock() < self._next_probe_at:
                return None

        async with self._probe_lock():
            with self._lock:
                if self._available:
                    return self._client
                if self._clock() < self._next_probe_at:
                    return None
                candidate = self._initial_client
                self._initial_client = None

            try:
                if candidate is None:
                    candidate = self._client_factory(self._redis_url)
                await candidate.ping()
            except _RECOVERABLE_ERRORS:
                with self._lock:
                    self._record_failure_locked(self._clock())
                self._notify(REDIS_UNAVAILABLE, "probe")
                return None

            with self._lock:
                self._client = candidate
                self._available = True
                self._failure_count = 0
                self._next_probe_at = 0.0
            self._notify(REDIS_AVAILABLE, "probe")
            return candidate

    def mark_unavailable(self, client: Any, operation: str) -> None:
        """Degrade once for the active async client."""
        with self._lock:
            if not self._available or client is not self._client:
                return
            self._record_failure_locked(self._clock())
        self._notify(REDIS_UNAVAILABLE, operation)
