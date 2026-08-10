import logging
import re
from collections.abc import Mapping
from typing import Any

_EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_ROUTE_PATTERN = re.compile(r"^/[A-Za-z0-9_./{}:-]{0,255}$")

_ENUM_FIELDS = {
    "outcome": {
        "success",
        "started",
        "rejected",
        "error",
        "degraded",
        "disabled",
    },
    "cache_status": {
        "hit",
        "miss",
        "stored",
        "deleted",
        "cleared",
        "skipped",
        "unavailable",
    },
}
_TOKEN_FIELDS = {
    "operation",
    "tool_name",
    "error_code",
    "method",
}
_INTEGER_FIELDS = {
    "status_code",
    "event_count",
    "invalid_line_count",
    "folded_count",
}
_NUMBER_FIELDS = {"duration_ms"}
_BOOLEAN_FIELDS = {"available"}
_SAFE_EVENT_FIELDS = frozenset(
    {
        *_ENUM_FIELDS,
        *_TOKEN_FIELDS,
        *_INTEGER_FIELDS,
        *_NUMBER_FIELDS,
        *_BOOLEAN_FIELDS,
        "route",
    }
)


def normalize_event_name(value: object) -> str:
    """Return a bounded event name or a stable fallback."""
    if isinstance(value, str) and _EVENT_NAME_PATTERN.fullmatch(value):
        return value
    return "log.message"


def safe_event_fields(fields: Mapping[str, Any]) -> dict[str, object]:
    """Keep only bounded, low-cardinality structured event fields."""
    safe: dict[str, object] = {}
    for key, value in fields.items():
        if key not in _SAFE_EVENT_FIELDS:
            continue
        if key in _ENUM_FIELDS:
            if isinstance(value, str) and value in _ENUM_FIELDS[key]:
                safe[key] = value
        elif key in _TOKEN_FIELDS:
            if isinstance(value, str) and _TOKEN_PATTERN.fullmatch(value):
                safe[key] = value
        elif key in _INTEGER_FIELDS:
            if isinstance(value, int) and not isinstance(value, bool):
                safe[key] = value
        elif key in _NUMBER_FIELDS:
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ):
                safe[key] = round(float(value), 3)
        elif key in _BOOLEAN_FIELDS:
            if isinstance(value, bool):
                safe[key] = value
        elif key == "route":
            if isinstance(value, str) and _ROUTE_PATTERN.fullmatch(value):
                safe[key] = value
    return safe


def emit_event(
    target_logger: logging.Logger,
    event_name: str,
    *,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    """Emit a structured event without accepting arbitrary event payloads."""
    normalized_event = normalize_event_name(event_name)
    target_logger.log(
        level,
        normalized_event,
        extra={
            "event_name": normalized_event,
            "event_fields": safe_event_fields(fields),
        },
    )
