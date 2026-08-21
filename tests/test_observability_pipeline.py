import asyncio
import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from data_agent.config.config import Config, ConfigurationError, config
from data_agent.config.logger import RedactingFormatter, logger
from data_agent.models.user import User, UserRole
from data_agent.observability.context import (bind_request_id, get_request_id,
                                              normalize_request_id,
                                              request_id_from_runnable_config)
from data_agent.observability.events import emit_event
from data_agent.services.agent_service import AgentService
from data_agent.services.auth_service import get_current_user

VALID_REQUEST_ID = "a" * 32
OTHER_REQUEST_ID = "b" * 32


class _AllowLeaseManager:
    @asynccontextmanager
    async def hold_async(self, _subject):
        yield


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    from data_agent.agent_server import app

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


class _JsonCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.stream = StringIO()
        self.setFormatter(RedactingFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.stream.write(self.format(record) + "\n")

    def events(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in self.stream.getvalue().splitlines()
            if line
        ]


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "A" * 32,
        "a" * 31,
        "a" * 33,
        "g" * 32,
        "../" + "a" * 32,
    ],
)
def test_request_id_validation_is_strict(value) -> None:
    assert normalize_request_id(value) is None

    with bind_request_id(value) as generated:
        assert re.fullmatch(r"[0-9a-f]{32}", generated)
        assert get_request_id() == generated

    assert get_request_id() is None


def test_request_id_is_extracted_from_langgraph_config() -> None:
    assert (
        request_id_from_runnable_config(
            {
                "configurable": {"request_id": VALID_REQUEST_ID},
                "metadata": {"request_id": OTHER_REQUEST_ID},
            }
        )
        == VALID_REQUEST_ID
    )
    assert (
        request_id_from_runnable_config(
            {"metadata": {"request_id": OTHER_REQUEST_ID}}
        )
        == OTHER_REQUEST_ID
    )
    assert (
        request_id_from_runnable_config(
            {"configurable": {"request_id": "unsafe"}}
        )
        is None
    )


def test_json_formatter_redacts_and_drops_unbounded_fields(monkeypatch) -> None:
    secret = "test-observability-secret-value"
    monkeypatch.setattr(config, "JWT_SECRET_KEY", secret)
    record = logging.LogRecord(
        "deep_data_agent.test",
        logging.ERROR,
        __file__,
        1,
        "Authorization: Bearer %s password=%s",
        ("X" * 24, secret),
        None,
    )
    record.event_name = "test.failed"
    record.event_fields = {
        "operation": "verify",
        "outcome": "error",
        "duration_ms": 1.23456,
        "prompt": "private prompt",
        "route": "/api/sessions/{session_id}",
        "unsafe": {"nested": "value"},
    }

    with bind_request_id(VALID_REQUEST_ID):
        payload = json.loads(RedactingFormatter().format(record))

    assert payload["schema_version"] == "1.0"
    assert payload["request_id"] == VALID_REQUEST_ID
    assert payload["event"] == "test.failed"
    assert payload["operation"] == "verify"
    assert payload["duration_ms"] == 1.235
    assert payload["route"] == "/api/sessions/{session_id}"
    assert "[REDACTED]" in payload["message"]
    assert secret not in payload["message"]
    assert "prompt" not in payload
    assert "unsafe" not in payload


def test_json_formatter_does_not_emit_raw_exception_text() -> None:
    try:
        raise RuntimeError("private prompt and upstream response")
    except RuntimeError:
        record = logging.LogRecord(
            "deep_data_agent.test",
            logging.ERROR,
            __file__,
            1,
            "operation failed",
            (),
            sys.exc_info(),
        )

    payload = json.loads(RedactingFormatter().format(record))

    assert payload["exception"] == "builtins.RuntimeError"
    assert "private prompt" not in json.dumps(payload)
    assert "upstream response" not in json.dumps(payload)


def test_middleware_reuses_valid_id_and_replaces_invalid_id() -> None:
    capture = _JsonCapture()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    try:
        valid = _request(
            "GET",
            "/api/health?ignored=private",
            headers={"X-Request-ID": VALID_REQUEST_ID},
        )
        invalid = _request(
            "GET",
            "/api/health",
            headers={"X-Request-ID": "INVALID-REQUEST-ID"},
        )
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)

    assert valid.status_code == 200
    assert valid.headers["X-Request-ID"] == VALID_REQUEST_ID
    replacement = invalid.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", replacement)
    assert replacement != "INVALID-REQUEST-ID"

    health_events = [
        event
        for event in capture.events()
        if event["event"] == "health.check"
    ]
    assert {event["request_id"] for event in health_events} == {
        VALID_REQUEST_ID,
        replacement,
    }
    assert all(event["route"] == "/api/health" for event in health_events)
    assert "private" not in json.dumps(health_events)
    assert "INVALID-REQUEST-ID" not in capture.stream.getvalue()


def test_cors_allows_and_exposes_request_id() -> None:
    preflight = _request(
        "OPTIONS",
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Request-ID",
        },
    )
    actual = _request(
        "GET",
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "X-Request-ID": VALID_REQUEST_ID,
        },
    )

    assert preflight.status_code == 200
    assert "x-request-id" in preflight.headers[
        "access-control-allow-headers"
    ].lower()
    assert actual.headers["access-control-expose-headers"].lower() == (
        "x-request-id"
    )
    assert actual.headers["X-Request-ID"] == VALID_REQUEST_ID


def test_agent_error_response_uses_middleware_request_id(monkeypatch) -> None:
    from data_agent import agent_server

    actor = User(id=1, role=UserRole.USER.value)
    previous_overrides = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_current_user] = lambda: actor
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "ainvoke",
        AsyncMock(side_effect=ConfigurationError("model unavailable")),
    )

    try:
        response = _request(
            "POST",
            "/api/query",
            headers={"X-Request-ID": VALID_REQUEST_ID},
            json={"query": "test"},
        )
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == VALID_REQUEST_ID
    assert response.json()["detail"]["request_id"] == VALID_REQUEST_ID


def test_agent_service_propagates_request_id_to_langgraph(monkeypatch) -> None:
    monkeypatch.setattr(
        "data_agent.services.agent_service.global_cache_service",
        SimpleNamespace(
            aget=AsyncMock(return_value=None),
            aset=AsyncMock(return_value=True),
        ),
    )
    message = SimpleNamespace(content="answer")
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [message]})
    service = AgentService(
        agent=agent,
        lease_manager=_AllowLeaseManager(),
    )

    actor = User(id=1, role=UserRole.USER.value)
    assert (
        asyncio.run(
            service.ainvoke(
                "query",
                actor=actor,
                request_id=VALID_REQUEST_ID,
            )
        )
        == "answer"
    )

    _, kwargs = agent.ainvoke.call_args
    assert kwargs["config"]["configurable"]["request_id"] == VALID_REQUEST_ID
    assert kwargs["config"]["metadata"]["request_id"] == VALID_REQUEST_ID


def test_log_rotation_config_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("LOG_MAX_BYTES", "1024")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "2")
    runtime_config = Config()

    assert runtime_config.LOG_MAX_BYTES == 1024
    assert runtime_config.LOG_BACKUP_COUNT == 2

    for invalid_value in ("0", "-1"):
        monkeypatch.setenv("LOG_BACKUP_COUNT", invalid_value)
        with pytest.raises(ConfigurationError, match="positive"):
            Config()


def test_emit_event_uses_only_safe_fields() -> None:
    capture = _JsonCapture()
    test_logger = logging.getLogger("deep_data_agent.test.event")
    previous_level = test_logger.level
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(capture)
    try:
        with bind_request_id(VALID_REQUEST_ID):
            emit_event(
                test_logger,
                "tool.completed",
                operation="search",
                tool_name="internet_search",
                outcome="success",
                duration_ms=2,
                raw_output="must-not-be-logged",
            )
    finally:
        test_logger.removeHandler(capture)
        test_logger.setLevel(previous_level)

    payload = capture.events()[0]
    assert payload["request_id"] == VALID_REQUEST_ID
    assert payload["tool_name"] == "internet_search"
    assert "raw_output" not in payload
