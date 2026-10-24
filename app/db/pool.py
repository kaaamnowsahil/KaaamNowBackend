"""Shared asyncpg pool — single DATABASE_URL entry point."""

from __future__ import annotations

import json
from urllib.parse import urlparse, urlunparse

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import (
    LOG_DATABASE_CONNECTED,
    MSG_DATABASE_POOL_NOT_INITIALIZED,
)
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None


def redact_database_url(dsn: str) -> str:
    """Log-safe DSN with the password replaced by ``***``."""
    parsed = urlparse(dsn)
    if not parsed.password:
        return dsn
    netloc = f"{parsed.username or ''}:***@{parsed.hostname or ''}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Decode json/jsonb to Python objects on every pooled connection."""
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    settings = load_settings()
    target = dsn or settings.database_url
    _pool = await asyncpg.create_pool(
        dsn=target,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        command_timeout=settings.db_command_timeout_seconds,
        timeout=settings.db_connect_timeout_seconds,
        max_inactive_connection_lifetime=settings.db_max_idle_seconds,
        init=_init_connection,
    )
    log.info(LOG_DATABASE_CONNECTED, extra=log_extra(dsn=redact_database_url(target)))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(MSG_DATABASE_POOL_NOT_INITIALIZED)
    return _pool
