import asyncio
import json
import logging
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from data_agent import agent_server
from data_agent.config.config import config
from data_agent.config.logger import RedactingFormatter, rate_limit_logger
from data_agent.observability import rate_limit_middleware
from data_agent.services.auth_service import create_access_token
from data_agent.services.rate_limit_service import RateLimitDecision

TEST_JWT_SECRET = "rate-limit-suite-secret-with-at-least-32-characters"

# 允许出现在脱敏后限流事件里的字段：标准载荷键 + 白名单安全字段。
_ALLOWED_EVENT_KEYS = {
    "schema_version",
    "timestamp",
    "level",
    "service",
    "logger",
    "event",
    "message",
    "request_id",
    "scope",
    "identity_kind",
    "decision",
    "outcome",
    "limit",
    "remaining",
    "retry_after",
    "window_seconds",
    "operation",
}


def _request(method: str, path: str, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=agent_server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


class _JsonCapture(logging.Handler):
    """Collect rendered structured events exactly as they would be logged."""

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


class _StaticLimiter:
    """Return one preset decision and record every call's keyword args."""

    def __init__(self, decision: RateLimitDecision) -> None:
        self.decision = decision
        self.calls: list[dict[str, object]] = []

    def check(self, **kwargs) -> RateLimitDecision:
        self.calls.append(kwargs)
        return self.decision


class _CountingLimiter:
    """Deterministic per-identity fixed-window counter for isolation tests."""

    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []
        self._counts: dict[tuple[str, str], int] = {}

    def check(
        self,
        *,
        scope: str,
        identity_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        self.calls.append(
            SimpleNamespace(
                scope=scope,
                identity_key=identity_key,
                limit=limit,
                window_seconds=window_seconds,
            )
        )
        counter_key = (scope, identity_key)
        self._counts[counter_key] = self._counts.get(counter_key, 0) + 1
        count = self._counts[counter_key]
        allowed = count <= limit
        return RateLimitDecision(
            allowed=allowed,
            limit=limit,
            remaining=max(limit - count, 0),
            retry_after=0 if allowed else window_seconds,
            window_seconds=window_seconds,
        )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_over_limit_returns_stable_429(monkeypatch) -> None:
    limited = RateLimitDecision(
        allowed=False,
        limit=7,
        remaining=0,
        retry_after=42,
        window_seconds=60,
    )
    fake = _StaticLimiter(limited)
    monkeypatch.setattr(
        rate_limit_middleware, "global_rate_limit_service", fake
    )

    response = _request("POST", "/api/query", json={"query": "hi"})

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "rate_limited"
    request_id = detail["request_id"]
    assert isinstance(request_id, str) and len(request_id) == 32
    assert response.headers["Retry-After"] == "42"
    assert response.headers["X-RateLimit-Limit"] == "7"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-Request-ID"] == request_id
    # /api/query 归入 query 类别配额。
    assert fake.calls and fake.calls[0]["scope"] == "query"


def test_under_limit_passes_through_with_headers(monkeypatch) -> None:
    allowed = RateLimitDecision(
        allowed=True,
        limit=20,
        remaining=19,
        retry_after=0,
        window_seconds=60,
    )
    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        _StaticLimiter(allowed),
    )
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "invoke",
        Mock(return_value="ok"),
    )

    response = _request("POST", "/api/query", json={"query": "hi"})

    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert response.headers["X-RateLimit-Limit"] == "20"
    assert response.headers["X-RateLimit-Remaining"] == "19"


def test_health_check_is_exempt_and_emits_no_decision(monkeypatch) -> None:
    # 若限流服务被调用即为 bug：健康检查必须在 check 之前短路。
    def _fail_if_called(**kwargs):
        raise AssertionError("health check must not touch rate limiter")

    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        SimpleNamespace(check=_fail_if_called),
    )

    capture = _JsonCapture()
    previous_level = rate_limit_logger.level
    rate_limit_logger.setLevel(logging.INFO)
    rate_limit_logger.addHandler(capture)
    try:
        responses = [_request("GET", "/api/health") for _ in range(3)]
    finally:
        rate_limit_logger.removeHandler(capture)
        rate_limit_logger.setLevel(previous_level)

    assert all(response.status_code == 200 for response in responses)
    assert all(
        response.json() == {"status": "healthy"} for response in responses
    )
    assert all(
        not str(event["event"]).startswith("rate_limit")
        for event in capture.events()
    )


def test_distinct_identities_are_counted_independently(monkeypatch) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setattr(config, "RATE_LIMIT_QUERY_MAX_REQUESTS", 1)
    limiter = _CountingLimiter()
    monkeypatch.setattr(
        rate_limit_middleware, "global_rate_limit_service", limiter
    )
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "invoke",
        Mock(return_value="ok"),
    )

    token_a = create_access_token(1)
    token_b = create_access_token(2)

    first_a = _request(
        "POST", "/api/query", headers=_auth(token_a), json={"query": "1"}
    )
    second_a = _request(
        "POST", "/api/query", headers=_auth(token_a), json={"query": "2"}
    )
    first_b = _request(
        "POST", "/api/query", headers=_auth(token_b), json={"query": "3"}
    )

    # 用户 A 第二次触顶被拒，用户 B 不受 A 计数影响仍放行。
    assert first_a.status_code == 200
    assert second_a.status_code == 429
    assert first_b.status_code == 200

    identity_keys = {call.identity_key for call in limiter.calls}
    assert identity_keys == {"user:1", "user:2"}


def test_forged_forwarded_header_does_not_change_identity(monkeypatch) -> None:
    monkeypatch.setattr(config, "TRUSTED_PROXY_COUNT", 0)
    allowed = RateLimitDecision(
        allowed=True,
        limit=120,
        remaining=119,
        retry_after=0,
        window_seconds=60,
    )
    limiter = _StaticLimiter(allowed)
    monkeypatch.setattr(
        rate_limit_middleware, "global_rate_limit_service", limiter
    )

    forged = "203.0.113.7"
    _request("GET", "/api/does-not-exist")
    _request(
        "GET",
        "/api/does-not-exist",
        headers={"X-Forwarded-For": forged},
    )

    assert len(limiter.calls) == 2
    identity_without = limiter.calls[0]["identity_key"]
    identity_with = limiter.calls[1]["identity_key"]
    # 伪造转发头不改变匿名计数键，且计数键基于直连地址而非伪造 IP。
    assert identity_without == identity_with
    assert identity_with.startswith("ip:")
    assert forged not in identity_with


def test_rate_limit_events_do_not_leak_sensitive_values(monkeypatch) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    token = create_access_token(12345)
    forged = "198.51.100.23"
    # 固定请求 ID（全为十六进制字母）使脱敏子串断言完全确定，不会因随机
    # 十六进制请求 ID 偶然包含身份数字而抖动。
    fixed_request_id = "a" * 32

    capture = _JsonCapture()
    previous_level = rate_limit_logger.level
    rate_limit_logger.setLevel(logging.INFO)
    rate_limit_logger.addHandler(capture)
    try:
        # 先走真实（离线降级）限流服务，捕获 degraded + allowed 决策事件。
        monkeypatch.setattr(
            agent_server.global_agent_service,
            "invoke",
            Mock(return_value="ok"),
        )
        degraded_response = _request(
            "POST",
            "/api/query",
            headers={
                **_auth(token),
                "X-Forwarded-For": forged,
                "X-Request-ID": fixed_request_id,
            },
            json={"query": "secret business prompt"},
        )
        # 再用受控 limited 决策，捕获 limited 决策事件。
        limited = RateLimitDecision(
            allowed=False,
            limit=7,
            remaining=0,
            retry_after=15,
            window_seconds=60,
        )
        monkeypatch.setattr(
            rate_limit_middleware,
            "global_rate_limit_service",
            _StaticLimiter(limited),
        )
        limited_response = _request(
            "POST",
            "/api/query",
            headers={
                **_auth(token),
                "X-Forwarded-For": forged,
                "X-Request-ID": fixed_request_id,
            },
            json={"query": "another secret prompt"},
        )
    finally:
        rate_limit_logger.removeHandler(capture)
        rate_limit_logger.setLevel(previous_level)

    assert degraded_response.status_code == 200
    assert limited_response.status_code == 429

    events = capture.events()
    event_names = {str(event["event"]) for event in events}
    assert "rate_limit.degraded" in event_names
    assert "rate_limit.decision" in event_names
    decisions = {
        event.get("decision")
        for event in events
        if event["event"] == "rate_limit.decision"
    }
    assert {"allowed", "limited"} <= decisions

    serialized = json.dumps(events)
    for forbidden in (
        token,
        forged,
        "Bearer",
        "12345",
        "secret business prompt",
        "another secret prompt",
    ):
        assert forbidden not in serialized

    # 事件仅含维度类别、决策与配额相关安全字段，无原始身份或业务数据键。
    for event in events:
        assert set(event) <= _ALLOWED_EVENT_KEYS


def test_disabled_rate_limit_passes_through_without_counting(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)

    def _fail_if_called(**kwargs):
        raise AssertionError("disabled rate limiter must not be invoked")

    monkeypatch.setattr(
        rate_limit_middleware,
        "global_rate_limit_service",
        SimpleNamespace(check=_fail_if_called),
    )
    monkeypatch.setattr(
        agent_server.global_agent_service,
        "invoke",
        Mock(return_value="ok"),
    )

    response = _request("POST", "/api/query", json={"query": "hi"})

    assert response.status_code == 200
    # 关闭时不添加限流响应头，也不调用限流服务。
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
