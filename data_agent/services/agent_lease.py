import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import redis
from redis.exceptions import RedisError

from data_agent.config.config import config
from data_agent.config.logger import agent_logger
from data_agent.observability.audit import audit_identity_ref
from data_agent.observability.events import emit_event
from data_agent.services.redis_recovery import (AGENT_PROTECTION_UNAVAILABLE,
                                                REDIS_AVAILABLE,
                                                RedisClientFactory,
                                                RedisProtectionState,
                                                RedisRecoveryState)

AGENT_BUSY = "agent_busy"
AGENT_IDENTITY_INVALID = "agent_identity_invalid"

_GLOBAL_LEASE_KEY = "agent:lease:{agent}:global"
_USER_LEASE_KEY_PREFIX = "agent:lease:{agent}:user:"
_ACQUIRE_SCRIPT = """
-- agent_lease_acquire_v1
local redis_time = redis.call("TIME")
local now_ms = tonumber(redis_time[1]) * 1000
    + math.floor(tonumber(redis_time[2]) / 1000)
local lease_id = ARGV[1]
local global_limit = tonumber(ARGV[2])
local user_limit = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local expires_at_ms = now_ms + ttl_ms

redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", now_ms)
redis.call("ZREMRANGEBYSCORE", KEYS[2], "-inf", now_ms)

local function retry_ms(key)
    local first = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    if first[2] then
        return math.max(1, tonumber(first[2]) - now_ms)
    end
    return ttl_ms
end

if redis.call("ZCARD", KEYS[2]) >= user_limit then
    return {0, retry_ms(KEYS[2]), 0}
end
if redis.call("ZCARD", KEYS[1]) >= global_limit then
    return {-1, retry_ms(KEYS[1]), 0}
end

redis.call("ZADD", KEYS[1], expires_at_ms, lease_id)
redis.call("ZADD", KEYS[2], expires_at_ms, lease_id)
redis.call("PEXPIRE", KEYS[1], ttl_ms)
redis.call("PEXPIRE", KEYS[2], ttl_ms)
return {1, 0, expires_at_ms}
"""
_RELEASE_SCRIPT = """
-- agent_lease_release_v1
local global_removed = redis.call("ZREM", KEYS[1], ARGV[1])
local user_removed = redis.call("ZREM", KEYS[2], ARGV[1])
if redis.call("ZCARD", KEYS[1]) == 0 then
    redis.call("DEL", KEYS[1])
end
if redis.call("ZCARD", KEYS[2]) == 0 then
    redis.call("DEL", KEYS[2])
end
return global_removed + user_removed
"""
_RECOVERABLE_ERRORS = (RedisError, OSError, TypeError, ValueError)


class AgentBusyError(RuntimeError):
    """Raised when no global or per-user Agent slot becomes available."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(AGENT_BUSY)


class AgentProtectionUnavailableError(RuntimeError):
    """Raised when Redis cannot enforce the Agent concurrency boundary."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(AGENT_PROTECTION_UNAVAILABLE)


class AgentIdentityError(PermissionError):
    """Raised when an Agent graph lacks a trusted authenticated subject."""

    def __init__(self) -> None:
        super().__init__(AGENT_IDENTITY_INVALID)


@dataclass(frozen=True)
class AgentLease:
    """Opaque lease data; only an irreversible subject digest is retained."""

    lease_id: str
    subject_digest: str
    expires_at_ms: int


_active_agent_lease: ContextVar[AgentLease | None] = ContextVar(
    "active_agent_lease",
    default=None,
)
_active_agent_subject: ContextVar[str | None] = ContextVar(
    "active_agent_subject",
    default=None,
)


def get_active_agent_lease() -> AgentLease | None:
    """Return the lease held by the current execution context, if any."""
    return _active_agent_lease.get()


def get_active_agent_subject() -> str | None:
    """Return the trusted subject bound to the active lease."""
    return _active_agent_subject.get()


class AgentLeaseManager:
    """Redis-backed atomic global/user Agent concurrency leases."""

    def __init__(
        self,
        redis_url: str | None = None,
        client: redis.Redis | None = None,
        client_factory: RedisClientFactory | None = None,
        recovery_state: RedisRecoveryState | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        async_sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        lease_id_factory: Callable[[], str] | None = None,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._async_sleeper = async_sleeper
        self._lease_id_factory = lease_id_factory or (
            lambda: uuid4().hex
        )
        self._poll_interval_seconds = poll_interval_seconds

        if recovery_state is not None:
            self._recovery = recovery_state
            return

        resolved_url = redis_url or config.REDIS_URL
        if client_factory is None:
            if client is not None:
                client_factory = lambda _redis_url: client
            else:
                client_factory = self._create_client
        self._recovery = RedisRecoveryState(
            redis_url=resolved_url,
            client_factory=client_factory,
            initial_client=client,
            initial_backoff_seconds=(
                config.REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS
            ),
            max_backoff_seconds=config.REDIS_RECOVERY_MAX_BACKOFF_SECONDS,
            jitter_ratio=config.REDIS_RECOVERY_JITTER_RATIO,
            clock=clock,
            on_state_change=self._on_redis_state_change,
        )

    @staticmethod
    def _create_client(redis_url: str) -> redis.Redis:
        return redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _on_redis_state_change(status: str, operation: str) -> None:
        if status == REDIS_AVAILABLE:
            emit_event(
                agent_logger,
                "agent.protection.recovered",
                operation=operation,
                outcome="success",
            )
        else:
            emit_event(
                agent_logger,
                "agent.protection.degraded",
                level=logging.WARNING,
                operation=operation,
                outcome="degraded",
                error_code=AGENT_PROTECTION_UNAVAILABLE,
            )

    @staticmethod
    def subject_digest(subject: str) -> str:
        if (
            not isinstance(subject, str)
            or not subject.isdigit()
            or int(subject) <= 0
            or str(int(subject)) != subject
        ):
            raise AgentIdentityError()
        return audit_identity_ref(int(subject))

    @staticmethod
    def _user_key(subject_digest: str) -> str:
        return _USER_LEASE_KEY_PREFIX + subject_digest

    @property
    def protection_state(self) -> RedisProtectionState:
        return self._recovery.protection_state

    def _protection_error(self) -> AgentProtectionUnavailableError:
        return AgentProtectionUnavailableError(
            self.protection_state.retry_after
        )

    def _try_acquire(
        self,
        *,
        subject_digest: str,
        lease_id: str,
    ) -> tuple[AgentLease | None, int]:
        client = self._recovery.get_client()
        if client is None:
            raise self._protection_error()

        ttl_ms = config.AGENT_CONCURRENCY_LEASE_TTL_SECONDS * 1000
        try:
            result = client.eval(
                _ACQUIRE_SCRIPT,
                2,
                _GLOBAL_LEASE_KEY,
                self._user_key(subject_digest),
                lease_id,
                config.AGENT_GLOBAL_CONCURRENCY_LIMIT,
                config.AGENT_USER_CONCURRENCY_LIMIT,
                ttl_ms,
            )
            status = int(result[0])
            retry_ms = max(0, int(result[1]))
            expires_at_ms = max(0, int(result[2]))
        except _RECOVERABLE_ERRORS:
            self._recovery.mark_unavailable(client, "lease_acquire")
            raise self._protection_error()

        if status == 1:
            if expires_at_ms <= 0:
                self._recovery.mark_unavailable(
                    client,
                    "lease_acquire",
                )
                raise self._protection_error()
            return (
                AgentLease(
                    lease_id=lease_id,
                    subject_digest=subject_digest,
                    expires_at_ms=expires_at_ms,
                ),
                0,
            )
        if status in {0, -1}:
            return None, max(1, math.ceil(retry_ms / 1000))

        self._recovery.mark_unavailable(client, "lease_acquire")
        raise self._protection_error()

    def acquire(self, subject: str) -> AgentLease:
        """Wait for at most the configured window and acquire one lease."""
        started_at = self._clock()
        wait_deadline = (
            started_at + config.AGENT_CONCURRENCY_WAIT_SECONDS
        )
        subject_digest = self.subject_digest(subject)
        lease_id = self._lease_id_factory()
        retry_after = 1

        while True:
            try:
                lease, retry_after = self._try_acquire(
                    subject_digest=subject_digest,
                    lease_id=lease_id,
                )
            except AgentProtectionUnavailableError:
                emit_event(
                    agent_logger,
                    "agent.lease.rejected",
                    level=logging.WARNING,
                    operation="lease",
                    outcome="rejected",
                    error_code=AGENT_PROTECTION_UNAVAILABLE,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                raise
            if lease is not None:
                emit_event(
                    agent_logger,
                    "agent.lease.acquired",
                    operation="lease",
                    outcome="success",
                    limit=config.AGENT_GLOBAL_CONCURRENCY_LIMIT,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                return lease

            remaining = wait_deadline - self._clock()
            if remaining <= 0:
                emit_event(
                    agent_logger,
                    "agent.lease.rejected",
                    level=logging.WARNING,
                    operation="lease",
                    outcome="rejected",
                    error_code=AGENT_BUSY,
                    limit=config.AGENT_GLOBAL_CONCURRENCY_LIMIT,
                    retry_after=retry_after,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                raise AgentBusyError(retry_after)
            self._sleeper(
                min(self._poll_interval_seconds, remaining)
            )

    async def acquire_async(self, subject: str) -> AgentLease:
        """Asynchronously wait for one lease while preserving cancellation."""
        started_at = self._clock()
        wait_deadline = (
            started_at + config.AGENT_CONCURRENCY_WAIT_SECONDS
        )
        subject_digest = self.subject_digest(subject)
        lease_id = self._lease_id_factory()
        retry_after = 1

        while True:
            try:
                lease, retry_after = self._try_acquire(
                    subject_digest=subject_digest,
                    lease_id=lease_id,
                )
            except AgentProtectionUnavailableError:
                emit_event(
                    agent_logger,
                    "agent.lease.rejected",
                    level=logging.WARNING,
                    operation="lease",
                    outcome="rejected",
                    error_code=AGENT_PROTECTION_UNAVAILABLE,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                raise
            if lease is not None:
                emit_event(
                    agent_logger,
                    "agent.lease.acquired",
                    operation="lease",
                    outcome="success",
                    limit=config.AGENT_GLOBAL_CONCURRENCY_LIMIT,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                return lease

            remaining = wait_deadline - self._clock()
            if remaining <= 0:
                emit_event(
                    agent_logger,
                    "agent.lease.rejected",
                    level=logging.WARNING,
                    operation="lease",
                    outcome="rejected",
                    error_code=AGENT_BUSY,
                    limit=config.AGENT_GLOBAL_CONCURRENCY_LIMIT,
                    retry_after=retry_after,
                    duration_ms=(self._clock() - started_at) * 1000,
                )
                raise AgentBusyError(retry_after)
            await self._async_sleeper(
                min(self._poll_interval_seconds, remaining)
            )

    def release(self, lease: AgentLease) -> bool:
        """Release a lease; repeated calls are harmless."""
        client = self._recovery.get_client()
        if client is None:
            emit_event(
                agent_logger,
                "agent.lease.release_deferred",
                level=logging.WARNING,
                operation="lease_release",
                outcome="degraded",
                error_code=AGENT_PROTECTION_UNAVAILABLE,
            )
            return False

        try:
            removed = int(
                client.eval(
                    _RELEASE_SCRIPT,
                    2,
                    _GLOBAL_LEASE_KEY,
                    self._user_key(lease.subject_digest),
                    lease.lease_id,
                )
            )
        except _RECOVERABLE_ERRORS:
            self._recovery.mark_unavailable(client, "lease_release")
            emit_event(
                agent_logger,
                "agent.lease.release_deferred",
                level=logging.WARNING,
                operation="lease_release",
                outcome="degraded",
                error_code=AGENT_PROTECTION_UNAVAILABLE,
            )
            return False

        emit_event(
            agent_logger,
            "agent.lease.released",
            operation="lease_release",
            outcome="success",
        )
        return removed > 0

    @contextmanager
    def hold(self, subject: str) -> Iterator[AgentLease]:
        """Hold a sync lease, reusing a matching lease in nested graph calls."""
        subject_digest = self.subject_digest(subject)
        active = get_active_agent_lease()
        if active is not None:
            if active.subject_digest != subject_digest:
                raise AgentIdentityError()
            yield active
            return

        lease = self.acquire(subject)
        lease_token = _active_agent_lease.set(lease)
        subject_token = _active_agent_subject.set(subject)
        try:
            yield lease
        finally:
            _active_agent_subject.reset(subject_token)
            _active_agent_lease.reset(lease_token)
            self.release(lease)

    @asynccontextmanager
    async def hold_async(self, subject: str) -> AsyncIterator[AgentLease]:
        """Hold an async lease and always attempt release on cancellation."""
        subject_digest = self.subject_digest(subject)
        active = get_active_agent_lease()
        if active is not None:
            if active.subject_digest != subject_digest:
                raise AgentIdentityError()
            yield active
            return

        lease = await self.acquire_async(subject)
        lease_token = _active_agent_lease.set(lease)
        subject_token = _active_agent_subject.set(subject)
        try:
            yield lease
        finally:
            _active_agent_subject.reset(subject_token)
            _active_agent_lease.reset(lease_token)
            self.release(lease)


global_agent_lease_manager = AgentLeaseManager()
