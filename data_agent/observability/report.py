import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from data_agent.observability.context import normalize_request_id
from data_agent.observability.events import (normalize_event_name,
                                             safe_event_fields)
from data_agent.observability.redaction import redact_sensitive_data

_FOLDED_EVENTS = frozenset({"health.check"})
_SAFE_LEVELS = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _safe_token(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    redacted = redact_sensitive_data(value)
    if not redacted or len(redacted) > 128:
        return fallback
    return redacted


def sanitize_log_event(value: object) -> dict[str, object] | None:
    """Reduce one parsed log value to the public diagnostic schema."""
    if not isinstance(value, Mapping):
        return None
    timestamp = _parse_timestamp(value.get("timestamp"))
    if timestamp is None:
        return None

    event: dict[str, object] = {
        "schema_version": "1.0",
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "level": (
            value["level"]
            if value.get("level") in _SAFE_LEVELS
            else "INFO"
        ),
        "service": _safe_token(value.get("service"), "unknown"),
        "logger": _safe_token(value.get("logger"), "unknown"),
        "event": normalize_event_name(value.get("event")),
        "message": redact_sensitive_data(value.get("message", "")),
    }
    request_id = normalize_request_id(value.get("request_id"))
    if request_id:
        event["request_id"] = request_id

    event.update(safe_event_fields(value))
    if isinstance(value.get("exception"), str):
        event["exception"] = redact_sensitive_data(value["exception"])
    return event


def parse_json_lines(
    lines: Iterable[str],
) -> tuple[list[dict[str, object]], int]:
    """Parse diagnostic events without echoing invalid input."""
    events: list[dict[str, object]] = []
    invalid_line_count = 0
    for line in lines:
        try:
            parsed: Any = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            invalid_line_count += 1
            continue
        event = sanitize_log_event(parsed)
        if event is None:
            invalid_line_count += 1
            continue
        events.append(event)
    return events, invalid_line_count


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 3)


def _http_metrics(events: list[dict[str, object]]) -> dict[str, object]:
    requests = [
        event
        for event in events
        if event.get("event") in {"http.request.completed", "health.check"}
        and isinstance(event.get("status_code"), int)
    ]
    errors = [
        event
        for event in requests
        if int(event["status_code"]) >= 500
    ]
    durations = [
        float(event["duration_ms"])
        for event in requests
        if isinstance(event.get("duration_ms"), (int, float))
    ]
    return {
        "request_count": len(requests),
        "error_count": len(errors),
        "error_rate": (
            round(len(errors) / len(requests), 6) if requests else 0.0
        ),
        "latency_ms": {
            "average": (
                round(sum(durations) / len(durations), 3)
                if durations
                else 0.0
            ),
            "maximum": round(max(durations), 3) if durations else 0.0,
            "p95": _percentile_95(durations),
        },
    }


def _signal_count(
    events: list[dict[str, object]],
    *,
    event_name: str,
) -> int:
    return sum(event.get("event") == event_name for event in events)


def _cache_degradation_count(
    events: list[dict[str, object]],
) -> int:
    return sum(
        event.get("event") == "cache.degraded"
        or event.get("cache_status") == "unavailable"
        for event in events
    )


def _alerts(
    http_error_count: int,
    cache_degradation_count: int,
    model_failure_count: int,
) -> list[dict[str, object]]:
    signals = (
        ("http_5xx", "critical", http_error_count),
        ("cache_degraded", "warning", cache_degradation_count),
        ("model_failure", "critical", model_failure_count),
    )
    return [
        {"code": code, "severity": severity, "count": count}
        for code, severity, count in signals
        if count > 0
    ]


def _fold_events(
    events: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    folded_counts: Counter[tuple[object, ...]] = Counter()
    timeline: list[dict[str, object]] = []
    for event in events:
        if event.get("event") not in _FOLDED_EVENTS:
            timeline.append(event)
            continue
        key = (
            event.get("event"),
            event.get("service"),
            event.get("route"),
            event.get("status_code"),
            event.get("outcome"),
        )
        folded_counts[key] += 1

    folded = [
        {
            "event": key[0],
            "service": key[1],
            "route": key[2],
            "status_code": key[3],
            "outcome": key[4],
            "count": count,
        }
        for key, count in folded_counts.items()
    ]
    folded.sort(key=lambda item: (-int(item["count"]), str(item["event"])))
    return timeline, folded


def build_diagnostic_report(
    events: Iterable[Mapping[str, object]],
    *,
    request_id: str | None = None,
    invalid_line_count: int = 0,
    max_events: int = 200,
) -> dict[str, object]:
    """Build a bounded, newest-first diagnostic report."""
    if request_id is not None and normalize_request_id(request_id) is None:
        raise ValueError("request_id must be 32 lowercase hexadecimal digits")
    if max_events <= 0:
        raise ValueError("max_events must be positive")

    selected = [
        dict(event)
        for event in events
        if request_id is None or event.get("request_id") == request_id
    ]
    selected.sort(
        key=lambda event: str(event.get("timestamp", "")),
        reverse=True,
    )
    http = _http_metrics(selected)
    timeline, folded = _fold_events(selected)
    truncated_count = max(0, len(timeline) - max_events)
    timeline = timeline[:max_events]

    cache_degradations = _cache_degradation_count(selected)
    model_failures = _signal_count(
        selected,
        event_name="model.failure",
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "request_id": request_id,
        "summary": {
            "matched_event_count": len(selected),
            "invalid_line_count": max(0, invalid_line_count),
            "truncated_event_count": truncated_count,
            "http": http,
            "cache_degradation_count": cache_degradations,
            "model_failure_count": model_failures,
        },
        "alerts": _alerts(
            int(http["error_count"]),
            cache_degradations,
            model_failures,
        ),
        "folded_events": folded,
        "timeline": timeline,
    }
