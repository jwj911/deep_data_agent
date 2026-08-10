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


@dataclass(frozen=True)
class RateLimitDecision:
    """Immutable outcome of a single fixed-window rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    window_seconds: int


class RateLimitService:
    """Redis fixed-window limiter that fails open when Redis is unavailable."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        client: Optional[redis.Redis] = None,
    ) -> None:
        self.redis_client = client
        self.available = False

        try:
            if self.redis_client is None:
                self.redis_client = redis.Redis.from_url(
                    redis_url or config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
                    socket_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
                )
            self.redis_client.ping()
            self.available = True
        except (RedisError, OSError, ValueError):
            self.redis_client = None
            emit_event(
                rate_limit_logger,
                "rate_limit.degraded",
                level=logging.WARNING,
                operation="connect",
                outcome="degraded",
            )

    def _disable_after_connection_error(self, scope: str) -> None:
        self.available = False
        emit_event(
            rate_limit_logger,
            "rate_limit.degraded",
            level=logging.WARNING,
            scope=scope,
            operation="check",
            outcome="degraded",
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
        if not self.available or self.redis_client is None:
            emit_event(
                rate_limit_logger,
                "rate_limit.degraded",
                level=logging.WARNING,
                scope=scope,
                operation="check",
                outcome="degraded",
                window_seconds=window_seconds,
            )
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after=0,
                window_seconds=window_seconds,
            )

        key = self._window_key(
            scope, identity_key, window_seconds, time.time()
        )
        try:
            count = int(self.redis_client.incr(key))
            if count == 1:
                self.redis_client.expire(key, window_seconds)

            allowed = count <= limit
            remaining = max(limit - count, 0)
            if allowed:
                retry_after = 0
            else:
                ttl = int(self.redis_client.ttl(key))
                retry_after = ttl if ttl > 0 else window_seconds

            return RateLimitDecision(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                retry_after=retry_after,
                window_seconds=window_seconds,
            )
        except RedisError:
            self._disable_after_connection_error(scope)
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after=0,
                window_seconds=window_seconds,
            )


global_rate_limit_service = RateLimitService()
