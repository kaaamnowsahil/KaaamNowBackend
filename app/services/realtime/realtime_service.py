"""Realtime socket session: authenticate, then forward change signals until the client leaves.

The access token travels in the first message, never in the URL, so it stays out of access logs.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_WORKER
from app.constants.auth.auth_route_strings import (
    MSG_ACCOUNT_DISABLED,
    MSG_AUTHENTICATION_REQUIRED,
)
from app.constants.realtime.realtime_constants import (
    AUTH_TIMEOUT_SECONDS,
    CLOSE_POLICY_VIOLATION,
    CLOSE_RECONNECT,
    CLOSE_UNAUTHORIZED,
    MESSAGE_AUTH,
    MESSAGE_CHANGED,
    MESSAGE_PING,
    MESSAGE_READY,
    PING_SECONDS,
    SESSION_SECONDS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import AuthenticationError
from app.repositories.realtime import realtime_repository
from app.repositories.users import user_repository
from app.security.jwt_tokens import verify_access_token
from app.services.realtime.realtime_hub import RealtimeHub, Subscription, hub

_CLIENT_GONE = (WebSocketDisconnect, RuntimeError, OSError)


def origin_allowed(origin: str | None, cors_origin: str) -> bool:
    """Browsers must come from an allowed origin; native apps send no Origin header."""
    allowed = [value.strip() for value in cors_origin.split(",") if value.strip()]
    return origin is None or allowed == ["*"] or origin in allowed


async def identify(token: str) -> UUID | None:
    """Verify the token and return the worker profile id (None for Business-only accounts)."""
    user = verify_access_token(token, load_settings())
    async with get_pool().acquire() as conn:
        if not await user_repository.is_user_active(conn, user.user_id):
            raise AuthenticationError(MSG_ACCOUNT_DISABLED, code="account_disabled")
        if ROLE_WORKER not in user.roles:
            return None
        return await realtime_repository.worker_profile_id(conn, user.user_id)


async def _authenticate(websocket: WebSocket) -> UUID | None:
    message = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
    token = message.get("token") if isinstance(message, dict) else None
    if message.get("type") != MESSAGE_AUTH or not isinstance(token, str) or not token:
        raise AuthenticationError(MSG_AUTHENTICATION_REQUIRED)
    return await identify(token)


async def _until_disconnect(websocket: WebSocket) -> None:
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass


async def _forward(websocket: WebSocket, subscription: Subscription) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SESSION_SECONDS
    gone = asyncio.create_task(_until_disconnect(websocket))
    try:
        while not gone.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                await websocket.close(code=CLOSE_RECONNECT)
                return
            change = asyncio.create_task(subscription.next())
            done, _ = await asyncio.wait(
                {change, gone},
                timeout=min(remaining, PING_SECONDS),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if change in done:
                await websocket.send_json({"type": MESSAGE_CHANGED, "topic": change.result()})
                continue
            change.cancel()
            if not gone.done():
                await websocket.send_json({"type": MESSAGE_PING})
    finally:
        gone.cancel()


async def serve(websocket: WebSocket, realtime_hub: RealtimeHub = hub) -> None:
    if not origin_allowed(websocket.headers.get("origin"), load_settings().cors_origin):
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return
    await websocket.accept()
    try:
        worker_profile_id = await _authenticate(websocket)
    except (AuthenticationError, TimeoutError, ValueError, KeyError, AttributeError):
        with contextlib.suppress(*_CLIENT_GONE):
            await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    except _CLIENT_GONE:
        return
    subscription = realtime_hub.subscribe(worker_profile_id)
    try:
        await websocket.send_json({"type": MESSAGE_READY})
        await _forward(websocket, subscription)
    except _CLIENT_GONE:
        pass
    finally:
        realtime_hub.unsubscribe(subscription)
