import logging
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import (BaseHTTPMiddleware,
                                       RequestResponseEndpoint)

from data_agent.config.logger import logger
from data_agent.observability.context import (bind_request_id,
                                              normalize_request_id)
from data_agent.observability.events import emit_event

REQUEST_ID_HEADER = "X-Request-ID"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path.startswith("/"):
        return path
    return "/unmatched"


def _outcome(status_code: int) -> str:
    if status_code < 400:
        return "success"
    if status_code < 500:
        return "rejected"
    return "error"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Bind request context and emit one bounded event per HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        requested_id = normalize_request_id(
            request.headers.get(REQUEST_ID_HEADER)
        )
        with bind_request_id(requested_id) as request_id:
            started_at = perf_counter()
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers[REQUEST_ID_HEADER] = request_id
                return response
            except Exception:
                logger.exception(
                    "Unhandled HTTP request failure",
                    extra={
                        "event_name": "http.request.failed",
                        "event_fields": {
                            "method": request.method,
                            "route": _route_template(request),
                            "status_code": status_code,
                            "outcome": "error",
                            "duration_ms": (
                                perf_counter() - started_at
                            )
                            * 1000,
                        },
                    },
                )
                raise
            finally:
                event_name = (
                    "health.check"
                    if _route_template(request) == "/api/health"
                    else "http.request.completed"
                )
                emit_event(
                    logger,
                    event_name,
                    level=(
                        logging.ERROR
                        if status_code >= 500
                        else logging.INFO
                    ),
                    method=request.method,
                    route=_route_template(request),
                    status_code=status_code,
                    outcome=_outcome(status_code),
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
