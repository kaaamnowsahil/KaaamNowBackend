"""Completion code: issued when work starts, shown only to the Business, entered by the Worker
to finish any booking (Shift or Live Work, hourly or task)."""

from __future__ import annotations

import hmac
from datetime import datetime
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.attendance.attendance_route_strings import (
    MSG_COMPLETION_CODE_INVALID,
    MSG_COMPLETION_CODE_LOCKED,
    MSG_COMPLETION_CODE_REISSUE_LIMIT,
)
from app.exceptions.api_errors import ApiError, bad_request, conflict
from app.repositories.attendance import completion_code_repository
from app.schemas.attendance.attendance_schemas import CompletionCodeView
from app.utils.references import new_numeric_code

COMPLETION_CODE_LENGTH = 6
MSG_COMPLETION_CODE_MISSING = "Ask the Business for the completion code shown in their app."


def new_code() -> str:
    return new_numeric_code(COMPLETION_CODE_LENGTH)


async def issue(conn: asyncpg.Connection, assignment_id: UUID, shift_id: UUID) -> None:
    """Idempotent: keeps an existing code."""
    await completion_code_repository.insert_code(
        conn, assignment_id=assignment_id, shift_id=shift_id, code=new_code()
    )


def _locked_error() -> ApiError:
    return conflict("completion_code_locked", MSG_COMPLETION_CODE_LOCKED)


async def verify(
    conn: asyncpg.Connection, assignment_id: UUID, shift_id: UUID, entered: str, now: datetime
) -> ApiError | None:
    """``None`` when the code matches (marked verified). Otherwise the error to raise AFTER the
    caller's transaction commits, so wrong attempts (and a newly issued code) are kept."""
    settings = load_settings()
    row = await completion_code_repository.lock_code(conn, assignment_id)
    if row is None:
        await issue(conn, assignment_id, shift_id)
        return conflict("completion_code_missing", MSG_COMPLETION_CODE_MISSING)
    if row["locked_at"] is not None:
        return _locked_error()
    if hmac.compare_digest(entered.strip().encode(), row["code"].encode()):
        await completion_code_repository.set_verified(conn, assignment_id, now)
        return None
    failed = await completion_code_repository.record_failed_attempt(
        conn, assignment_id, max_attempts=settings.completion_code_max_attempts, now=now
    )
    if failed is None or failed["locked_at"] is not None:
        return _locked_error()
    left = max(settings.completion_code_max_attempts - failed["failed_attempts"], 0)
    return bad_request(
        "completion_code_invalid",
        MSG_COMPLETION_CODE_INVALID,
        {"attempts_left": left, "fields": {"completion_code": "Incorrect code"}},
    )


async def mark_used(conn: asyncpg.Connection, assignment_id: UUID, now: datetime) -> None:
    """Work ended another way (Business ended/stopped it): the code is no longer usable."""
    await completion_code_repository.set_verified(conn, assignment_id, now)


async def reissue(conn: asyncpg.Connection, assignment_id: UUID, shift_id: UUID) -> None:
    """Business issues a fresh code (e.g. after a lock-out)."""
    row = await completion_code_repository.lock_code(conn, assignment_id)
    if row is None:
        await issue(conn, assignment_id, shift_id)
        return
    if row["verified_at"] is not None:
        raise conflict("completion_code_used", "This booking is already completed.")
    if row["issued_count"] >= load_settings().completion_code_max_reissues:
        raise conflict("completion_code_reissue_limit", MSG_COMPLETION_CODE_REISSUE_LIMIT)
    await completion_code_repository.reissue_code(conn, assignment_id, code=new_code())


def view(row: asyncpg.Record | None, *, for_business: bool) -> CompletionCodeView | None:
    """Only while work is open (unverified)."""
    if row is None or row["verified_at"] is not None:
        return None
    settings = load_settings()
    locked = row["locked_at"] is not None
    return CompletionCodeView(
        code=row["code"] if for_business else None,
        attempts_left=max(settings.completion_code_max_attempts - row["failed_attempts"], 0),
        locked=locked,
        can_reissue=for_business and row["issued_count"] < settings.completion_code_max_reissues,
    )


async def load_view(
    conn: asyncpg.Connection, assignment_id: UUID, *, for_business: bool
) -> CompletionCodeView | None:
    return view(
        await completion_code_repository.get_code(conn, assignment_id), for_business=for_business
    )
