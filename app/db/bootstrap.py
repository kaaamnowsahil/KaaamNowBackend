"""Apply ordered SQL from /sql, then the idempotent seed."""

from __future__ import annotations

from pathlib import Path

import asyncpg

from app.constants.application.application_constants import LOG_DATABASE_BOOTSTRAP_COMPLETE
from app.db.schema_apply_order import SCHEMA_SQL_RELATIVE_PATHS
from app.observability.logging import get_logger, log_extra
from app.paths import SEED_SQL, SQL_DIR

log = get_logger(__name__)

# Serialises concurrent boots (several API replicas starting at once).
_BOOTSTRAP_ADVISORY_LOCK_KEY = 7_420_001


async def _execute_sql_file(conn: asyncpg.Connection, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"schema SQL missing: {path}")
    await conn.execute(path.read_text())


async def bootstrap_database(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", _BOOTSTRAP_ADVISORY_LOCK_KEY)
            for relative in SCHEMA_SQL_RELATIVE_PATHS:
                await _execute_sql_file(conn, SQL_DIR / relative)
            if SEED_SQL.is_file():
                await conn.execute(SEED_SQL.read_text())
    log.info(
        LOG_DATABASE_BOOTSTRAP_COMPLETE,
        extra=log_extra(files=len(SCHEMA_SQL_RELATIVE_PATHS)),
    )
