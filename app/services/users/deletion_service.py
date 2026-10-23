"""Self-service deletion requests, administrative review and safe processing."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

import asyncpg

from app.constants.admin.account_deletion_route_strings import (
    MSG_DELETION_APPROVAL_BLOCKED,
    MSG_DELETION_HOLD_EXPIRES,
    MSG_DELETION_HOLD_REASON,
)
from app.constants.auth.auth_route_strings import MSG_ACCOUNT_DISABLED
from app.constants.users.user_route_strings import MSG_DELETION_REQUEST_NOT_FOUND
from app.db.pool import get_pool
from app.exceptions.api_errors import (
    AuthenticationError,
    bad_request,
    conflict,
    not_found,
)
from app.repositories.users import deletion_repository as repository
from app.repositories.users import user_repository
from app.schemas.users.deletion_schemas import (
    AccountDeletionEvent,
    AccountDeletionHoldCreate,
    AccountDeletionRequestPage,
    AccountDeletionRequestResponse,
    AdminAccountDeletionRequest,
    AdminAccountDeletionRequestDetail,
    DeletionHold,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.users.sources.photo_storage import delete_images
from app.utils.clock import utc_now

_HOLD_MAX_DURATION = timedelta(days=30)
_HOLD_REVIEW_STATUSES = {"pending", "approved", "on_hold"}
_BLOCKER_LABELS = (
    ("active_shifts", "active shift"),
    ("active_bookings", "active booking"),
    ("pending_payments", "pending payment"),
    ("open_complaints", "open support case"),
    ("pending_verification_reviews", "pending verification review"),
)


def _blockers(row: Mapping[str, int]) -> list[str]:
    return [
        f"{row[column]} {label}{'' if row[column] == 1 else 's'}"
        for column, label in _BLOCKER_LABELS
        if row[column] > 0
    ]


async def _request_response(
    conn: asyncpg.Connection, row: asyncpg.Record
) -> AccountDeletionRequestResponse:
    now = utc_now()
    blocker_counts = await repository.get_blocker_counts(conn, row["user_id"])
    holds = await repository.list_active_holds(conn, row["id"], now)
    return AccountDeletionRequestResponse(
        id=row["id"],
        status=row["status"],
        requested_at=row["requested_at"],
        approved_at=row["approved_at"],
        completed_at=row["completed_at"],
        blockers=_blockers(blocker_counts),
        holds=[DeletionHold.model_validate(dict(hold)) for hold in holds],
    )


async def create_request(user: AuthenticatedUser) -> AccountDeletionRequestResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await user_repository.lock_user(conn, user.user_id)
            if not await user_repository.is_user_active(conn, user.user_id):
                raise AuthenticationError(MSG_ACCOUNT_DISABLED, code="account_disabled")
            row = await repository.get_open_request(conn, user.user_id)
            if row is None:
                row = await repository.create_request(conn, user.user_id)
                await repository.add_event(
                    conn,
                    row["id"],
                    user.user_id,
                    "requested",
                    {"requested_at": now.isoformat()},
                )
            return await _request_response(conn, row)


async def get_current_request(user_id: UUID) -> AccountDeletionRequestResponse:
    async with get_pool().acquire() as conn:
        row = await repository.get_open_request(conn, user_id)
        if row is None:
            row = await repository.get_latest_request(conn, user_id)
        if row is None:
            raise not_found("deletion_request_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
        return await _request_response(conn, row)


def _admin_request(
    row: asyncpg.Record, blockers: list[str], holds: list[asyncpg.Record]
) -> AdminAccountDeletionRequest:
    return AdminAccountDeletionRequest(
        id=row["id"],
        user_id=row["user_id"],
        status=row["status"],
        phone=row["phone"],
        full_name=row["full_name"],
        roles=list(row["roles"]),
        requested_at=row["requested_at"],
        approved_at=row["approved_at"],
        completed_at=row["completed_at"],
        blockers=blockers,
        holds=[DeletionHold.model_validate(dict(hold)) for hold in holds],
    )


async def list_requests(
    *, status_filter: str | None, limit: int, offset: int
) -> AccountDeletionRequestPage:
    async with get_pool().acquire() as conn:
        rows, total = await repository.list_requests(conn, status_filter, limit, offset)
        items: list[AdminAccountDeletionRequest] = []
        for row in rows:
            blockers = _blockers(await repository.get_blocker_counts(conn, row["user_id"]))
            holds = await repository.list_active_holds(conn, row["id"], utc_now())
            items.append(_admin_request(row, blockers, holds))
    return AccountDeletionRequestPage(items=items, total=total, limit=limit, offset=offset)


async def get_admin_request(request_id: UUID) -> AdminAccountDeletionRequestDetail:
    async with get_pool().acquire() as conn:
        row = await repository.get_admin_request(conn, request_id)
        if row is None:
            raise not_found("deletion_request_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
        blockers = _blockers(await repository.get_blocker_counts(conn, row["user_id"]))
        holds = await repository.list_active_holds(conn, row["id"], utc_now())
        events = await repository.list_events(conn, row["id"])
    request = _admin_request(row, blockers, holds)
    return AdminAccountDeletionRequestDetail(
        **request.model_dump(),
        events=[AccountDeletionEvent.model_validate(dict(event)) for event in events],
    )


async def approve_request(
    request_id: UUID, actor: AuthenticatedUser
) -> AdminAccountDeletionRequestDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            row = await repository.lock_request(conn, request_id)
            if row is None:
                raise not_found("deletion_request_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
            if row["status"] != "pending":
                raise conflict("deletion_request_not_pending", MSG_DELETION_APPROVAL_BLOCKED)
            blockers = _blockers(await repository.get_blocker_counts(conn, row["user_id"]))
            holds = await repository.list_active_holds(conn, row["id"], now)
            if blockers or holds:
                raise conflict(
                    "deletion_request_blocked",
                    MSG_DELETION_APPROVAL_BLOCKED,
                    {"blockers": blockers, "holds": [str(hold["id"]) for hold in holds]},
                )
            if not await repository.approve_request(conn, request_id, now):
                raise conflict("deletion_request_not_pending", MSG_DELETION_APPROVAL_BLOCKED)
            await repository.add_event(
                conn,
                request_id,
                actor.user_id,
                "approved",
                {"approved_at": now.isoformat()},
            )
    return await get_admin_request(request_id)


async def add_hold(
    request_id: UUID, body: AccountDeletionHoldCreate, actor: AuthenticatedUser
) -> AdminAccountDeletionRequestDetail:
    now = utc_now()
    if body.expires_at.tzinfo is None or body.expires_at.utcoffset() is None:
        raise bad_request("deletion_hold_invalid_expiry", MSG_DELETION_HOLD_EXPIRES)
    if body.expires_at <= now or body.expires_at > now + _HOLD_MAX_DURATION:
        raise bad_request("deletion_hold_invalid_expiry", MSG_DELETION_HOLD_EXPIRES)
    reason = body.reason.strip()
    if len(reason) < 20:
        raise bad_request("deletion_hold_reason_required", MSG_DELETION_HOLD_REASON)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            request = await repository.lock_request(conn, request_id)
            if request is None:
                raise not_found("deletion_request_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
            if request["status"] not in _HOLD_REVIEW_STATUSES:
                raise conflict("deletion_request_closed", MSG_DELETION_REQUEST_NOT_FOUND)
            hold = await repository.add_hold(
                conn,
                request_id,
                body.basis,
                reason,
                body.reference,
                body.expires_at,
                actor.user_id,
            )
            await repository.set_request_on_hold(conn, request_id)
            await repository.add_event(
                conn,
                request_id,
                actor.user_id,
                "hold_added",
                {
                    "hold_id": str(hold["id"]),
                    "basis": body.basis,
                    "reason": reason,
                    "reference": body.reference,
                    "expires_at": body.expires_at.isoformat(),
                },
            )
    return await get_admin_request(request_id)


async def release_hold(
    request_id: UUID, hold_id: UUID, actor: AuthenticatedUser
) -> AdminAccountDeletionRequestDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            request = await repository.lock_request(conn, request_id)
            if request is None:
                raise not_found("deletion_request_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
            if request["status"] not in _HOLD_REVIEW_STATUSES:
                raise conflict("deletion_request_closed", MSG_DELETION_REQUEST_NOT_FOUND)
            if not await repository.release_hold(conn, hold_id, request_id, now):
                raise not_found("deletion_hold_not_found", MSG_DELETION_REQUEST_NOT_FOUND)
            await repository.set_request_pending_if_no_holds(conn, request_id, now)
            await repository.add_event(
                conn,
                request_id,
                actor.user_id,
                "hold_released",
                {"hold_id": str(hold_id), "released_at": now.isoformat()},
            )
    return await get_admin_request(request_id)


async def process_deletion_requests(pool: asyncpg.Pool) -> int:
    """Re-check all blockers inside locked transactions before anonymizing."""
    processed = 0
    orphaned_images: list[str] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            candidates = await repository.lock_approved_requests(conn, 20)
            for candidate in candidates:
                now = utc_now()
                account = await repository.lock_user(conn, candidate["user_id"])
                if account is None:
                    continue
                await repository.lock_user_profiles(conn, candidate["user_id"])
                blockers = _blockers(
                    await repository.get_blocker_counts(conn, candidate["user_id"])
                )
                holds = await repository.list_active_holds(conn, candidate["id"], now)
                if holds:
                    await repository.set_request_on_hold(conn, candidate["id"])
                    continue
                if blockers:
                    continue
                orphaned_images += await user_repository.list_profile_image_urls(
                    conn, candidate["user_id"]
                )
                await repository.anonymize_user(conn, candidate["user_id"], account["phone"], now)
                if await repository.complete_request(conn, candidate["id"], now):
                    await repository.add_event(
                        conn,
                        candidate["id"],
                        None,
                        "completed",
                        {"completed_at": now.isoformat()},
                    )
                    processed += 1
    await delete_images(orphaned_images)
    return processed


async def expire_holds(pool: asyncpg.Pool) -> int:
    expired = 0
    now = utc_now()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await repository.lock_expired_holds(conn, now, 100)
            for hold in rows:
                await repository.mark_hold_expired(conn, hold["id"])
                await repository.set_request_pending_if_no_holds(conn, hold["request_id"], now)
                await repository.add_event(
                    conn,
                    hold["request_id"],
                    None,
                    "hold_expired",
                    {
                        "hold_id": str(hold["id"]),
                        "expired_at": now.isoformat(),
                    },
                )
                expired += 1
    return expired
