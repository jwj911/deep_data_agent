import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
from functools import lru_cache
from time import perf_counter
from typing import Annotated, Any, Literal

from pydantic import Field
from tavily import AsyncTavilyClient

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import tool_logger
from data_agent.observability.context import bind_runnable_request_id
from data_agent.observability.events import emit_event
from data_agent.services.cache_service import global_cache_service


@lru_cache(maxsize=1)
def _get_tavily_client() -> AsyncTavilyClient:
    return AsyncTavilyClient(
        api_key=config.require_search_api_key(),
        timeout=config.SEARCH_TIMEOUT_SECONDS,
    )


def _generate_cache_key(
    query: str,
    max_results: int,
    topic: str,
) -> str:
    """Generate a policy-versioned cache key without retaining the query."""
    key = f"search:v2:{query}:{max_results}:{topic}"
    return "search:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def _error(code: str, message: str) -> dict[str, str]:
    return {"error": message, "code": code}


def _sanitize_result(
    result: Any,
    *,
    max_results: int,
) -> dict[str, list[dict[str, object]]]:
    if not isinstance(result, Mapping):
        raise TypeError("search result must be an object")
    raw_results = result.get("results")
    if not isinstance(raw_results, list):
        raise TypeError("search results must be a list")

    sanitized: list[dict[str, object]] = []
    for item in raw_results[:max_results]:
        if not isinstance(item, Mapping):
            continue
        bounded_item: dict[str, object] = {}
        for field in ("title", "url", "content", "published_date"):
            value = item.get(field)
            if isinstance(value, str):
                bounded_item[field] = value
        score = item.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            bounded_item["score"] = score
        sanitized.append(bounded_item)
    return {"results": sanitized}


def _result_size_bytes(result: object) -> int:
    return len(
        json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


async def internet_search(
    query: Annotated[str, Field(min_length=1, max_length=2000)],
    max_results: Annotated[int, Field(ge=1, le=5)] = 5,
    topic: Literal["general", "news"] = "general",
) -> dict[str, object]:
    """Run one bounded general or news search using the Tavily API."""
    with bind_runnable_request_id():
        started_at = perf_counter()
        emit_event(
            tool_logger,
            "tool.started",
            operation="search",
            tool_name="internet_search",
            outcome="started",
        )
        normalized_query = query.strip() if isinstance(query, str) else ""
        if (
            not normalized_query
            or len(normalized_query) > config.SEARCH_QUERY_MAX_CHARS
        ):
            return _error(
                "search_invalid_query",
                "Search query is empty or too long",
            )
        if (
            not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or not 1 <= max_results <= config.SEARCH_MAX_RESULTS
        ):
            return _error(
                "search_invalid_max_results",
                "Search result count is out of range",
            )
        if topic not in ("general", "news"):
            return _error(
                "search_invalid_topic",
                "Search topic is not supported",
            )
        try:
            config.require_search_api_key()
        except ConfigurationError:
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
            return _error(
                "configuration_error",
                "Internet search is not configured",
            )

        cache_key = _generate_cache_key(
            normalized_query,
            max_results,
            topic,
        )

        cached_result = await global_cache_service.aget(cache_key)
        if cached_result:
            try:
                bounded_cached_result = _sanitize_result(
                    cached_result,
                    max_results=max_results,
                )
            except TypeError:
                bounded_cached_result = None
            if (
                bounded_cached_result is None
                or _result_size_bytes(bounded_cached_result)
                > config.SEARCH_MAX_OUTPUT_BYTES
            ):
                await global_cache_service.adelete(cache_key)
            else:
                emit_event(
                    tool_logger,
                    "tool.completed",
                    operation="search",
                    tool_name="internet_search",
                    outcome="success",
                    cache_status="hit",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return bounded_cached_result

        try:
            async with asyncio.timeout(config.SEARCH_TIMEOUT_SECONDS):
                result = await _get_tavily_client().search(
                    normalized_query,
                    max_results=max_results,
                    include_answer=False,
                    include_images=False,
                    include_raw_content=False,
                    topic=topic,
                )
            bounded_result = _sanitize_result(
                result,
                max_results=max_results,
            )
            if (
                _result_size_bytes(bounded_result)
                > config.SEARCH_MAX_OUTPUT_BYTES
            ):
                emit_event(
                    tool_logger,
                    "tool.failed",
                    level=logging.WARNING,
                    operation="search",
                    tool_name="internet_search",
                    outcome="rejected",
                    error_code="search_response_too_large",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return _error(
                    "search_response_too_large",
                    "Search response exceeded the output limit",
                )

            await global_cache_service.aset(
                cache_key,
                bounded_result,
                expire=3600,
            )
            emit_event(
                tool_logger,
                "tool.completed",
                operation="search",
                tool_name="internet_search",
                outcome="success",
                cache_status="miss",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return bounded_result
        except ConfigurationError:
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
            return _error(
                "configuration_error",
                "Internet search is not configured",
            )
        except TimeoutError:
            emit_event(
                tool_logger,
                "tool.failed",
                level=logging.WARNING,
                operation="search",
                tool_name="internet_search",
                outcome="error",
                error_code="search_timeout",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return _error(
                "search_timeout",
                "Internet search timed out",
            )
        except Exception:
            emit_event(
                tool_logger,
                "tool.failed",
                level=logging.ERROR,
                operation="search",
                tool_name="internet_search",
                outcome="error",
                error_code="upstream_error",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return _error(
                "upstream_error",
                "Internet search is temporarily unavailable",
            )
