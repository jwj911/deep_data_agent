import os

import redis
import redis.asyncio as async_redis
from redis.exceptions import ConnectionError as RedisConnectionError

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["MOONSHOT_API_KEY"] = "your_moonshot_api_key_here"
os.environ["TAVILY_API_KEY"] = "your_tavily_api_key_here"
os.environ["JWT_SECRET_KEY"] = (
    "test-suite-jwt-secret-with-at-least-32-characters"
)
os.environ["CORS_ALLOWED_ORIGINS"] = (
    "http://localhost:3000,https://app.example.test"
)


class _OfflineRedis:
    def ping(self) -> None:
        raise RedisConnectionError("Redis disabled in tests")


class _AsyncOfflineRedis:
    async def ping(self) -> None:
        raise RedisConnectionError("Redis disabled in tests")


def _offline_redis_from_url(*args, **kwargs) -> _OfflineRedis:
    return _OfflineRedis()


def _async_offline_redis_from_url(*args, **kwargs) -> _AsyncOfflineRedis:
    return _AsyncOfflineRedis()


# Prevent import-time cache initialization from contacting any Redis instance.
redis.Redis.from_url = staticmethod(_offline_redis_from_url)
async_redis.Redis.from_url = staticmethod(_async_offline_redis_from_url)
