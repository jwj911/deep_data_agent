import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

_REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


def normalize_request_id(value: object) -> str | None:
    """Return a valid request ID without normalizing unsafe input."""
    if not isinstance(value, str) or not _REQUEST_ID_PATTERN.fullmatch(value):
        return None
    return value


def new_request_id() -> str:
    """Generate the canonical request ID format."""
    return uuid4().hex


def get_request_id() -> str | None:
    """Return the request ID bound to the current execution context."""
    return _request_id_context.get()


def get_or_create_request_id(value: object = None) -> str:
    """Resolve an explicit or contextual request ID, then generate one."""
    return (
        normalize_request_id(value)
        or get_request_id()
        or new_request_id()
    )


@contextmanager
def bind_request_id(value: object = None) -> Iterator[str]:
    """Bind a validated request ID for the duration of an operation."""
    request_id = get_or_create_request_id(value)
    token = _request_id_context.set(request_id)
    try:
        yield request_id
    finally:
        _request_id_context.reset(token)


def request_id_from_runnable_config(
    runnable_config: Mapping[str, Any] | None = None,
) -> str | None:
    """Extract a request ID from LangGraph configurable or metadata."""
    config = runnable_config
    if config is None:
        try:
            from langgraph.config import get_config

            config = get_config()
        except (ImportError, RuntimeError):
            return None

    for container_name in ("configurable", "metadata"):
        container = config.get(container_name)
        if isinstance(container, Mapping):
            request_id = normalize_request_id(container.get("request_id"))
            if request_id:
                return request_id
    return None


@contextmanager
def bind_runnable_request_id() -> Iterator[str]:
    """Bind the request ID carried by the active LangGraph run."""
    with bind_request_id(request_id_from_runnable_config()) as request_id:
        yield request_id
