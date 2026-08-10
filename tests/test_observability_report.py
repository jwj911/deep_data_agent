import json

from data_agent.observability.report import (build_diagnostic_report,
                                             parse_json_lines)
from scripts import export_diagnostics

REQUEST_ID = "c" * 32
OTHER_REQUEST_ID = "d" * 32


def _event(
    timestamp: str,
    event: str,
    *,
    request_id: str = REQUEST_ID,
    **fields,
) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "timestamp": timestamp,
            "level": "INFO",
            "service": "fastapi",
            "logger": "deep_data_agent",
            "event": event,
            "message": event,
            "request_id": request_id,
            **fields,
        }
    )


def _sample_lines() -> list[str]:
    return [
        _event(
            "2026-08-10T10:00:00Z",
            "health.check",
            route="/api/health",
            method="GET",
            status_code=200,
            outcome="success",
            duration_ms=5,
        ),
        _event(
            "2026-08-10T10:00:01Z",
            "health.check",
            route="/api/health",
            method="GET",
            status_code=200,
            outcome="success",
            duration_ms=10,
        ),
        _event(
            "2026-08-10T10:00:02Z",
            "http.request.completed",
            route="/api/query",
            method="POST",
            status_code=200,
            outcome="success",
            duration_ms=50,
        ),
        _event(
            "2026-08-10T10:00:03Z",
            "cache.degraded",
            operation="get",
            cache_status="unavailable",
            outcome="degraded",
        ),
        _event(
            "2026-08-10T10:00:04Z",
            "model.failure",
            operation="invoke",
            error_code="agent_upstream_error",
            outcome="error",
        ),
        _event(
            "2026-08-10T10:00:05Z",
            "http.request.completed",
            route="/api/query",
            method="POST",
            status_code=502,
            outcome="error",
            duration_ms=100,
        ),
        _event(
            "2026-08-10T10:00:06Z",
            "http.request.completed",
            request_id=OTHER_REQUEST_ID,
            route="/api/auth/me",
            method="GET",
            status_code=401,
            outcome="rejected",
            duration_ms=20,
        ),
        "not-json secret-value",
    ]


def test_report_is_newest_first_and_folds_health_noise() -> None:
    events, invalid_line_count = parse_json_lines(_sample_lines())

    report = build_diagnostic_report(
        events,
        request_id=REQUEST_ID,
        invalid_line_count=invalid_line_count,
    )

    assert report["summary"]["matched_event_count"] == 6
    assert report["summary"]["invalid_line_count"] == 1
    assert report["summary"]["http"] == {
        "request_count": 4,
        "error_count": 1,
        "error_rate": 0.25,
        "latency_ms": {
            "average": 41.25,
            "maximum": 100.0,
            "p95": 100.0,
        },
    }
    assert report["summary"]["cache_degradation_count"] == 1
    assert report["summary"]["model_failure_count"] == 1
    assert report["folded_events"] == [
        {
            "event": "health.check",
            "service": "fastapi",
            "route": "/api/health",
            "status_code": 200,
            "outcome": "success",
            "count": 2,
        }
    ]
    timestamps = [event["timestamp"] for event in report["timeline"]]
    assert timestamps == sorted(timestamps, reverse=True)
    assert all(
        event["event"] != "health.check"
        for event in report["timeline"]
    )
    assert report["alerts"] == [
        {"code": "http_5xx", "severity": "critical", "count": 1},
        {"code": "cache_degraded", "severity": "warning", "count": 1},
        {"code": "model_failure", "severity": "critical", "count": 1},
    ]


def test_report_without_request_filter_includes_aggregate_events() -> None:
    events, invalid_line_count = parse_json_lines(_sample_lines())

    report = build_diagnostic_report(
        events,
        invalid_line_count=invalid_line_count,
        max_events=2,
    )

    assert report["request_id"] is None
    assert report["summary"]["matched_event_count"] == 7
    assert report["summary"]["truncated_event_count"] == 3
    assert len(report["timeline"]) == 2


def test_parser_redacts_secrets_and_drops_unknown_fields() -> None:
    api_key = "sk-" + "A" * 24
    token = "eyJ" + "B" * 8 + "." + "C" * 8 + "." + "D" * 8
    line = json.dumps(
        {
            "timestamp": "2026-08-10T10:00:00Z",
            "level": "ERROR",
            "service": "fastapi",
            "logger": "deep_data_agent",
            "event": "model.failure",
            "message": f"api_key={api_key}",
            "exception": f"Authorization: Bearer {token}",
            "request_id": REQUEST_ID,
            "prompt": "private business content",
            "nested": {"secret": api_key},
        }
    )

    events, invalid_line_count = parse_json_lines([line])

    assert invalid_line_count == 0
    rendered = json.dumps(events)
    assert api_key not in rendered
    assert token not in rendered
    assert "private business content" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_parser_counts_invalid_schema_without_echoing_content() -> None:
    events, invalid_line_count = parse_json_lines(
        [
            '{"event":"missing.timestamp","message":"private"}',
            "private malformed line",
            "[]",
        ]
    )

    assert events == []
    assert invalid_line_count == 3


def test_cli_writes_explicit_report_and_rejects_bad_id(
    tmp_path,
    capsys,
) -> None:
    input_path = tmp_path / "events.jsonl"
    output_path = tmp_path / "report.json"
    input_path.write_text("\n".join(_sample_lines()), encoding="utf-8")

    result = export_diagnostics.main(
        [
            "--input",
            str(input_path),
            "--request-id",
            REQUEST_ID,
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["request_id"] == REQUEST_ID
    assert report["summary"]["matched_event_count"] == 6
    assert capsys.readouterr().out == ""

    bad_result = export_diagnostics.main(
        [
            "--input",
            str(input_path),
            "--request-id",
            "PRIVATE-INVALID-ID",
        ]
    )
    captured = capsys.readouterr()
    assert bad_result == 2
    assert captured.out == ""
    assert captured.err == "Unable to export the diagnostic report.\n"
    assert "PRIVATE-INVALID-ID" not in captured.err
