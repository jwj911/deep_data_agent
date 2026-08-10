import hashlib
import logging
from functools import lru_cache
from time import perf_counter
from typing import Literal

from tavily import TavilyClient

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import tool_logger
from data_agent.observability.context import bind_runnable_request_id
from data_agent.observability.events import emit_event
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
    with bind_runnable_request_id():
        started_at = perf_counter()
        emit_event(
            tool_logger,
            "tool.started",
            operation="search",
            tool_name="internet_search",
            outcome="started",
        )
        cache_key = _generate_cache_key(
            query,
            max_results,
            topic,
            include_raw_content,
        )

        cached_result = global_cache_service.get(cache_key)
        if cached_result:
            emit_event(
                tool_logger,
                "tool.completed",
                operation="search",
                tool_name="internet_search",
                outcome="success",
                cache_status="hit",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return cached_result

        try:
            result = _get_tavily_client().search(
                query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                topic=topic,
            )

            global_cache_service.set(cache_key, result, expire=3600)
            emit_event(
                tool_logger,
                "tool.completed",
                operation="search",
                tool_name="internet_search",
                outcome="success",
                cache_status="miss",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return result
        except ConfigurationError as exc:
            emit_event(
                tool_logger,
                "tool.disabled",
                level=logging.WARNING,
                operation="search",
                tool_name="internet_search",
                outcome="disabled",
                error_code="configuration_error",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {"error": str(exc), "code": "configuration_error"}
        except Exception:
            tool_logger.exception(
                "Internet search request failed",
                extra={
                    "event_name": "tool.failed",
                    "event_fields": {
                        "operation": "search",
                        "tool_name": "internet_search",
                        "outcome": "error",
                        "error_code": "upstream_error",
                        "duration_ms": (
                            perf_counter() - started_at
                        )
                        * 1000,
                    },
                },
            )
            return {
                "error": "Internet search is temporarily unavailable",
                "code": "upstream_error",
            }
