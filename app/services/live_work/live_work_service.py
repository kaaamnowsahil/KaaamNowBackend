"""Business side of Live Work: Post Work, Live Work status, Extend Work, cancel, End Work."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_BUSINESS
from app.constants.attendance.attendance_route_strings import MSG_TASK_NO_TIMING
from app.constants.notifications.notification_route_strings import KIND_EXTENSION_REQUESTED
from app.constants.shifts.shift_route_strings import (
    ASG_CHECKED_IN,
    CHECK_IN_CODE_LENGTH,
    PRICING_TASK,
    SHIFT_AWAITING_PAYMENT,
    SHIFT_CANCELLED,
    SHIFT_COMPLETED,
    SHIFT_DRAFT,
    SHIFT_LIVE,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request, conflict, not_found
from app.pagination import clamp_page_limit
from app.repositories.live_work import live_work_repository
from app.repositories.shifts import assignment_repository, shift_repository
from app.schemas.live_work.live_work_schemas import (
    BusinessLiveBooking,
    BusinessLiveBookingPage,
    LiveAvailableWorkers,
    LiveCancelPreview,
    LiveCancelRequest,
    LiveExtensionCreate,
    LiveExtensionQuote,
    LivePriceBreakdown,
    LiveWorkCreate,
    LiveWorkerDot,
    LiveWorkQuoteRequest,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.attendance import completion_codes
from app.services.cancellations import cancellation_service
from app.services.cancellations.cancellation_rules import SeatQuote
from app.services.catalog import catalog_service
from app.services.live_work import (
    live_refund_service,
    live_work_billing,
    live_work_core,
    live_work_hooks,
)
from app.services.live_work.live_pricing import (
    LiveCharge,
    LiveRates,
    LiveTerms,
    booking_charge,
    extension_charge,
    extension_rate,
    live_terms,
    validate_extension_minutes,
    validate_reserved_minutes,
)
from app.services.live_work.live_pricing_settings_service import active_rates, breakdown
from app.services.live_work.live_work_views import (
    available_worker_map,
    build_business_state,
    cancel_reason,
)
from app.services.notifications.notification_service import notify
from app.services.profiles.profile_lookup import business_scope, require_postable_business
from app.services.promos import promo_service
from app.services.promos.promo_rules import Promo
from app.services.users import terms_service
from app.utils.clock import utc_now
from app.utils.references import new_numeric_code

MSG_FIX_FIELDS = "Please correct the highlighted fields."


def field_errors(errors: dict[str, str]) -> ApiError:
    return bad_request("validation_error", MSG_FIX_FIELDS, {"fields": errors})


async def _owned_booking(
    conn: asyncpg.Connection, user: AuthenticatedUser, shift_id: UUID
) -> asyncpg.Record:
    scope = await business_scope(conn, user.user_id)
    pricing = await live_work_repository.get_booking_pricing(conn, shift_id)
    if pricing is None or pricing["business_profile_id"] not in scope:
        raise live_work_core.not_found_error()
    return pricing


def _terms(body: LiveWorkQuoteRequest | LiveWorkCreate) -> LiveTerms:
    return live_terms(
        pricing_mode=body.pricing_mode,
        hourly_rate_minor=body.hourly_rate_minor,
        duration_minutes=body.duration_minutes,
        task_price_minor=body.task_price_minor,
        task_window_minutes=load_settings().task_window_minutes,
    )


def _duration_error(terms: LiveTerms) -> str | None:
    return None if terms.is_task else validate_reserved_minutes(terms.reserved_minutes)


def _terms_charge(
    terms: LiveTerms, rates: LiveRates, promo: Promo | None, workers: int
) -> LiveCharge:
    """Per-Worker charge; the coupon is split across the Workers."""
    return booking_charge(
        terms.hourly_rate_minor,
        terms.reserved_minutes,
        rates,
        promo,
        task_price_minor=terms.task_price_minor if terms.is_task else None,
        workers=workers,
    )


def _workers_error(workers: int) -> str | None:
    limit = load_settings().live_max_workers
    return None if 1 <= workers <= limit else f"Choose between 1 and {limit} Workers."


async def quote(user: AuthenticatedUser, body: LiveWorkQuoteRequest) -> LivePriceBreakdown:
    terms = _terms(body)
    errors = {
        field: message
        for field, message in (
            ("duration_minutes", _duration_error(terms)),
            ("workers_required", _workers_error(body.workers_required)),
        )
        if message
    }
    if errors:
        raise field_errors(errors)
    workers = body.workers_required
    async with get_pool().acquire() as conn:
        if body.category_slug:
            await catalog_service.resolve_category_id(conn, body.category_slug)
        rates = await active_rates(conn)
        promo = (
            await promo_service.quote_live(
                conn,
                body.promo_code,
                user_id=user.user_id,
                amount_minor=terms.base_minor * workers,
            )
            if body.promo_code
            else None
        )
    return breakdown(
        currency=load_settings().default_currency,
        hourly_rate_minor=terms.hourly_rate_minor,
        reserved_minutes=terms.reserved_minutes,
        rates=rates,
        charge=_terms_charge(terms, rates, promo, workers),
        promo_code=promo.code if promo else None,
        pricing_mode=terms.pricing_mode,
        task_price_minor=terms.task_price_minor,
        workers_required=workers,
    )


async def available_workers(
    user: AuthenticatedUser, *, category_slug: str | None, latitude: float, longitude: float
) -> LiveAvailableWorkers:
    now = utc_now()
    async with get_pool().acquire() as conn:
        await business_scope(conn, user.user_id)
        category_id = (
            await catalog_service.resolve_category_id(conn, category_slug)
            if category_slug
            else None
        )
        count, radius, points = await available_worker_map(
            conn,
            latitude=latitude,
            longitude=longitude,
            category_id=category_id,
            business_user_id=user.user_id,
            now=now,
        )
    return LiveAvailableWorkers(
        count=count,
        radius_km=radius,
        category_slug=category_slug,
        fresh_within_seconds=load_settings().location_freshness_seconds,
        checked_at=now,
        workers=[LiveWorkerDot(latitude=lat, longitude=lng) for lat, lng in points],
    )


def _validate_create(body: LiveWorkCreate) -> None:
    errors: dict[str, str] = {}
    duration_error = _duration_error(_terms(body))
    if duration_error:
        errors["duration_minutes"] = duration_error
    workers_error = _workers_error(body.workers_required)
    if workers_error:
        errors["workers_required"] = workers_error
    if not body.accept_terms:
        errors["accept_terms"] = "Please accept the Live Work booking terms to continue."
    if body.latitude == 0 and body.longitude == 0:
        errors["address_text"] = "Pick the Work Location on the map."
    if errors:
        raise field_errors(errors)


async def _create_locked(
    conn: asyncpg.Connection, user: AuthenticatedUser, body: LiveWorkCreate
) -> UUID:
    now = utc_now()
    settings = load_settings()
    business = await require_postable_business(conn, user.user_id, body.business_profile_id)
    if body.idempotency_key:
        existing = await live_work_repository.find_booking_by_idempotency(
            conn, business["id"], body.idempotency_key
        )
        if existing is not None:
            return existing
    await terms_service.require_accepted(conn, user.user_id, ROLE_BUSINESS)
    terms = _terms(body)
    rates = await active_rates(conn)
    category_id = await catalog_service.resolve_category_id(conn, body.category_slug)
    shift_id = await shift_repository.insert_shift(
        conn,
        business_profile_id=business["id"],
        shift_type=SHIFT_LIVE,
        currency=settings.default_currency,
        check_in_code=new_numeric_code(CHECK_IN_CODE_LENGTH),
        values={
            "category_id": category_id,
            "job_title": body.job_title,
            "responsibilities": body.description,
            "requirements": "",
            "workers_required": body.workers_required,
            "pricing_mode": terms.pricing_mode,
            "hourly_rate_minor": terms.hourly_rate_minor,
            "task_price_minor": terms.task_price_minor,
            "starts_at": now,
            "ends_at": now + timedelta(minutes=terms.reserved_minutes),
            "break_minutes": 0,
            "workplace_name": business["business_name"],
            "address_text": body.address_text,
            "latitude": body.latitude,
            "longitude": body.longitude,
            "arrival_instructions": body.arrival_instructions,
            "site_contact_name": body.site_contact_name,
            "cancellation_cutoff_hours": 0,
        },
    )
    promo = (
        await promo_service.reserve_for_live(
            conn,
            body.promo_code,
            user_id=user.user_id,
            shift_id=shift_id,
            amount_minor=terms.base_minor * body.workers_required,
            now=now,
        )
        if body.promo_code
        else None
    )
    charge = _terms_charge(terms, rates, promo, body.workers_required)
    booking_total = charge.total_minor * body.workers_required
    if body.expected_total_minor is not None and body.expected_total_minor != booking_total:
        # Raised inside the posting transaction, so the shift and coupon hold roll back.
        raise conflict(
            "price_changed",
            "The price was updated. Please review the new total before posting.",
            {"total_minor": booking_total, "settings_version": rates.version},
        )
    await live_work_repository.insert_booking_pricing(
        conn,
        shift_id=shift_id,
        business_profile_id=business["id"],
        currency=settings.default_currency,
        hourly_rate_minor=terms.hourly_rate_minor,
        reserved_minutes=terms.reserved_minutes,
        rates=rates,
        charge=charge,
        idempotency_key=body.idempotency_key,
        promo_code_id=promo.id if promo else None,
        promo_code=promo.code if promo else None,
        pricing_mode=terms.pricing_mode,
        task_price_minor=terms.task_price_minor,
        workers_required=body.workers_required,
    )
    await live_work_repository.set_awaiting_payment(
        conn, shift_id, now=now, fee_policy_version=None, commission_pct=rates.commission_pct
    )
    await shift_repository.record_history(
        conn, shift_id, SHIFT_DRAFT, SHIFT_AWAITING_PAYMENT, user.user_id, "live_work_posted"
    )
    pricing = await live_work_repository.get_booking_pricing(conn, shift_id)
    await live_work_billing.create_deposit_invoice(conn, pricing, now)
    return shift_id


async def create(user: AuthenticatedUser, body: LiveWorkCreate) -> BusinessLiveBooking:
    _validate_create(body)
    async with get_pool().acquire() as conn:
        try:
            async with conn.transaction():
                shift_id = await _create_locked(conn, user, body)
        except asyncpg.UniqueViolationError:
            if not body.idempotency_key:
                raise
            scope = await business_scope(conn, user.user_id, body.business_profile_id)
            shift_id = await live_work_repository.find_booking_by_idempotency(
                conn, scope[0], body.idempotency_key
            )
            if shift_id is None:
                raise
        return await build_business_state(conn, shift_id, utc_now())


async def get_booking(user: AuthenticatedUser, shift_id: UUID) -> BusinessLiveBooking:
    async with get_pool().acquire() as conn:
        await _owned_booking(conn, user, shift_id)
        return await build_business_state(conn, shift_id, utc_now())


async def list_bookings(
    user: AuthenticatedUser, *, active_only: bool, limit: int | None, offset: int
) -> BusinessLiveBookingPage:
    page_limit = clamp_page_limit(limit)
    now = utc_now()
    async with get_pool().acquire() as conn:
        scope = await business_scope(conn, user.user_id)
        rows = await live_work_repository.list_business_bookings(
            conn, scope, active_only=active_only, limit=page_limit, offset=offset
        )
        items = [await build_business_state(conn, r["shift_id"], now) for r in rows]
    return BusinessLiveBookingPage(items=items, limit=page_limit, offset=offset)


def cancel_preview_view(plan: live_work_core.CancelPlan, currency: str) -> LiveCancelPreview:
    q = plan.quote
    return LiveCancelPreview(
        party=plan.party,  # type: ignore[arg-type]
        stage=plan.stage,  # type: ignore[arg-type]
        fee_minor=q.fee_minor if q else 0,
        worker_compensation_minor=q.worker_compensation_minor if q else 0,
        business_refund_minor=plan.refund_minor,
        business_retained_minor=q.business_retained_minor if q else 0,
        strike_weight=float(q.strike_weight) if q else 0.0,
        business_voucher=q.business_voucher if q else False,
        rule=plan.rule,
        effect=plan.effect,
        currency=currency,
    )


async def cancel_preview(user: AuthenticatedUser, shift_id: UUID) -> LiveCancelPreview:
    async with get_pool().acquire() as conn:
        pricing = await _owned_booking(conn, user, shift_id)
        shift = await live_work_repository.get_shift(conn, shift_id)
        plan = await live_work_core.business_cancel_plan(conn, shift, pricing)
    return cancel_preview_view(plan, pricing["currency"])


def _check_expected_refund(body: LiveCancelRequest, plan: live_work_core.CancelPlan) -> None:
    if body.expected_refund_minor is not None and body.expected_refund_minor != plan.refund_minor:
        raise conflict(
            "cancellation_terms_changed",
            "The booking changed. Please review the cancellation again.",
            {"refund_minor": plan.refund_minor},
        )


async def _release_worker(
    conn: asyncpg.Connection,
    *,
    shift: asyncpg.Record,
    seat: asyncpg.Record,
    quote: SeatQuote,
    reason: str,
    actor_user_id: UUID,
    now: datetime,
) -> None:
    """Business releases one Worker before they start: the seat's fee tier is recorded and the
    Worker is told. The caller refunds the rest of the seat."""
    await assignment_repository.cancel_assignment(
        conn,
        seat["id"],
        now=now,
        actor_user_id=actor_user_id,
        reason=cancel_reason("business", reason),
        late=quote.fee_minor > 0,
    )
    await cancellation_service.apply_seat(
        conn,
        shift=shift,
        assignment_id=seat["id"],
        worker_profile_id=seat["worker_profile_id"],
        worker_user_id=seat["worker_user_id"],
        quote=quote,
        actor_user_id=actor_user_id,
        now=now,
    )
    await live_work_core.close_open_extensions(conn, shift["id"], now, seat["id"])
    await live_work_core.notify_cancelled(
        conn,
        seat["worker_user_id"],
        "Live Work cancelled by the Business",
        shift["job_title"],
        {"shift_id": shift["id"], "assignment_id": seat["id"], "live_work": True},
    )


async def cancel(
    user: AuthenticatedUser, shift_id: UUID, body: LiveCancelRequest
) -> BusinessLiveBooking:
    """Cancel the whole booking (every Worker who hasn't started, and the empty seats)."""
    now = utc_now()
    refund_ids: list[UUID | None] = []
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            if shift["status"] == SHIFT_CANCELLED:
                return await build_business_state(conn, shift_id, now)
            plan = await live_work_core.business_cancel_plan(conn, shift, pricing)
            _check_expected_refund(body, plan)
            await live_work_core.withdraw_offers(conn, shift_id)
            for invoice in await live_work_repository.list_shift_invoices(conn, shift_id):
                await live_work_billing.void_invoice(conn, invoice["id"])
            if plan.stage in ("before_payment", "before_acceptance"):
                await promo_service.restore_for_booking(conn, shift_id, now)
            if plan.stage == "before_acceptance":
                refund_ids += await live_work_core.queue_split_refund(
                    conn,
                    shift_id,
                    plan.refund_minor,
                    live_refund_service.REASON_BUSINESS_CANCELLED,
                    user.user_id,
                )
            elif plan.stage in ("before_start", "during_work"):
                for seat, quote in plan.seats:
                    if seat["status"] == ASG_CHECKED_IN:
                        refund_ids += await live_work_core.business_force_stop(
                            conn,
                            shift=shift,
                            pricing=pricing,
                            assignment=await assignment_repository.lock_context(conn, seat["id"]),
                            actor_user_id=user.user_id,
                            now=now,
                        )
                        continue
                    await _release_worker(
                        conn,
                        shift=shift,
                        seat=seat,
                        quote=quote,
                        reason=body.reason,
                        actor_user_id=user.user_id,
                        now=now,
                    )
                    refund_ids += await live_work_core.queue_split_refund(
                        conn,
                        shift_id,
                        quote.business_refund_minor,
                        live_refund_service.REASON_BUSINESS_CANCELLED,
                        user.user_id,
                        assignment_id=seat["id"],
                    )
                if plan.empty_seat_refund_minor:
                    refund_ids += await live_work_core.queue_split_refund(
                        conn,
                        shift_id,
                        plan.empty_seat_refund_minor,
                        live_refund_service.REASON_BUSINESS_CANCELLED,
                        user.user_id,
                        deposit_only=True,
                        scope="empty_seats",
                    )
            seats = await live_work_repository.list_assignments(conn, shift_id)
            current = await shift_repository.lock_shift(conn, shift_id)
            if any(a["status"] in live_work_core.DONE_SEAT_STATUSES for a in seats):
                if current["status"] != SHIFT_COMPLETED:
                    await shift_repository.set_status(
                        conn,
                        shift_id,
                        from_status=current["status"],
                        to_status=SHIFT_COMPLETED,
                        now=now,
                        actor_user_id=user.user_id,
                        reason="business_cancelled_rest",
                    )
            else:
                await shift_repository.cancel_shift(
                    conn, shift_id, now=now, reason=cancel_reason("business", body.reason)
                )
                await shift_repository.record_history(
                    conn,
                    shift_id,
                    current["status"],
                    SHIFT_CANCELLED,
                    user.user_id,
                    "business_cancelled",
                )
        await live_refund_service.process_refunds(refund_ids)
        return await build_business_state(conn, shift_id, utc_now())


async def _owned_seat(
    conn: asyncpg.Connection, shift_id: UUID, assignment_id: UUID, *, lock: bool
) -> asyncpg.Record:
    seat = await (
        assignment_repository.lock_context(conn, assignment_id)
        if lock
        else assignment_repository.get_context(conn, assignment_id)
    )
    if seat is None or seat["shift_id"] != shift_id:
        raise live_work_core.not_found_error()
    return seat


async def cancel_worker_preview(
    user: AuthenticatedUser, shift_id: UUID, assignment_id: UUID
) -> LiveCancelPreview:
    async with get_pool().acquire() as conn:
        pricing = await _owned_booking(conn, user, shift_id)
        seat = await _owned_seat(conn, shift_id, assignment_id, lock=False)
        plan = await live_work_core.business_seat_cancel_plan(conn, pricing, seat)
    return cancel_preview_view(plan, pricing["currency"])


async def cancel_worker(
    user: AuthenticatedUser, shift_id: UUID, assignment_id: UUID, body: LiveCancelRequest
) -> BusinessLiveBooking:
    """Release one Worker before they start; the other Workers keep their booking."""
    now = utc_now()
    refund_ids: list[UUID | None] = []
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            seat = await _owned_seat(conn, shift_id, assignment_id, lock=True)
            if seat["status"] == "cancelled":
                return await build_business_state(conn, shift_id, now)
            plan = await live_work_core.business_seat_cancel_plan(conn, pricing, seat)
            _check_expected_refund(body, plan)
            quote = plan.quote
            assert quote is not None
            if plan.stage == "during_work":
                refund_ids = await live_work_core.business_force_stop(
                    conn,
                    shift=shift,
                    pricing=pricing,
                    assignment=seat,
                    actor_user_id=user.user_id,
                    now=now,
                )
                await live_refund_service.process_refunds(refund_ids)
                return await build_business_state(conn, shift_id, utc_now())
            await _release_worker(
                conn,
                shift=shift,
                seat=seat,
                quote=quote,
                reason=body.reason,
                actor_user_id=user.user_id,
                now=now,
            )
            refund_ids = await live_work_core.release_seat(
                conn,
                shift,
                pricing,
                assignment_id,
                plan.refund_minor,
                live_refund_service.REASON_BUSINESS_CANCELLED,
                user.user_id,
                now,
            )
        await live_refund_service.process_refunds(refund_ids)
        return await build_business_state(conn, shift_id, utc_now())


async def _seat_for_action(
    conn: asyncpg.Connection, shift_id: UUID, assignment_id: UUID | None, statuses: tuple[str, ...]
) -> asyncpg.Record:
    """The Worker an action targets: ``assignment_id``, or the first Worker in ``statuses``."""
    seats = await live_work_repository.list_assignments(conn, shift_id)
    if assignment_id is not None:
        seats = [a for a in seats if a["id"] == assignment_id]
        if not seats:
            raise live_work_core.not_found_error()
    seat = next((a for a in seats if a["status"] in statuses), None)
    if seat is None:
        raise live_work_core.state_error({"stage": seats[0]["status"] if seats else None})
    return seat


def _reject_task_extension(pricing: asyncpg.Record) -> None:
    if pricing["pricing_mode"] == PRICING_TASK:
        raise conflict("task_no_timing", MSG_TASK_NO_TIMING)


async def _extension_quote(
    conn: asyncpg.Connection,
    pricing: asyncpg.Record,
    extra_minutes: int,
    assignment_id: UUID | None = None,
) -> LiveExtensionQuote:
    """For one Worker: their reserved time + their applied extensions."""
    _reject_task_extension(pricing)
    applied = [
        e
        for e in await live_work_repository.list_extensions(conn, pricing["shift_id"])
        if e["status"] == "applied" and assignment_id in (None, e["assignment_id"])
    ]
    surcharge = Decimal(pricing["extension_surcharge_pct"])
    charge = extension_charge(
        pricing["hourly_rate_minor"],
        extra_minutes,
        surcharge_pct=surcharge,
        commission_pct=Decimal(pricing["commission_pct"]),
        tax_pct=Decimal(pricing["tax_pct"]),
        tax_base=pricing["tax_base"],
    )
    current_minutes = pricing["reserved_minutes"] + sum(e["extra_minutes"] for e in applied)
    current_total = pricing["total_minor"] + sum(e["total_minor"] for e in applied)
    return LiveExtensionQuote(
        original_minutes=pricing["reserved_minutes"],
        original_total_minor=pricing["total_minor"],
        current_minutes=current_minutes,
        additional_minutes=extra_minutes,
        base_rate_minor=pricing["hourly_rate_minor"],
        surcharge_pct=float(surcharge),
        extension_rate_minor=extension_rate(pricing["hourly_rate_minor"], surcharge),
        additional_base_minor=charge.base_amount_minor,
        commission_pct=float(pricing["commission_pct"]),
        commission_minor=charge.commission_minor,
        tax_label=pricing["tax_label"],
        tax_pct=float(pricing["tax_pct"]),
        tax_minor=charge.tax_minor,
        additional_total_minor=charge.total_minor,
        revised_minutes=current_minutes + extra_minutes,
        revised_total_minor=current_total + charge.total_minor,
        currency=pricing["currency"],
    )


async def extension_quote(
    user: AuthenticatedUser,
    shift_id: UUID,
    extra_minutes: int,
    assignment_id: UUID | None = None,
) -> LiveExtensionQuote:
    error = validate_extension_minutes(extra_minutes)
    if error:
        raise field_errors({"extra_minutes": error})
    async with get_pool().acquire() as conn:
        pricing = await _owned_booking(conn, user, shift_id)
        if assignment_id is None:
            seats = await live_work_repository.list_assignments(conn, shift_id)
            working = next((a for a in seats if a["status"] == ASG_CHECKED_IN), None)
            assignment_id = working["id"] if working else None
        elif not any(
            a["id"] == assignment_id
            for a in await live_work_repository.list_assignments(conn, shift_id)
        ):
            raise live_work_core.not_found_error()
        return await _extension_quote(conn, pricing, extra_minutes, assignment_id)


async def request_extension(
    user: AuthenticatedUser, shift_id: UUID, body: LiveExtensionCreate
) -> BusinessLiveBooking:
    error = validate_extension_minutes(body.extra_minutes)
    if error:
        raise field_errors({"extra_minutes": error})
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            assignment = await _seat_for_action(
                conn, shift_id, body.assignment_id, (ASG_CHECKED_IN,)
            )
            ext_quote = await _extension_quote(conn, pricing, body.extra_minutes, assignment["id"])
            if (
                body.expected_total_minor is not None
                and body.expected_total_minor != ext_quote.additional_total_minor
            ):
                raise conflict(
                    "price_changed",
                    "The extension price changed. Please review it again.",
                    {"total_minor": ext_quote.additional_total_minor},
                )
            surcharge = Decimal(pricing["extension_surcharge_pct"])
            charge = extension_charge(
                pricing["hourly_rate_minor"],
                body.extra_minutes,
                surcharge_pct=surcharge,
                commission_pct=Decimal(pricing["commission_pct"]),
                tax_pct=Decimal(pricing["tax_pct"]),
                tax_base=pricing["tax_base"],
            )
            try:
                async with conn.transaction():
                    await live_work_repository.insert_extension(
                        conn,
                        shift_id=shift_id,
                        assignment_id=assignment["id"],
                        extra_minutes=body.extra_minutes,
                        hourly_rate_minor=pricing["hourly_rate_minor"],
                        surcharge_pct=surcharge,
                        extension_rate_minor=ext_quote.extension_rate_minor,
                        commission_pct=Decimal(pricing["commission_pct"]),
                        tax_pct=Decimal(pricing["tax_pct"]),
                        tax_base=pricing["tax_base"],
                        charge=charge,
                        requested_by_user_id=user.user_id,
                        now=now,
                    )
            except asyncpg.UniqueViolationError:
                raise conflict(
                    "extension_open", "An extension request is already open for this Worker."
                ) from None
            await notify(
                conn,
                assignment["worker_user_id"],
                KIND_EXTENSION_REQUESTED,
                "Extend Work requested",
                f"+{body.extra_minutes} min on {shift['job_title']} · accept or decline",
                {"shift_id": shift_id, "assignment_id": assignment["id"], "live_work": True},
            )
        return await build_business_state(conn, shift_id, utc_now())


async def cancel_extension(
    user: AuthenticatedUser, shift_id: UUID, extension_id: UUID
) -> BusinessLiveBooking:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await _owned_booking(conn, user, shift_id)
            ext = await live_work_repository.lock_extension(conn, extension_id)
            if ext is None or ext["shift_id"] != shift_id:
                raise not_found("extension_not_found", "Extension not found.")
            if ext["status"] in ("requested", "awaiting_payment"):
                await live_work_repository.set_extension_status(
                    conn, extension_id, "cancelled", now
                )
                if ext["invoice_id"]:
                    await live_work_billing.void_invoice(conn, ext["invoice_id"])
            elif ext["status"] != "cancelled":
                raise live_work_core.state_error({"extension_status": ext["status"]})
        return await build_business_state(conn, shift_id, utc_now())


async def end_work(
    user: AuthenticatedUser, shift_id: UUID, assignment_id: UUID | None = None
) -> BusinessLiveBooking:
    """Business ends a Worker's work without the completion code = force-cancel (100% billed,
    the Worker gets their share). Agreed completion goes through the Worker and the code."""
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            current = await _seat_for_action(conn, shift_id, assignment_id, (ASG_CHECKED_IN,))
            assignment = await assignment_repository.lock_context(conn, current["id"])
            refund_ids = await live_work_core.business_force_stop(
                conn,
                shift=shift,
                pricing=pricing,
                assignment=assignment,
                actor_user_id=user.user_id,
                now=now,
            )
        await live_refund_service.process_refunds(refund_ids)
        return await build_business_state(conn, shift_id, utc_now())


async def reissue_arrival_code(
    user: AuthenticatedUser, shift_id: UUID, assignment_id: UUID | None = None
) -> BusinessLiveBooking:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await _owned_booking(conn, user, shift_id)
            current = await _seat_for_action(
                conn, shift_id, assignment_id, live_work_core.BEFORE_START_SEAT_STATUSES
            )
            code = await live_work_repository.lock_arrival_code(conn, current["id"])
            if code is None or code["verified_at"] is not None:
                raise live_work_core.state_error()
            if code["issued_count"] >= settings.live_arrival_max_reissues:
                raise conflict(
                    "arrival_code_reissue_limit",
                    "New codes can't be issued any more for this booking. Contact support.",
                )
            await live_work_repository.reissue_arrival_code(
                conn,
                current["id"],
                code=live_work_hooks.new_arrival_code(),
                expires_at=now + timedelta(seconds=settings.live_arrival_code_ttl_seconds),
            )
        return await build_business_state(conn, shift_id, utc_now())


async def reissue_completion_code(
    user: AuthenticatedUser, shift_id: UUID, assignment_id: UUID | None = None
) -> BusinessLiveBooking:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await _owned_booking(conn, user, shift_id)
            current = await _seat_for_action(conn, shift_id, assignment_id, (ASG_CHECKED_IN,))
            await completion_codes.reissue(conn, current["id"], shift_id)
        return await build_business_state(conn, shift_id, utc_now())
