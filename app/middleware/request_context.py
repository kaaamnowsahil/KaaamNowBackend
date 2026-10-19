"""Request id + structured access log for every HTTP request (pure ASGI, no body buffering)."""

from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.constants.application.application_common import PATH_HEALTH
from app.observability.logging import get_logger, log_extra
from app.utils.request_context import set_request_id

log = get_logger("http.access")

HEADER_REQUEST_ID = "x-request-id"
_QUIET_PATHS = frozenset({PATH_HEALTH, "/docs", "/openapi.json", "/favicon.ico"})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(HEADER_REQUEST_ID.encode(), b"").decode()[:64]
        request_id = incoming or f"req_{uuid.uuid4().hex[:20]}"
        set_request_id(request_id)
        started = time.perf_counter()
        status_holder: dict[str, int] = {"status": 500}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((HEADER_REQUEST_ID.encode(), request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            path = scope.get("path", "")
            if path not in _QUIET_PATHS:
                log.info(
                    "request",
                    extra=log_extra(
                        method=scope.get("method"),
                        path=path,
                        status=status_holder["status"],
                        duration_ms=round((time.perf_counter() - started) * 1000, 1),
                    ),
                )
            set_request_id(None)
