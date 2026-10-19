"""Admin verification queue for workers and businesses."""

from __future__ import annotations

from uuid import UUID

from app.constants.notifications.notification_route_strings import KIND_VERIFICATION_UPDATED
from app.constants.profiles.profile_route_strings import (
    MSG_BUSINESS_NOT_FOUND,
    MSG_WORKER_NOT_FOUND,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import not_found
from app.pagination import clamp_page_limit
from app.repositories.profiles import profile_repository
from app.schemas.profiles.profile_schemas import (
    BusinessProfileResponse,
    VerificationDecision,
    VerificationQueue,
    WorkerProfileResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_service import (
    business_profile_response,
    worker_profile_response,
)
from app.utils.clock import utc_now

_TITLES = {
    "verified": "You're verified",
    "rejected": "Verification needs attention",
}


async def list_queue(status: str, limit: int | None, offset: int) -> VerificationQueue:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        workers = await profile_repository.list_worker_verifications(
            conn, status, page_limit, offset
        )
        businesses = await profile_repository.list_business_verifications(
            conn, status, page_limit, offset
        )
    return VerificationQueue(
        workers=[worker_profile_response(r) for r in workers],
        businesses=[business_profile_response(r) for r in businesses],
    )


async def decide_worker(
    admin: AuthenticatedUser, worker_profile_id: UUID, body: VerificationDecision
) -> WorkerProfileResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            user_id = await profile_repository.set_worker_verification(
                conn,
                worker_profile_id,
                status=body.status,
                note=body.note,
                now=utc_now(),
                admin_user_id=admin.user_id,
            )
            if user_id is None:
                raise not_found("worker_not_found", MSG_WORKER_NOT_FOUND)
            await notify(
                conn,
                user_id,
                KIND_VERIFICATION_UPDATED,
                _TITLES[body.status],
                body.note or "",
                {"profile": "worker", "status": body.status},
            )
            row = await profile_repository.get_worker_profile(conn, worker_profile_id)
    return worker_profile_response(row)


async def decide_business(
    admin: AuthenticatedUser, business_profile_id: UUID, body: VerificationDecision
) -> BusinessProfileResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            user_id = await profile_repository.set_business_verification(
                conn,
                business_profile_id,
                status=body.status,
                note=body.note,
                now=utc_now(),
                admin_user_id=admin.user_id,
            )
            if user_id is None:
                raise not_found("business_not_found", MSG_BUSINESS_NOT_FOUND)
            await notify(
                conn,
                user_id,
                KIND_VERIFICATION_UPDATED,
                _TITLES[body.status],
                body.note or "",
                {"profile": "business", "status": body.status},
            )
            row = await profile_repository.get_business_profile(conn, business_profile_id)
    return business_profile_response(row)
