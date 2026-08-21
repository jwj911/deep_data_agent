import json
import logging
from datetime import timedelta
from typing import Any, Optional

import redis
import redis.asyncio as async_redis
from redis.exceptions import RedisError

from data_agent.config.config import config
from data_agent.config.logger import cache_logger
from data_agent.observability.events import emit_event
from data_agent.services.redis_recovery import (REDIS_AVAILABLE,
                                                AsyncRedisClientFactory,
                                                AsyncRedisRecoveryState,
                                                RedisClientFactory,
                                                RedisProtectionState,
                                                RedisRecoveryState)


class CacheService:
    """Redis-backed cache that degrades to cache misses when unavailable."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        client: Optional[redis.Redis] = None,
        client_factory: RedisClientFactory | None = None,
        recovery_state: RedisRecoveryState | None = None,
        async_client: Any | None = None,
        async_client_factory: AsyncRedisClientFactory | None = None,
        async_recovery_state: AsyncRedisRecoveryState | None = None,
    ) -> None:
        resolved_url = redis_url or config.REDIS_URL
        if recovery_state is not None:
            self._recovery = recovery_state
        else:
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
                max_backoff_seconds=(
                    config.REDIS_RECOVERY_MAX_BACKOFF_SECONDS
                ),
                jitter_ratio=config.REDIS_RECOVERY_JITTER_RATIO,
                on_state_change=self._on_redis_state_change,
            )

        if async_recovery_state is not None:
            self._async_recovery = async_recovery_state
        else:
            if async_client_factory is None:
                if async_client is not None:
                    async_client_factory = lambda _redis_url: async_client
                else:
                    async_client_factory = self._create_async_client
            self._async_recovery = AsyncRedisRecoveryState(
                redis_url=resolved_url,
                client_factory=async_client_factory,
                initial_client=async_client,
                initial_backoff_seconds=(
                    config.REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS
                ),
                max_backoff_seconds=(
                    config.REDIS_RECOVERY_MAX_BACKOFF_SECONDS
                ),
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
    def _create_async_client(redis_url: str) -> async_redis.Redis:
        return async_redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _on_redis_state_change(status: str, operation: str) -> None:
        if status == REDIS_AVAILABLE:
            emit_event(
                cache_logger,
                "cache.recovered",
                operation=operation,
                cache_status="available",
                outcome="success",
            )
        else:
            cache_logger.warning(
                "Redis unavailable; cache disabled (operation=%s)",
                operation,
                extra={
                    "event_name": "cache.degraded",
                    "event_fields": {
                        "operation": operation,
                        "cache_status": "unavailable",
                        "outcome": "degraded",
                    },
                },
            )

    @property
    def available(self) -> bool:
        return self._recovery.available

    @property
    def protection_state(self) -> RedisProtectionState:
        return self._recovery.protection_state

    @property
    def async_protection_state(self) -> RedisProtectionState:
        return self._async_recovery.protection_state

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        client = self._recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.lookup",
                level=logging.WARNING,
                operation="get",
                cache_status="unavailable",
                outcome="degraded",
            )
            return None

        try:
            value = client.get(key)
            if value:
                emit_event(
                    cache_logger,
                    "cache.lookup",
                    operation="get",
                    cache_status="hit",
                    outcome="success",
                )
                return json.loads(value)
            emit_event(
                cache_logger,
                "cache.lookup",
                operation="get",
                cache_status="miss",
                outcome="success",
            )
            return None
        except (RedisError, OSError):
            self._recovery.mark_unavailable(client, "get")
            return None
        except (TypeError, json.JSONDecodeError):
            cache_logger.warning(
                "Ignoring invalid cached value",
                extra={
                    "event_name": "cache.invalid",
                    "event_fields": {
                        "operation": "get",
                        "cache_status": "skipped",
                        "outcome": "degraded",
                    },
                },
            )
            return None

    def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """Set value in cache with expiration"""
        client = self._recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.store",
                level=logging.WARNING,
                operation="set",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            client.setex(
                key,
                timedelta(seconds=expire),
                json.dumps(value),
            )
            emit_event(
                cache_logger,
                "cache.store",
                operation="set",
                cache_status="stored",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._recovery.mark_unavailable(client, "set")
            return False
        except (TypeError, ValueError):
            cache_logger.warning(
                "Skipping non-serializable cache value",
                extra={
                    "event_name": "cache.invalid",
                    "event_fields": {
                        "operation": "set",
                        "cache_status": "skipped",
                        "outcome": "degraded",
                    },
                },
            )
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        client = self._recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.delete",
                level=logging.WARNING,
                operation="delete",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            client.delete(key)
            emit_event(
                cache_logger,
                "cache.delete",
                operation="delete",
                cache_status="deleted",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._recovery.mark_unavailable(client, "delete")
            return False

    def clear(self) -> bool:
        """Clear all cache"""
        client = self._recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.clear",
                level=logging.WARNING,
                operation="clear",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            client.flushdb()
            emit_event(
                cache_logger,
                "cache.clear",
                operation="clear",
                cache_status="cleared",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._recovery.mark_unavailable(client, "clear")
            return False

    async def aget(self, key: str) -> Optional[Any]:
        """Get a cached value through cancellable Redis I/O."""
        client = await self._async_recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.lookup",
                level=logging.WARNING,
                operation="get",
                cache_status="unavailable",
                outcome="degraded",
            )
            return None

        try:
            value = await client.get(key)
            if value:
                emit_event(
                    cache_logger,
                    "cache.lookup",
                    operation="get",
                    cache_status="hit",
                    outcome="success",
                )
                return json.loads(value)
            emit_event(
                cache_logger,
                "cache.lookup",
                operation="get",
                cache_status="miss",
                outcome="success",
            )
            return None
        except (RedisError, OSError):
            self._async_recovery.mark_unavailable(client, "get")
            return None
        except (TypeError, json.JSONDecodeError):
            cache_logger.warning(
                "Ignoring invalid cached value",
                extra={
                    "event_name": "cache.invalid",
                    "event_fields": {
                        "operation": "get",
                        "cache_status": "skipped",
                        "outcome": "degraded",
                    },
                },
            )
            return None

    async def aset(
        self,
        key: str,
        value: Any,
        expire: int = 3600,
    ) -> bool:
        """Store a cached value through cancellable Redis I/O."""
        client = await self._async_recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.store",
                level=logging.WARNING,
                operation="set",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            await client.setex(
                key,
                timedelta(seconds=expire),
                json.dumps(value),
            )
            emit_event(
                cache_logger,
                "cache.store",
                operation="set",
                cache_status="stored",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._async_recovery.mark_unavailable(client, "set")
            return False
        except (TypeError, ValueError):
            cache_logger.warning(
                "Skipping non-serializable cache value",
                extra={
                    "event_name": "cache.invalid",
                    "event_fields": {
                        "operation": "set",
                        "cache_status": "skipped",
                        "outcome": "degraded",
                    },
                },
            )
            return False

    async def adelete(self, key: str) -> bool:
        """Delete a cached value through cancellable Redis I/O."""
        client = await self._async_recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.delete",
                level=logging.WARNING,
                operation="delete",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            await client.delete(key)
            emit_event(
                cache_logger,
                "cache.delete",
                operation="delete",
                cache_status="deleted",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._async_recovery.mark_unavailable(client, "delete")
            return False

    async def aclear(self) -> bool:
        """Clear the cache through cancellable Redis I/O."""
        client = await self._async_recovery.get_client()
        if client is None:
            emit_event(
                cache_logger,
                "cache.clear",
                level=logging.WARNING,
                operation="clear",
                cache_status="unavailable",
                outcome="degraded",
            )
            return False

        try:
            await client.flushdb()
            emit_event(
                cache_logger,
                "cache.clear",
                operation="clear",
                cache_status="cleared",
                outcome="success",
            )
            return True
        except (RedisError, OSError):
            self._async_recovery.mark_unavailable(client, "clear")
            return False


global_cache_service = CacheService()
