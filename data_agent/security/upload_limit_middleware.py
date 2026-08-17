from collections.abc import Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from data_agent.config.config import config

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
_UPLOAD_PATHS = frozenset({"/api/files", "/api/files/"})


class FileUploadBodyLimitMiddleware:
    """Buffer only file uploads under a strict pre-parser byte ceiling."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        code: str,
        message: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": {"code": code, "message": message}},
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in _UPLOAD_PATHS
        ):
            await self.app(scope, receive, send)
            return

        content_lengths = [
            value
            for key, value in scope.get("headers", [])
            if key.lower() == b"content-length"
        ]
        if len(content_lengths) > 1:
            await self._reject(
                scope,
                receive,
                send,
                status_code=400,
                code="invalid_content_length",
                message="Invalid upload request",
            )
            return
        if content_lengths:
            try:
                declared_length = int(content_lengths[0])
            except (TypeError, ValueError):
                declared_length = -1
            if declared_length < 0:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    code="invalid_content_length",
                    message="Invalid upload request",
                )
                return
            if declared_length > config.FILE_UPLOAD_REQUEST_MAX_BYTES:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    code="upload_request_too_large",
                    message="Upload request exceeds the configured limit",
                )
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    code="upload_disconnected",
                    message="Upload request did not complete",
                )
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > config.FILE_UPLOAD_REQUEST_MAX_BYTES:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    code="upload_request_too_large",
                    message="Upload request exceeds the configured limit",
                )
                return
            if not message.get("more_body", False):
                break

        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {
                "type": "http.request",
                "body": bytes(body),
                "more_body": False,
            }

        await self.app(scope, replay_receive, send)
