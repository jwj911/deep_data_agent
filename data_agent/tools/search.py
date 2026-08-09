import hashlib
from functools import lru_cache
from typing import Literal

from tavily import TavilyClient

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import tool_logger
from data_agent.services.cache_service import global_cache_service


@lru_cache(maxsize=1)
def _get_tavily_client() -> TavilyClient:
    return TavilyClient(api_key=config.require_search_api_key())


def _generate_cache_key(
    query: str,
    max_results: int,
    topic: str,
    include_raw_content: bool,
) -> str:
    """Generate cache key for search query"""
    key = f"search:{query}:{max_results}:{topic}:{include_raw_content}"
    return hashlib.md5(key.encode()).hexdigest()


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "images", "videos", "files"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Run a search query using the Tavily API with caching."""
    tool_logger.info("Performing internet search")

    cache_key = _generate_cache_key(query, max_results, topic, include_raw_content)

    cached_result = global_cache_service.get(cache_key)
    if cached_result:
        tool_logger.info("Using cached search result")
        return cached_result

    try:
        result = _get_tavily_client().search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )

        global_cache_service.set(cache_key, result, expire=3600)
        tool_logger.info("Cached search result")
        return result
    except ConfigurationError as exc:
        tool_logger.warning("Internet search disabled: %s", exc)
        return {"error": str(exc), "code": "configuration_error"}
    except Exception:
        tool_logger.exception("Internet search request failed")
        return {
            "error": "Internet search is temporarily unavailable",
            "code": "upstream_error",
        }
