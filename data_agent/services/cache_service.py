import json
import logging
from datetime import timedelta
from typing import Any, Optional

import redis
from redis.exceptions import RedisError

from data_agent.config.config import config
from data_agent.config.logger import cache_logger
from data_agent.observability.events import emit_event


class CacheService:
    """Redis-backed cache that degrades to cache misses when unavailable."""

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
            cache_logger.warning(
                "Redis unavailable; cache disabled (operation=connect)",
                extra={
                    "event_name": "cache.degraded",
                    "event_fields": {
                        "operation": "connect",
                        "cache_status": "unavailable",
                        "outcome": "degraded",
                    },
                },
            )

    def _disable_after_connection_error(self, operation: str) -> None:
        self.available = False
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

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.available or self.redis_client is None:
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
            value = self.redis_client.get(key)
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
        except RedisError:
            self._disable_after_connection_error("get")
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
        if not self.available or self.redis_client is None:
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
            self.redis_client.setex(
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
        except RedisError:
            self._disable_after_connection_error("set")
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
        if not self.available or self.redis_client is None:
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
            self.redis_client.delete(key)
            emit_event(
                cache_logger,
                "cache.delete",
                operation="delete",
                cache_status="deleted",
                outcome="success",
            )
            return True
        except RedisError:
            self._disable_after_connection_error("delete")
            return False

    def clear(self) -> bool:
        """Clear all cache"""
        if not self.available or self.redis_client is None:
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
            self.redis_client.flushdb()
            emit_event(
                cache_logger,
                "cache.clear",
                operation="clear",
                cache_status="cleared",
                outcome="success",
            )
            return True
        except RedisError:
            self._disable_after_connection_error("clear")
            return False


global_cache_service = CacheService()
