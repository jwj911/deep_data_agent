import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

import redis
from redis.exceptions import RedisError

from data_agent.config.config import config
from data_agent.config.logger import rate_limit_logger
from data_agent.observability.events import emit_event
from data_agent.services.redis_recovery import (REDIS_AVAILABLE,
                                                REDIS_UNAVAILABLE_REASON,
                                                RedisClientFactory,
                                                RedisProtectionState,
                                                RedisRecoveryState)

PROTECTION_ENFORCED = "enforced"
PROTECTION_DEGRADED = "degraded"
PROTECTION_UNAVAILABLE = "unavailable"
PROTECTION_WITHIN_LIMIT = "within_limit"
PROTECTION_LIMIT_EXCEEDED = "rate_limit_exceeded"
_FAIL_OPEN_SCOPES = frozenset({"auth", "session", "default"})


@dataclass(frozen=True)
class RateLimitDecision:
    """Immutable outcome of a single fixed-window rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    window_seconds: int
    protection_status: str = PROTECTION_ENFORCED
    protection_reason: str = PROTECTION_WITHIN_LIMIT


class RateLimitService:
    """Redis fixed-window limiter with scope-specific failure policy."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        client: Optional[redis.Redis] = None,
        client_factory: RedisClientFactory | None = None,
        recovery_state: RedisRecoveryState | None = None,
    ) -> None:
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
                rate_limit_logger,
                "rate_limit.recovered",
                operation=operation,
                outcome="success",
            )
        else:
            emit_event(
                rate_limit_logger,
                "rate_limit.degraded",
                level=logging.WARNING,
                operation=operation,
                outcome="degraded",
            )

    @property
    def available(self) -> bool:
        return self._recovery.available

    @property
    def protection_state(self) -> RedisProtectionState:
        return self._recovery.protection_state

    def _unavailable_decision(
        self,
        *,
        scope: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        state = self.protection_state
        fail_closed = scope not in _FAIL_OPEN_SCOPES
        return RateLimitDecision(
            allowed=not fail_closed,
            limit=limit,
            remaining=0 if fail_closed else limit,
            retry_after=state.retry_after if fail_closed else 0,
            window_seconds=window_seconds,
            protection_status=(
                PROTECTION_UNAVAILABLE
                if fail_closed
                else PROTECTION_DEGRADED
            ),
            protection_reason=REDIS_UNAVAILABLE_REASON,
        )

    @staticmethod
    def _window_key(
        scope: str,
        identity_key: str,
        window_seconds: int,
        now: float,
    ) -> str:
        """Build a fixed-window key from an irreversible identity digest."""
        window_index = int(now // window_seconds)
        digest = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:32]
        return f"ratelimit:{scope}:{digest}:{window_index}"

    def check(
        self,
        *,
        scope: str,
        identity_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Count one request in the current fixed window and decide allowance.

        This service only counts and digests; it never records the raw
        identity_key, tokens, plaintext origins, prompts or business data.
        """
        client = self._recovery.get_client()
        if client is None:
            return self._unavailable_decision(
                scope=scope,
                limit=limit,
                window_seconds=window_seconds,
            )

        key = self._window_key(
            scope, identity_key, window_seconds, time.time()
        )
        try:
            count = int(client.incr(key))
            if count == 1:
                client.expire(key, window_seconds)

            allowed = count <= limit
            remaining = max(limit - count, 0)
            if allowed:
                retry_after = 0
            else:
                ttl = int(client.ttl(key))
                retry_after = ttl if ttl > 0 else window_seconds

            return RateLimitDecision(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                retry_after=retry_after,
                window_seconds=window_seconds,
                protection_status=PROTECTION_ENFORCED,
                protection_reason=(
                    PROTECTION_WITHIN_LIMIT
                    if allowed
                    else PROTECTION_LIMIT_EXCEEDED
                ),
            )
        except (RedisError, OSError, ValueError):
            self._recovery.mark_unavailable(client, "check")
            return self._unavailable_decision(
                scope=scope,
                limit=limit,
                window_seconds=window_seconds,
            )


global_rate_limit_service = RateLimitService()
