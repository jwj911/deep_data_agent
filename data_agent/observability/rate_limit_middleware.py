from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import (BaseHTTPMiddleware,
                                       RequestResponseEndpoint)

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import rate_limit_logger
from data_agent.observability.context import (get_or_create_request_id,
                                              get_request_id)
from data_agent.observability.events import emit_event
from data_agent.observability.middleware import REQUEST_ID_HEADER
from data_agent.services.auth_service import ALGORITHM
from data_agent.services.rate_limit_service import (PROTECTION_DEGRADED,
                                                    PROTECTION_UNAVAILABLE,
                                                    global_rate_limit_service)
from data_agent.services.redis_recovery import AGENT_PROTECTION_UNAVAILABLE

_HEALTH_PATHS = frozenset({"/api/health", "/api/live", "/api/ready"})


def _resolve_scope(path: str) -> tuple[str, int, int]:
    """Map a request path to its rate-limit scope and quota bounds."""
    if path.startswith("/api/auth"):
        return (
            "auth",
            config.RATE_LIMIT_AUTH_MAX_REQUESTS,
            config.RATE_LIMIT_AUTH_WINDOW_SECONDS,
        )
    if path == "/api/query":
        return (
            "query",
            config.RATE_LIMIT_QUERY_MAX_REQUESTS,
            config.RATE_LIMIT_QUERY_WINDOW_SECONDS,
        )
    if path.startswith("/api/sessions") or path.startswith("/api/files"):
        return (
            "session",
            config.RATE_LIMIT_SESSION_MAX_REQUESTS,
            config.RATE_LIMIT_SESSION_WINDOW_SECONDS,
        )
    return (
        "default",
        config.RATE_LIMIT_DEFAULT_MAX_REQUESTS,
        config.RATE_LIMIT_DEFAULT_WINDOW_SECONDS,
    )


def _bearer_token(header: str | None) -> str | None:
    """Extract a bearer token from an Authorization header, if present."""
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _safe_token_subject(token: str) -> str | None:
    """Decode a token subject without side effects; never raise.

    Verifies only signature and expiry (no database lookup). Any failure
    falls back to anonymous; decode failures must never block a request or
    surface a 401 here -- 401 semantics stay with route dependencies.
    """
    try:
        secret_key = config.require_jwt_secret_key()
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"verify_exp": True, "require_exp": True},
        )
    except (JWTError, ConfigurationError, ValueError, TypeError):
        return None
    except Exception:
        # 任何其他异常也吞掉并回退匿名，绝不因解码失败而阻断请求。
        return None

    subject = payload.get("sub")
    if (
        isinstance(subject, str)
        and subject.isdigit()
        and int(subject) > 0
        and str(int(subject)) == subject
    ):
        return subject
    return None


def _client_ip(request: Request) -> str:
    """Resolve the client IP within the trusted proxy hop boundary."""
    direct = request.client.host if request.client else "unknown"
    trusted = config.TRUSTED_PROXY_COUNT
    if trusted > 0:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if len(hops) >= trusted:
                return hops[-trusted]
    return direct


def _resolve_identity(request: Request) -> tuple[str, str]:
    """Return (identity_kind, identity_key) for the current request."""
    token = _bearer_token(request.headers.get("Authorization"))
    if token is not None:
        subject = _safe_token_subject(token)
        if subject is not None:
            return "user", f"user:{subject}"
    return "anonymous", f"ip:{_client_ip(request)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-identity fixed-window rate limiting with stable 429 semantics."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # 关闭时直接透传：不计数、不解析身份、不触碰 Redis。
        if not config.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        # Health probes never consume request quota. Readiness performs its
        # own explicit Redis check after this short circuit.
        if path in _HEALTH_PATHS:
            return await call_next(request)

        scope, limit, window_seconds = _resolve_scope(path)
        identity_kind, identity_key = _resolve_identity(request)

        decision = global_rate_limit_service.check(
            scope=scope,
            identity_key=identity_key,
            limit=limit,
            window_seconds=window_seconds,
        )

        if decision.protection_status == PROTECTION_UNAVAILABLE:
            request_id = get_request_id() or get_or_create_request_id()
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": {
                        "code": AGENT_PROTECTION_UNAVAILABLE,
                        "message": (
                            "Agent protection is temporarily unavailable"
                        ),
                        "request_id": request_id,
                    }
                },
            )
            response.headers["Retry-After"] = str(decision.retry_after)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Protection"] = (
                decision.protection_status
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            emit_event(
                rate_limit_logger,
                "rate_limit.decision",
                scope=scope,
                identity_kind=identity_kind,
                decision="denied",
                outcome="rejected",
                error_code=AGENT_PROTECTION_UNAVAILABLE,
                limit=decision.limit,
                remaining=0,
                retry_after=decision.retry_after,
                window_seconds=decision.window_seconds,
                protection_status=decision.protection_status,
                protection_reason=decision.protection_reason,
            )
            return response

        if decision.allowed:
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(
                decision.remaining
            )
            response.headers["X-RateLimit-Protection"] = (
                decision.protection_status
            )
            emit_event(
                rate_limit_logger,
                "rate_limit.decision",
                scope=scope,
                identity_kind=identity_kind,
                decision="allowed",
                outcome=(
                    "degraded"
                    if decision.protection_status == PROTECTION_DEGRADED
                    else "success"
                ),
                limit=decision.limit,
                remaining=decision.remaining,
                window_seconds=decision.window_seconds,
                protection_status=decision.protection_status,
                protection_reason=decision.protection_reason,
            )
            return response

        request_id = get_request_id() or get_or_create_request_id()
        response = JSONResponse(
            status_code=429,
            content={
                "detail": {
                    "code": "rate_limited",
                    "message": "Too many requests",
                    "request_id": request_id,
                }
            },
        )
        response.headers["Retry-After"] = str(decision.retry_after)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        response.headers["X-RateLimit-Protection"] = (
            decision.protection_status
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        emit_event(
            rate_limit_logger,
            "rate_limit.decision",
            scope=scope,
            identity_kind=identity_kind,
            decision="limited",
            outcome="rejected",
            limit=decision.limit,
            remaining=0,
            retry_after=decision.retry_after,
            window_seconds=decision.window_seconds,
            protection_status=decision.protection_status,
            protection_reason=decision.protection_reason,
        )
        return response
