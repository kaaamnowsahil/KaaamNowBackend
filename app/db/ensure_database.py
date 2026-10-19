"""Create the target database on boot when it is missing (local/dev convenience)."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import asyncpg

from app.constants.application.application_constants import LOG_DATABASE_CREATED
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)


def _maintenance_dsn(dsn: str) -> tuple[str, str]:
    parsed = urlparse(dsn)
    database = (parsed.path or "").lstrip("/") or "postgres"
    return urlunparse(parsed._replace(path="/postgres")), database


async def ensure_database_exists(dsn: str) -> None:
    maintenance_dsn, database = _maintenance_dsn(dsn)
    conn = await asyncpg.connect(maintenance_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if exists:
            return
        quoted = '"' + database.replace('"', '""') + '"'
        await conn.execute(f"CREATE DATABASE {quoted}")
        log.info(LOG_DATABASE_CREATED, extra=log_extra(database=database))
    finally:
        await conn.close()
