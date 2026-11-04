"""Apply ordered SQL from /sql, then the idempotent seed."""

from __future__ import annotations

import hashlib
from pathlib import Path

import asyncpg

from app.constants.application.application_constants import LOG_DATABASE_BOOTSTRAP_COMPLETE
from app.db.advisory_locks import BOOTSTRAP_ADVISORY_LOCK_KEY, SWEEP_ADVISORY_LOCK_KEY
from app.db.schema_apply_order import SCHEMA_SQL_RELATIVE_PATHS
from app.observability.logging import get_logger, log_extra
from app.paths import SEED_SQL, SQL_DIR

log = get_logger(__name__)


async def _execute_sql_file(conn: asyncpg.Connection, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"schema SQL missing: {path}")
    await conn.execute(path.read_text())


_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_bootstrap_state (
    id          BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
    fingerprint TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
_SAVE_FINGERPRINT = """
INSERT INTO schema_bootstrap_state (id, fingerprint) VALUES (true, $1)
ON CONFLICT (id) DO UPDATE SET fingerprint = EXCLUDED.fingerprint, applied_at = now()
"""


def _sql_files() -> list[Path]:
    files = [SQL_DIR / relative for relative in SCHEMA_SQL_RELATIVE_PATHS]
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"schema SQL missing: {path}")
    return files + ([SEED_SQL] if SEED_SQL.is_file() else [])


def sql_fingerprint(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def _applied_fingerprint(conn: asyncpg.Connection) -> str | None:
    try:
        return await conn.fetchval("SELECT fingerprint FROM schema_bootstrap_state")
    except asyncpg.UndefinedTableError:
        return None


async def bootstrap_database(pool: asyncpg.Pool, *, force: bool = False) -> None:
    """Every schema file and the seed are idempotent; they are re-applied only when one of them
    changed since the last successful boot (one query otherwise, which keeps cold starts fast)."""
    files = _sql_files()
    fingerprint = sql_fingerprint(files)
    async with pool.acquire() as conn:
        if not force and await _applied_fingerprint(conn) == fingerprint:
            log.info(LOG_DATABASE_BOOTSTRAP_COMPLETE, extra=log_extra(files=0, unchanged=True))
            return
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", BOOTSTRAP_ADVISORY_LOCK_KEY)
            # Instances still running the previous deploy keep sweeping; waiting for their
            # sweep (and blocking new ones) avoids deadlocks between sweep queries and DDL.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", SWEEP_ADVISORY_LOCK_KEY)
            for path in files:
                await _execute_sql_file(conn, path)
            await conn.execute(_STATE_TABLE)
            await conn.execute(_SAVE_FINGERPRINT, fingerprint)
    log.info(
        LOG_DATABASE_BOOTSTRAP_COMPLETE,
        extra=log_extra(files=len(SCHEMA_SQL_RELATIVE_PATHS)),
    )
