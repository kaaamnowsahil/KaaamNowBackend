"""Authoritative Live Work state for the Business and the Worker (polled by the apps)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.billing.billing_route_strings import INVOICE_KIND_DEPOSIT, INVOICE_KIND_FINAL
from app.constants.shifts.shift_route_strings import (
    ASG_APPROVED,
    ASG_CHECKED_IN,
    ASG_CHECKED_OUT,
    ASG_CONFIRMED,
    ASG_EN_ROUTE,
    DISPATCH_WITHDRAWN,
    PRICING_TASK,
    SHIFT_AWAITING_PAYMENT,
    SHIFT_CANCELLED,
    SHIFT_COMPLETED,
    SHIFT_EXPIRED,
    SHIFT_IN_PROGRESS,
    SHIFT_SEARCHING,
)
from app.repositories.earnings import earnings_repository
from app.repositories.live_work import live_work_repository
from app.repositories.live_work.live_work_repository import AvailableWorkersQuery
from app.repositories.profiles import profile_repository
from app.repositories.shifts import dispatch_repository
from app.schemas.live_work.live_work_schemas import (
    BusinessLiveActions,
    BusinessLiveBooking,
    LiveArrivalCodeView,
    LiveAssignmentView,
    LiveCancellationView,
    LiveExtensionView,
    LiveInvoiceSummary,
    LiveRefundView,
    LiveSearchView,
    LiveSeatActions,
    LiveSeatView,
    LiveTimerView,
    LiveWorkDetails,
    LiveWorkerArrivalView,
    LiveWorkerLocation,
    LiveWorkerView,
    WorkerLiveActions,
    WorkerLiveBooking,
    WorkerLiveEarnings,
)
from app.services.attendance import completion_codes
from app.services.catalog import catalog_service
from app.services.live_work import live_work_billing
from app.services.live_work.live_pricing_settings_service import breakdown, rates_from_row
from app.services.live_work.live_refund_service import REASON_UNFILLED_SEATS
from app.utils.geo import bounding_box_deltas, haversine_km

ACTIVE_ASSIGNMENT_STATUSES = (ASG_CONFIRMED, ASG_EN_ROUTE, ASG_CHECKED_IN)
BEFORE_START_STATUSES = (ASG_CONFIRMED, ASG_EN_ROUTE)
OPEN_EXTENSION_STATUSES = ("requested", "awaiting_payment")
CANCELLED_BY_PREFIXES = ("business", "worker", "system")
# Available-worker map: at most this many dots, rounded to 3 decimals (~110 m).
MAP_POINT_LIMIT = 50
MAP_POINT_DECIMALS = 3


def cancel_reason(party: str, reason: str) -> str:
    return f"{party}: {reason}".strip()[:300] if reason else party


def _split_reason(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    party, _, rest = value.partition(":")
    if party in CANCELLED_BY_PREFIXES:
        return party, rest.strip() or None
    return None, value


def business_status(shift_status: str, assignment: asyncpg.Record | None) -> str:
    if shift_status == SHIFT_AWAITING_PAYMENT:
        return "awaiting_payment"
    if shift_status == SHIFT_SEARCHING:
        return "searching"
    if shift_status == SHIFT_EXPIRED:
        return "no_workers"
    if shift_status == SHIFT_CANCELLED:
        return "cancelled"
    if shift_status == SHIFT_COMPLETED:
        return "completed"
    if shift_status == SHIFT_IN_PROGRESS:
        return "in_progress"
    if assignment is not None and assignment["status"] == ASG_EN_ROUTE:
        return "en_route"
    return "assigned"


def worker_status(assignment_status: str) -> str:
    return {
        ASG_CONFIRMED: "assigned",
        ASG_EN_ROUTE: "en_route",
        ASG_CHECKED_IN: "in_progress",
        ASG_CHECKED_OUT: "completed",
        ASG_APPROVED: "completed",
    }.get(assignment_status, "cancelled")


def _version(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def work_details(booking: asyncpg.Record, *, include_coordinates: bool) -> LiveWorkDetails:
    return LiveWorkDetails(
        category_slug=booking["category_slug"],
        category_name=booking["category_name"],
        job_title=booking["job_title"],
        description=booking["responsibilities"] or "",
        address_text=booking["address_text"] or "",
        latitude=booking["latitude"] if include_coordinates else None,
        longitude=booking["longitude"] if include_coordinates else None,
        arrival_instructions=booking["arrival_instructions"] or "",
        site_contact_name=booking["site_contact_name"] or "",
        business_name=booking["business_name"],
        pricing_mode=booking["pricing_mode"],
        reserved_minutes=booking["reserved_minutes"],
        hourly_rate_minor=booking["hourly_rate_minor"],
        task_price_minor=booking["task_price_minor"],
    )


def booking_breakdown(booking: asyncpg.Record):  # type: ignore[no-untyped-def]
    return breakdown(
        currency=booking["currency"],
        hourly_rate_minor=booking["hourly_rate_minor"],
        reserved_minutes=booking["reserved_minutes"],
        rates=rates_from_row(booking),
        charge=live_work_billing.snapshot_charge(booking),
        promo_code=booking["promo_code"],
        pricing_mode=booking["pricing_mode"],
        task_price_minor=booking["task_price_minor"],
        workers_required=booking["workers_required"],
    )


def extension_view(row: asyncpg.Record) -> LiveExtensionView:
    data = dict(row)
    for key in ("surcharge_pct", "commission_pct", "tax_pct"):
        data[key] = float(data[key])
    return LiveExtensionView.model_validate(data)


def invoice_summary(row: asyncpg.Record) -> LiveInvoiceSummary:
    return LiveInvoiceSummary(
        id=row["id"],
        invoice_kind=row["invoice_kind"],
        status=row["status"],
        total_minor=row["total_minor"],
        amount_due_minor=(
            max(row["total_minor"] - row["deposit_applied_minor"], 0)
            if row["status"] == "pending"
            else 0
        ),
        refund_due_minor=row["refund_due_minor"],
        paid_at=row["paid_at"],
    )


def _timer(
    booking: asyncpg.Record, assignment: asyncpg.Record | None, now: datetime
) -> LiveTimerView | None:
    if assignment is None or assignment["checked_in_at"] is None:
        return None
    running = assignment["status"] == ASG_CHECKED_IN
    if booking["pricing_mode"] == PRICING_TASK:
        # No countdown for a task: it ends when the job is done.
        return LiveTimerView(
            started_at=assignment["checked_in_at"],
            ends_at=None,
            reserved_minutes=0,
            extended_minutes=0,
            remaining_seconds=None,
            completed_at=assignment["checked_out_at"],
        )
    ends_at = assignment["checked_in_at"] + timedelta(
        minutes=booking["reserved_minutes"] + assignment["extended_minutes"]
    )
    return LiveTimerView(
        started_at=assignment["checked_in_at"],
        ends_at=ends_at,
        reserved_minutes=booking["reserved_minutes"],
        extended_minutes=assignment["extended_minutes"],
        remaining_seconds=max(int((ends_at - now).total_seconds()), 0) if running else None,
        completed_at=assignment["checked_out_at"],
    )


async def _worker_location(
    conn: asyncpg.Connection, booking: asyncpg.Record, assignment: asyncpg.Record, now: datetime
) -> tuple[LiveWorkerLocation | None, str]:
    if assignment["status"] not in ACTIVE_ASSIGNMENT_STATUSES:
        return None, "not_shared"
    row = await profile_repository.get_worker_location(conn, assignment["worker_profile_id"])
    if row is None:
        return None, "unavailable"
    age = max(int((now - row["recorded_at"]).total_seconds()), 0)
    stale = age > load_settings().location_freshness_seconds
    distance = haversine_km(
        row["latitude"], row["longitude"], booking["latitude"], booking["longitude"]
    )
    return (
        LiveWorkerLocation(
            latitude=row["latitude"],
            longitude=row["longitude"],
            accuracy_m=row["accuracy_m"],
            recorded_at=row["recorded_at"],
            age_seconds=age,
            is_stale=stale,
            distance_km=round(distance, 2),
        ),
        "stale" if stale else "live",
    )


async def _available_workers_query(
    conn: asyncpg.Connection,
    *,
    latitude: float,
    longitude: float,
    category_id: UUID | None,
    business_user_id: UUID,
    now: datetime,
) -> AvailableWorkersQuery:
    settings = load_settings()
    radius = (await catalog_service.search_radii(conn)).live_max_km
    lat_delta, lng_delta = bounding_box_deltas(latitude, radius)
    return AvailableWorkersQuery(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius,
        require_verified=settings.require_verified_workers,
        fresh_since=now - timedelta(seconds=settings.location_freshness_seconds),
        lat_delta=lat_delta,
        lng_delta=lng_delta,
        category_id=category_id,
        business_user_id=business_user_id,
        now=now,
    )


async def available_workers_near(
    conn: asyncpg.Connection,
    *,
    latitude: float,
    longitude: float,
    category_id: UUID | None,
    business_user_id: UUID,
    now: datetime,
) -> tuple[int, float]:
    query = await _available_workers_query(
        conn,
        latitude=latitude,
        longitude=longitude,
        category_id=category_id,
        business_user_id=business_user_id,
        now=now,
    )
    return await live_work_repository.count_available_workers(conn, query), query.radius_km


def blur_point(latitude: float, longitude: float) -> tuple[float, float]:
    """~110 m grid: shows where workers are without revealing exact positions."""
    return round(latitude, MAP_POINT_DECIMALS), round(longitude, MAP_POINT_DECIMALS)


async def available_worker_map(
    conn: asyncpg.Connection,
    *,
    latitude: float,
    longitude: float,
    category_id: UUID | None,
    business_user_id: UUID,
    now: datetime,
) -> tuple[int, float, list[tuple[float, float]]]:
    query = await _available_workers_query(
        conn,
        latitude=latitude,
        longitude=longitude,
        category_id=category_id,
        business_user_id=business_user_id,
        now=now,
    )
    count = await live_work_repository.count_available_workers(conn, query)
    rows = await live_work_repository.list_available_worker_points(conn, query, MAP_POINT_LIMIT)
    points = [blur_point(row["latitude"], row["longitude"]) for row in rows]
    return count, query.radius_km, points


def _arrival_flags(code: asyncpg.Record, now: datetime) -> tuple[int, bool, bool]:
    max_attempts = load_settings().live_arrival_max_attempts
    attempts_left = max(max_attempts - code["failed_attempts"], 0)
    return attempts_left, code["locked_at"] is not None, code["expires_at"] <= now


def _refund_view(row: asyncpg.Record) -> LiveRefundView:
    return LiveRefundView.model_validate(dict(row))


def _worker_view(seat: asyncpg.Record) -> LiveWorkerView:
    return LiveWorkerView(
        worker_id=seat["worker_profile_id"],
        full_name=seat["full_name"],
        photo_url=seat["photo_url"],
        rating_avg=float(seat["rating_avg"]) if seat["rating_avg"] is not None else None,
        rating_count=seat["rating_count"] or 0,
        completed_shift_count=seat["completed_shift_count"] or 0,
        verification_status=seat["verification_status"],
    )


async def _seat_view(
    conn: asyncpg.Connection,
    booking: asyncpg.Record,
    seat: asyncpg.Record,
    extensions: list[asyncpg.Record],
    invoices: list[asyncpg.Record],
    now: datetime,
) -> tuple[LiveSeatView, datetime | None]:
    """→ (one Worker's card, location timestamp for the version hash)."""
    location, location_status = await _worker_location(conn, booking, seat, now)
    arrival = None
    if seat["status"] in BEFORE_START_STATUSES:
        code = await live_work_repository.get_arrival_code(conn, seat["id"])
        if code is not None:
            attempts_left, locked, expired = _arrival_flags(code, now)
            arrival = LiveArrivalCodeView(
                code=code["code"],
                expires_at=code["expires_at"],
                attempts_left=attempts_left,
                locked=locked,
                expired=expired,
                verified=code["verified_at"] is not None,
            )
    working = seat["status"] == ASG_CHECKED_IN
    completion = (
        await completion_codes.load_view(conn, seat["id"], for_business=True) if working else None
    )
    final = next(
        (
            i
            for i in invoices
            if i["invoice_kind"] == INVOICE_KIND_FINAL and i["assignment_id"] == seat["id"]
        ),
        None,
    )
    open_ext = any(
        e["assignment_id"] == seat["id"] and e["status"] in OPEN_EXTENSION_STATUSES
        for e in extensions
    )
    view = LiveSeatView(
        assignment=LiveAssignmentView(
            assignment_id=seat["id"],
            status=seat["status"],
            accepted_at=seat["confirmed_at"],
            travel_started_at=seat["travel_started_at"],
            started_at=seat["checked_in_at"],
            completed_at=seat["checked_out_at"],
            ended_reason=seat["ended_reason"],
            worker=_worker_view(seat),
            location=location,
            location_status=location_status,  # type: ignore[arg-type]
        ),
        arrival_code=arrival,
        completion_code=completion,
        timer=_timer(booking, seat, now),
        actions=LiveSeatActions(
            can_cancel=seat["status"] in BEFORE_START_STATUSES or working,
            can_extend=working and not open_ext and booking["pricing_mode"] != PRICING_TASK,
            can_end_work=working,
            can_reissue_code=arrival is not None,
            can_reissue_completion_code=completion is not None and completion.can_reissue,
        ),
        final_invoice=invoice_summary(final) if final else None,
    )
    return view, location.recorded_at if location else None


async def build_business_state(
    conn: asyncpg.Connection, shift_id: UUID, now: datetime
) -> BusinessLiveBooking:
    booking = await live_work_repository.get_booking(conn, shift_id)
    all_seats = await live_work_repository.list_assignments(conn, shift_id)
    invoices = await live_work_repository.list_shift_invoices(conn, shift_id)
    extensions = await live_work_repository.list_extensions(conn, shift_id)
    refunds = await live_work_repository.list_refunds(conn, shift_id)
    first = all_seats[0] if all_seats else None
    status = business_status(booking["shift_status"], first)
    deposit = next((i for i in invoices if i["invoice_kind"] == INVOICE_KIND_DEPOSIT), None)
    final = next((i for i in invoices if i["invoice_kind"] == INVOICE_KIND_FINAL), None)

    search = None
    if status == "searching":
        count, _ = await available_workers_near(
            conn,
            latitude=booking["latitude"],
            longitude=booking["longitude"],
            category_id=booking["category_id"],
            business_user_id=booking["business_user_id"],
            now=now,
        )
        expires = booking["search_expires_at"]
        search = LiveSearchView(
            started_at=booking["search_started_at"],
            expires_at=expires,
            seconds_left=max(int((expires - now).total_seconds()), 0) if expires else 0,
            radius_km=booking["search_radius_km"],
            notified_workers=await dispatch_repository.count_dispatches(conn, shift_id),
            available_workers=count,
        )

    shown = (
        all_seats if status == "cancelled" else [a for a in all_seats if a["status"] != "cancelled"]
    )
    if status == "awaiting_payment":
        shown = []
    seats: list[LiveSeatView] = []
    markers: list[datetime | None] = []
    for seat in shown:
        view, marker = await _seat_view(conn, booking, seat, extensions, invoices, now)
        seats.append(view)
        markers.append(marker)
    # The single-Worker fields mirror the first card; N=1 bookings read exactly as before.
    lead = seats[0] if seats and status != "searching" else None

    cancellation = None
    if status == "cancelled":
        party, reason = _split_reason(booking["cancel_reason"])
        refund_total = sum(r["amount_minor"] for r in refunds)
        paid_total = sum(
            i["total_minor"]
            for i in invoices
            if i["status"] == "paid" and i["invoice_kind"] != INVOICE_KIND_FINAL
        )
        cancellation = LiveCancellationView(
            cancelled_at=booking["cancelled_at"],
            cancelled_by=party,  # type: ignore[arg-type]
            reason=reason,
            fee_minor=max(paid_total - refund_total, 0),
            refund_minor=refund_total,
        )

    working = any(v.assignment.status == ASG_CHECKED_IN for v in seats)
    active = any(v.assignment.status in ACTIVE_ASSIGNMENT_STATUSES for v in seats)
    open_ext = next((e for e in extensions if e["status"] in OPEN_EXTENSION_STATUSES), None)
    actions = BusinessLiveActions(
        can_pay=(
            status == "awaiting_payment" and deposit is not None and deposit["status"] == "pending"
        )
        or (open_ext is not None and open_ext["status"] == "awaiting_payment"),
        can_cancel=working
        or status in ("awaiting_payment", "searching", "assigned", "en_route")
        or (status == "in_progress" and active),
        can_extend=lead is not None and lead.actions.can_extend,
        can_end_work=working,
        can_reissue_code=lead is not None and lead.actions.can_reissue_code,
        can_repost=status in ("no_workers", "cancelled"),
        can_reissue_completion_code=lead is not None and lead.actions.can_reissue_completion_code,
    )
    version = _version(
        booking["updated_at"],
        booking["open_seats"],
        [(a["id"], a["updated_at"], a["checked_in_at"]) for a in all_seats],
        [(e["id"], e["status"]) for e in extensions],
        [(r["id"], r["status"]) for r in refunds],
        [(i["id"], i["status"]) for i in invoices],
        markers,
        [
            (
                v.arrival_code.attempts_left if v.arrival_code else None,
                v.arrival_code.code if v.arrival_code else None,
                v.completion_code.code if v.completion_code else None,
                v.completion_code.attempts_left if v.completion_code else None,
            )
            for v in seats
        ],
        search.available_workers if search else None,
        search.notified_workers if search else None,
    )
    return BusinessLiveBooking(
        booking_id=shift_id,
        status=status,  # type: ignore[arg-type]
        shift_status=booking["shift_status"],
        server_time=now,
        version=version,
        created_at=booking["created_at"],
        work=work_details(booking, include_coordinates=True),
        pricing=booking_breakdown(booking),
        search=search,
        deposit_invoice=invoice_summary(deposit) if deposit else None,
        assignment=lead.assignment if lead else None,
        arrival_code=lead.arrival_code if lead else None,
        completion_code=lead.completion_code if lead else None,
        timer=lead.timer if lead else None,
        extensions=[extension_view(e) for e in extensions],
        final_invoice=invoice_summary(final) if final else None,
        refunds=[_refund_view(r) for r in refunds],
        cancellation=cancellation,
        actions=actions,
        workers_required=booking["workers_required"],
        workers_filled=booking["workers_filled"],
        seat_total_minor=booking["total_minor"],
        unfilled_refund_minor=sum(
            r["amount_minor"] for r in refunds if r["reason"] == REASON_UNFILLED_SEATS
        ),
        workers=seats,
    )


async def build_worker_state(
    conn: asyncpg.Connection, assignment: asyncpg.Record, now: datetime
) -> WorkerLiveBooking:
    """``assignment``: an assignment context row (see assignment_repository.get_context)."""
    booking = await live_work_repository.get_booking(conn, assignment["shift_id"])
    status = worker_status(assignment["status"])
    extensions = [
        e
        for e in await live_work_repository.list_extensions(conn, assignment["shift_id"])
        if e["assignment_id"] == assignment["id"]
    ]
    applied_net = sum(e["worker_net_minor"] for e in extensions if e["status"] == "applied")
    arrival = None
    if assignment["status"] in BEFORE_START_STATUSES:
        code = await live_work_repository.get_arrival_code(conn, assignment["id"])
        if code is not None:
            attempts_left, locked, expired = _arrival_flags(code, now)
            arrival = LiveWorkerArrivalView(
                verified=code["verified_at"] is not None,
                attempts_left=attempts_left,
                locked=locked,
                expired=expired,
            )
    cancellation = None
    can_accept_again = False
    if status == "cancelled":
        party, reason = _split_reason(assignment["cancel_reason"])
        if party == "worker":
            can_accept_again = await _can_accept_again(conn, booking, assignment, now)
        cancellation = LiveCancellationView(
            cancelled_at=assignment["cancelled_at"],
            cancelled_by=party,  # type: ignore[arg-type]
            reason=reason,
            fee_minor=0,
            refund_minor=0,
        )
    timer_assignment = {
        "checked_in_at": assignment["checked_in_at"],
        "checked_out_at": assignment["checked_out_at"],
        "status": assignment["status"],
        "extended_minutes": assignment["extended_minutes"],
    }
    pending_answer = any(e["status"] == "requested" for e in extensions)
    completion = (
        await completion_codes.load_view(conn, assignment["id"], for_business=False)
        if assignment["status"] == ASG_CHECKED_IN
        else None
    )
    return WorkerLiveBooking(
        assignment_id=assignment["id"],
        booking_id=assignment["shift_id"],
        status=status,  # type: ignore[arg-type]
        server_time=now,
        version=_version(
            booking["updated_at"],
            assignment["updated_at"],
            assignment["checked_in_at"],
            [(e["id"], e["status"]) for e in extensions],
            arrival.attempts_left if arrival else None,
            arrival.locked if arrival else None,
            completion.attempts_left if completion else None,
            completion.locked if completion else None,
        ),
        work=work_details(booking, include_coordinates=status != "cancelled"),
        earnings=WorkerLiveEarnings(
            reserved_minutes=booking["reserved_minutes"],
            base_amount_minor=booking["base_amount_minor"],
            commission_pct=float(Decimal(booking["commission_pct"])),
            worker_commission_minor=booking["worker_commission_minor"],
            worker_net_minor=booking["worker_net_minor"],
            extension_net_minor=applied_net,
            total_net_minor=booking["worker_net_minor"] + applied_net,
            final_net_minor=(
                await earnings_repository.assignment_net(
                    conn, assignment["worker_profile_id"], assignment["id"]
                )
                if assignment["status"] in (ASG_CHECKED_OUT, ASG_APPROVED)
                else None
            ),
        ),
        arrival=arrival,
        completion=completion,
        timer=_timer(booking, timer_assignment, now),  # type: ignore[arg-type]
        extensions=[extension_view(e) for e in extensions],
        cancellation=cancellation,
        workers_required=booking["workers_required"],
        actions=WorkerLiveActions(
            can_start_travel=assignment["status"] == ASG_CONFIRMED,
            can_start_work=assignment["status"] in BEFORE_START_STATUSES,
            can_complete=assignment["status"] == ASG_CHECKED_IN,
            can_cancel=assignment["status"] in ACTIVE_ASSIGNMENT_STATUSES,
            can_answer_extension=pending_answer and assignment["status"] == ASG_CHECKED_IN,
            can_accept_again=can_accept_again,
        ),
    )


async def _can_accept_again(
    conn: asyncpg.Connection, booking: asyncpg.Record, assignment: asyncpg.Record, now: datetime
) -> bool:
    """Same rule as live accept: withdrawn dispatch, not re-accepted yet, search still open."""
    expires_at = booking["search_expires_at"]
    if booking["shift_status"] != SHIFT_SEARCHING or expires_at is None or expires_at <= now:
        return False
    dispatch = await dispatch_repository.get_dispatch(
        conn, assignment["shift_id"], assignment["worker_profile_id"]
    )
    return (
        dispatch is not None
        and dispatch["status"] == DISPATCH_WITHDRAWN
        and dispatch["reaccept_count"] == 0
    )
