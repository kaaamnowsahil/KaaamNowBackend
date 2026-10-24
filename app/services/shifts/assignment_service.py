"""Booked worker lifecycle shared by both sides: detail, travel, tracking, chat, cancel."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.catalog.catalog_route_strings import (
    DIRECTION_BUSINESS_TO_WORKER,
    DIRECTION_WORKER_TO_BUSINESS,
)
from app.constants.notifications.notification_route_strings import (
    KIND_ASSIGNMENT_CANCELLED,
    KIND_NEW_MESSAGE,
    KIND_WORKER_EN_ROUTE,
)
from app.constants.shifts.shift_route_strings import (
    APP_WITHDRAWN,
    ASG_BOOKED_STATUSES,
    ASG_CANCELLED,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_CONFIRMED,
    ASG_EN_ROUTE,
    ASG_WORKED_STATUSES,
    MESSAGES_PAGE_LIMIT,
    MSG_ASSIGNMENT_NOT_FOUND,
    MSG_ASSIGNMENT_STATE,
    MSG_CANCEL_REASON_REQUIRED,
    MSG_SHIFT_NOT_FOUND,
    MSG_SHIFT_STARTED,
    MSG_TRAVEL_TOO_EARLY,
    MSG_WORKER_CANCELLATION_CUTOFF,
    SHIFT_FILLED,
    SHIFT_LIVE,
    SHIFT_OPEN,
    SHIFT_SEARCHING,
    TRAVEL_OPENS_HOURS_BEFORE,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.repositories.profiles import profile_repository
from app.repositories.ratings import rating_repository
from app.repositories.shifts import (
    application_repository,
    assignment_repository,
    shift_repository,
)
from app.schemas.shifts.assignment_schemas import (
    AssignmentCancelRequest,
    AssignmentCancelResponse,
    AssignmentDetail,
    ContactResponse,
    MessageCreate,
    MessageItem,
    RatingView,
    Roster,
    TrackingPoint,
    TrackingResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_lookup import business_scope
from app.services.shifts.domain.shift_mappers import (
    attendance_summary,
    business_card,
    roster_entry,
    worker_shift_card,
    worker_summary,
)
from app.services.shifts.domain.shift_rules import is_late_cancellation
from app.utils.clock import utc_now
from app.utils.geo import eta_minutes, haversine_km

PARTY_WORKER = "worker"
PARTY_BUSINESS = "business"


def caller_party(ctx: asyncpg.Record, user: AuthenticatedUser) -> str:
    """Which side of the assignment the caller is on; 404 for strangers."""
    if ctx["worker_user_id"] == user.user_id:
        return PARTY_WORKER
    if ctx["business_user_id"] == user.user_id:
        return PARTY_BUSINESS
    raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)


async def load_context(
    conn: asyncpg.Connection, assignment_id: UUID, user: AuthenticatedUser, *, lock: bool = False
) -> tuple[asyncpg.Record, str]:
    ctx = await (
        assignment_repository.lock_context(conn, assignment_id)
        if lock
        else assignment_repository.get_context(conn, assignment_id)
    )
    if ctx is None:
        raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
    return ctx, caller_party(ctx, user)


def _cancelled_by(ctx: asyncpg.Record) -> str | None:
    if ctx["cancelled_at"] is None:
        return None
    return PARTY_WORKER if ctx["cancelled_by_user_id"] == ctx["worker_user_id"] else PARTY_BUSINESS


def check_in_opens_at(ctx: asyncpg.Record) -> datetime:
    return ctx["starts_at"] - timedelta(minutes=load_settings().check_in_opens_minutes_before)


async def build_assignment_detail(
    conn: asyncpg.Connection, assignment_id: UUID, user: AuthenticatedUser
) -> AssignmentDetail:
    ctx, party = await load_context(conn, assignment_id, user)
    shift_row = await shift_repository.get_worker_shift(
        conn,
        ctx["shift_id"],
        worker_profile_id=ctx["worker_profile_id"],
        latitude=None,
        longitude=None,
    )
    worker_row = await assignment_repository.get_worker_summary(conn, ctx["worker_profile_id"])
    ratings = await rating_repository.list_ratings_for_assignment(conn, assignment_id)
    my_direction = (
        DIRECTION_WORKER_TO_BUSINESS if party == PARTY_WORKER else DIRECTION_BUSINESS_TO_WORKER
    )
    already_rated = any(r["direction"] == my_direction for r in ratings)
    return AssignmentDetail(
        id=ctx["id"],
        status=ctx["status"],
        source=ctx["source"],
        hourly_rate_minor=ctx["hourly_rate_minor"],
        confirmed_at=ctx["confirmed_at"],
        travel_started_at=ctx["travel_started_at"],
        cancelled_at=ctx["cancelled_at"],
        cancelled_by=_cancelled_by(ctx),
        cancel_reason=ctx["cancel_reason"],
        late_cancellation=ctx["late_cancellation"],
        applied_at=ctx["application_applied_at"],
        selected_at=ctx["application_decided_at"],
        shift=worker_shift_card(shift_row),
        worker=worker_summary(worker_row),
        business=business_card(shift_row),
        attendance=attendance_summary(ctx),
        ratings=[
            RatingView(
                direction=r["direction"],
                stars=r["stars"],
                tags=list(r["tags"]),
                review=r["review"],
                created_at=r["created_at"],
            )
            for r in ratings
        ],
        can_rate=ctx["status"] in ASG_WORKED_STATUSES and not already_rated,
        check_in_opens_at=check_in_opens_at(ctx),
    )


async def get_assignment(user: AuthenticatedUser, assignment_id: UUID) -> AssignmentDetail:
    async with get_pool().acquire() as conn:
        return await build_assignment_detail(conn, assignment_id, user)


async def roster(user: AuthenticatedUser, shift_id: UUID) -> Roster:
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        shift = await shift_repository.get_business_shift(conn, shift_id, scope)
        if shift is None:
            raise not_found("shift_not_found", MSG_SHIFT_NOT_FOUND)
        rows = await assignment_repository.list_roster(conn, shift_id)
    return Roster(
        shift_id=shift_id,
        workers_required=shift["workers_required"],
        booked_count=shift["booked_count"],
        items=[roster_entry(r) for r in rows],
    )


async def start_travel(user: AuthenticatedUser, assignment_id: UUID) -> AssignmentDetail:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            if party != PARTY_WORKER or ctx["status"] != ASG_CONFIRMED:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            opens = ctx["starts_at"] - timedelta(hours=TRAVEL_OPENS_HOURS_BEFORE)
            if ctx["shift_type"] != SHIFT_LIVE and now < opens:
                raise conflict("travel_too_early", MSG_TRAVEL_TOO_EARLY)
            await assignment_repository.start_travel(conn, assignment_id, now)
            await notify(
                conn,
                ctx["business_user_id"],
                KIND_WORKER_EN_ROUTE,
                "Your worker is on the way",
                ctx["job_title"],
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
            return await build_assignment_detail(conn, assignment_id, user)


async def tracking(user: AuthenticatedUser, assignment_id: UUID) -> TrackingResponse:
    settings = load_settings()
    async with get_pool().acquire() as conn:
        ctx, _ = await load_context(conn, assignment_id, user)
        location = None
        if ctx["status"] in (ASG_CONFIRMED, ASG_EN_ROUTE, ASG_CHECKED_IN):
            location = await profile_repository.get_worker_location(conn, ctx["worker_profile_id"])
    response = TrackingResponse(
        assignment_id=assignment_id,
        status=ctx["status"],
        travel_started_at=ctx["travel_started_at"],
        shift_latitude=ctx["shift_latitude"],
        shift_longitude=ctx["shift_longitude"],
    )
    if location is not None:
        distance = haversine_km(
            location["latitude"],
            location["longitude"],
            ctx["shift_latitude"],
            ctx["shift_longitude"],
        )
        response.worker_location = TrackingPoint(
            latitude=location["latitude"],
            longitude=location["longitude"],
            recorded_at=location["recorded_at"],
        )
        response.distance_km = round(distance, 2)
        response.eta_minutes = eta_minutes(distance, settings.tracking_average_speed_kmph)
    return response


async def contact(user: AuthenticatedUser, assignment_id: UUID) -> ContactResponse:
    async with get_pool().acquire() as conn:
        ctx, party = await load_context(conn, assignment_id, user)
        if ctx["status"] not in (ASG_CONFIRMED, ASG_EN_ROUTE, ASG_CHECKED_IN, ASG_CHECKED_OUT):
            raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
        if party == PARTY_WORKER:
            row = await assignment_repository.get_business_contact(conn, ctx["business_profile_id"])
            name = ctx["site_contact_name"] or row["full_name"] or row["business_name"]
            return ContactResponse(name=name, phone=row["phone"], role=PARTY_BUSINESS)
        row = await assignment_repository.get_worker_summary(conn, ctx["worker_profile_id"])
        return ContactResponse(name=row["full_name"], phone=row["phone"], role=PARTY_WORKER)


def _message_item(row: asyncpg.Record, user: AuthenticatedUser) -> MessageItem:
    return MessageItem(
        id=row["id"],
        sender_user_id=row["sender_user_id"],
        is_mine=row["sender_user_id"] == user.user_id,
        body=row["body"],
        read_at=row["read_at"],
        created_at=row["created_at"],
    )


async def list_messages(
    user: AuthenticatedUser, assignment_id: UUID, after: datetime | None
) -> list[MessageItem]:
    async with get_pool().acquire() as conn:
        await load_context(conn, assignment_id, user)
        rows = await assignment_repository.list_messages(
            conn, assignment_id, after=after, limit=MESSAGES_PAGE_LIMIT
        )
        await assignment_repository.mark_messages_read(conn, assignment_id, user.user_id, utc_now())
    return [_message_item(r, user) for r in rows]


async def send_message(
    user: AuthenticatedUser, assignment_id: UUID, body: MessageCreate
) -> MessageItem:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user)
            if ctx["status"] == ASG_CANCELLED:
                raise conflict("assignment_state", MSG_ASSIGNMENT_STATE)
            row = await assignment_repository.insert_message(
                conn, assignment_id, user.user_id, body.body
            )
            recipient = ctx["business_user_id"] if party == PARTY_WORKER else ctx["worker_user_id"]
            sender = ctx["business_name"] if party == PARTY_BUSINESS else "Your worker"
            await notify(
                conn,
                recipient,
                KIND_NEW_MESSAGE,
                f"New message from {sender}",
                body.body[:140],
                {"assignment_id": assignment_id, "shift_id": ctx["shift_id"]},
            )
    return _message_item(row, user)


async def _reopen_after_cancel(
    conn: asyncpg.Connection, ctx: asyncpg.Record, now: datetime, actor: UUID
) -> str:
    """A freed seat on a filled shift reopens recruiting if the shift hasn't started."""
    shift = await shift_repository.lock_shift(conn, ctx["shift_id"])
    if shift["status"] != SHIFT_FILLED or shift["starts_at"] <= now:
        return shift["status"]
    if shift["shift_type"] == SHIFT_LIVE:
        if shift["search_expires_at"] and shift["search_expires_at"] > now:
            target = SHIFT_SEARCHING
        else:
            return shift["status"]
    else:
        target = SHIFT_OPEN
    await shift_repository.set_status(
        conn,
        shift["id"],
        from_status=SHIFT_FILLED,
        to_status=target,
        now=now,
        actor_user_id=actor,
        reason="seat_freed",
    )
    return target


async def cancel(
    user: AuthenticatedUser, assignment_id: UUID, body: AssignmentCancelRequest, *, as_party: str
) -> AssignmentCancelResponse:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            ctx, party = await load_context(conn, assignment_id, user, lock=True)
            if party != as_party:
                raise not_found("assignment_not_found", MSG_ASSIGNMENT_NOT_FOUND)
            if ctx["status"] not in ASG_BOOKED_STATUSES:
                code_msg = (
                    MSG_SHIFT_STARTED if ctx["status"] == ASG_CHECKED_IN else MSG_ASSIGNMENT_STATE
                )
                raise conflict("assignment_state", code_msg)
            late = is_late_cancellation(ctx["starts_at"], ctx["cancellation_cutoff_hours"], now)
            if party == PARTY_WORKER and ctx["shift_type"] != SHIFT_LIVE:
                if late:
                    raise conflict(
                        "cancellation_cutoff",
                        MSG_WORKER_CANCELLATION_CUTOFF.format(
                            hours=ctx["cancellation_cutoff_hours"]
                        ),
                    )
                if not body.reason.strip():
                    raise bad_request("reason_required", MSG_CANCEL_REASON_REQUIRED)
            await assignment_repository.cancel_assignment(
                conn,
                assignment_id,
                now=now,
                actor_user_id=user.user_id,
                reason=body.reason,
                late=late,
            )
            if party == PARTY_WORKER and ctx["application_id"] is not None:
                await application_repository.set_response(
                    conn, ctx["application_id"], status=APP_WITHDRAWN, now=now
                )
            shift_status = await _reopen_after_cancel(conn, ctx, now, user.user_id)
            if party == PARTY_WORKER:
                recipient, title = ctx["business_user_id"], "A worker cancelled"
            else:
                recipient, title = ctx["worker_user_id"], "Your booking was cancelled"
            await notify(
                conn,
                recipient,
                KIND_ASSIGNMENT_CANCELLED,
                title,
                f"{ctx['job_title']}{' · ' + body.reason if body.reason else ''}",
                {"shift_id": ctx["shift_id"], "assignment_id": assignment_id},
            )
    return AssignmentCancelResponse(
        assignment_id=assignment_id,
        status=ASG_CANCELLED,
        late_cancellation=late,
        shift_status=shift_status,
    )
