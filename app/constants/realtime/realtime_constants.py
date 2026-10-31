"""Realtime socket: route, message types and timings."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1

PATH_REALTIME: Final[str] = f"{API_V1}/realtime"

# Client -> server
MESSAGE_AUTH: Final[str] = "auth"
# Server -> client
MESSAGE_READY: Final[str] = "ready"
MESSAGE_CHANGED: Final[str] = "changed"
MESSAGE_PING: Final[str] = "ping"

# Any shift was posted, edited, filled or cancelled.
TOPIC_SHIFTS: Final[str] = "shifts"
# This worker's Live Work requests changed (new offer, expired, withdrawn, taken).
TOPIC_LIVE_REQUESTS: Final[str] = "live_requests"

# Postgres LISTEN/NOTIFY channel fed by triggers in sql/relations/realtime_notify.sql.
NOTIFY_CHANNEL: Final[str] = "kn_realtime"
NOTIFY_SHIFTS: Final[str] = "shifts"
NOTIFY_LIVE_PREFIX: Final[str] = "live:"
# Retry delay after the listener connection fails.
LISTEN_RETRY_SECONDS: Final[float] = 3.0
# A silently dropped listener connection is noticed by this health query.
LISTEN_HEALTH_SECONDS: Final[float] = 30.0
AUTH_TIMEOUT_SECONDS: Final[float] = 10.0
# Keeps idle connections open through proxies and detects closed clients.
PING_SECONDS: Final[float] = 25.0
# Below the 300 s function limit on Vercel; clients reconnect when the server closes.
SESSION_SECONDS: Final[float] = 270.0

CLOSE_RECONNECT: Final[int] = 4000
CLOSE_UNAUTHORIZED: Final[int] = 4401
CLOSE_POLICY_VIOLATION: Final[int] = 1008
