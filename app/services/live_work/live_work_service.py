"""Business side of Live Work: Post Work, Live Work status, Extend Work, cancel, End Work."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_BUSINESS
from app.constants.notifications.notification_route_strings import KIND_EXTENSION_REQUESTED
from app.constants.shifts.shift_route_strings import (
    ASG_CHECKED_IN,
    CHECK_IN_CODE_LENGTH,
    SHIFT_AWAITING_PAYMENT,
    SHIFT_CANCELLED,
    SHIFT_DRAFT,
    SHIFT_IN_PROGRESS,
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
from app.services.cancellations import cancellation_service
from app.services.catalog import catalog_service
from app.services.live_work import (
    live_refund_service,
    live_work_billing,
    live_work_core,
    live_work_hooks,
)
from app.services.live_work.live_pricing import (
    booking_charge,
    extension_charge,
    extension_rate,
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
from app.services.users import terms_service
from app.utils.clock import utc_now
from app.utils.money import pay_for_minutes
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


async def quote(user: AuthenticatedUser, body: LiveWorkQuoteRequest) -> LivePriceBreakdown:
    error = validate_reserved_minutes(body.duration_minutes)
    if error:
        raise field_errors({"duration_minutes": error})
    async with get_pool().acquire() as conn:
        if body.category_slug:
            await catalog_service.resolve_category_id(conn, body.category_slug)
        rates = await active_rates(conn)
        promo = (
            await promo_service.quote_live(
                conn,
                body.promo_code,
                user_id=user.user_id,
                amount_minor=pay_for_minutes(body.hourly_rate_minor, body.duration_minutes),
            )
            if body.promo_code
            else None
        )
    return breakdown(
        currency=load_settings().default_currency,
        hourly_rate_minor=body.hourly_rate_minor,
        reserved_minutes=body.duration_minutes,
        rates=rates,
        charge=booking_charge(body.hourly_rate_minor, body.duration_minutes, rates, promo),
        promo_code=promo.code if promo else None,
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
    duration_error = validate_reserved_minutes(body.duration_minutes)
    if duration_error:
        errors["duration_minutes"] = duration_error
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
            "workers_required": 1,
            "hourly_rate_minor": body.hourly_rate_minor,
            "starts_at": now,
            "ends_at": now + timedelta(minutes=body.duration_minutes),
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
            amount_minor=pay_for_minutes(body.hourly_rate_minor, body.duration_minutes),
            now=now,
        )
        if body.promo_code
        else None
    )
    charge = booking_charge(body.hourly_rate_minor, body.duration_minutes, rates, promo)
    if body.expected_total_minor is not None and body.expected_total_minor != charge.total_minor:
        # Raised inside the posting transaction, so the shift and coupon hold roll back.
        raise conflict(
            "price_changed",
            "The price was updated. Please review the new total before posting.",
            {"total_minor": charge.total_minor, "settings_version": rates.version},
        )
    await live_work_repository.insert_booking_pricing(
        conn,
        shift_id=shift_id,
        business_profile_id=business["id"],
        currency=settings.default_currency,
        hourly_rate_minor=body.hourly_rate_minor,
        reserved_minutes=body.duration_minutes,
        rates=rates,
        charge=charge,
        idempotency_key=body.idempotency_key,
        promo_code_id=promo.id if promo else None,
        promo_code=promo.code if promo else None,
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
        assignment = await live_work_repository.get_current_assignment(conn, shift_id)
        plan = await live_work_core.business_cancel_plan(conn, shift, pricing, assignment)
    return cancel_preview_view(plan, pricing["currency"])


async def cancel(
    user: AuthenticatedUser, shift_id: UUID, body: LiveCancelRequest
) -> BusinessLiveBooking:
    now = utc_now()
    refund_ids: list[UUID | None] = []
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            if shift["status"] == SHIFT_CANCELLED:
                return await build_business_state(conn, shift_id, now)
            assignment = await live_work_repository.get_current_assignment(conn, shift_id)
            plan = await live_work_core.business_cancel_plan(conn, shift, pricing, assignment)
            if (
                body.expected_refund_minor is not None
                and body.expected_refund_minor != plan.refund_minor
            ):
                raise conflict(
                    "cancellation_terms_changed",
                    "The booking changed. Please review the cancellation again.",
                    {"refund_minor": plan.refund_minor},
                )
            await live_work_core.withdraw_offers(conn, shift_id)
            deposit = await live_work_repository.list_shift_invoices(conn, shift_id)
            for invoice in deposit:
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
            elif plan.stage == "before_start":
                await assignment_repository.cancel_assignment(
                    conn,
                    assignment["id"],
                    now=now,
                    actor_user_id=user.user_id,
                    reason=cancel_reason("business", body.reason),
                    late=plan.quote.fee_minor > 0,  # type: ignore[union-attr]
                )
                await cancellation_service.apply_seat(
                    conn,
                    shift=shift,
                    assignment_id=assignment["id"],
                    worker_profile_id=assignment["worker_profile_id"],
                    worker_user_id=assignment["worker_user_id"],
                    quote=plan.quote,  # type: ignore[arg-type]
                    actor_user_id=user.user_id,
                    now=now,
                )
                refund_ids += await live_work_core.queue_split_refund(
                    conn,
                    shift_id,
                    plan.refund_minor,
                    live_refund_service.REASON_BUSINESS_CANCELLED,
                    user.user_id,
                )
                await live_work_core.notify_cancelled(
                    conn,
                    assignment["worker_user_id"],
                    "Live Work cancelled by the Business",
                    shift["job_title"],
                    {"shift_id": shift_id, "assignment_id": assignment["id"], "live_work": True},
                )
            await shift_repository.cancel_shift(
                conn, shift_id, now=now, reason=cancel_reason("business", body.reason)
            )
            await shift_repository.record_history(
                conn, shift_id, shift["status"], SHIFT_CANCELLED, user.user_id, "business_cancelled"
            )
        await live_refund_service.process_refunds(refund_ids)
        return await build_business_state(conn, shift_id, utc_now())


async def _extension_quote(
    conn: asyncpg.Connection, pricing: asyncpg.Record, extra_minutes: int
) -> LiveExtensionQuote:
    applied = [
        e
        for e in await live_work_repository.list_extensions(conn, pricing["shift_id"])
        if e["status"] == "applied"
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
    user: AuthenticatedUser, shift_id: UUID, extra_minutes: int
) -> LiveExtensionQuote:
    error = validate_extension_minutes(extra_minutes)
    if error:
        raise field_errors({"extra_minutes": error})
    async with get_pool().acquire() as conn:
        pricing = await _owned_booking(conn, user, shift_id)
        return await _extension_quote(conn, pricing, extra_minutes)


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
            assignment = await live_work_repository.get_current_assignment(conn, shift_id)
            if (
                shift["status"] != SHIFT_IN_PROGRESS
                or assignment is None
                or assignment["status"] != ASG_CHECKED_IN
            ):
                raise live_work_core.state_error({"stage": shift["status"]})
            ext_quote = await _extension_quote(conn, pricing, body.extra_minutes)
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
                    "extension_open", "An extension request is already open for this booking."
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


async def end_work(user: AuthenticatedUser, shift_id: UUID) -> BusinessLiveBooking:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            pricing = await _owned_booking(conn, user, shift_id)
            shift = await shift_repository.lock_shift(conn, shift_id)
            current = await live_work_repository.get_current_assignment(conn, shift_id)
            if current is None:
                raise live_work_core.state_error({"stage": shift["status"]})
            assignment = await assignment_repository.lock_context(conn, current["id"])
            await live_work_core.complete_booking(
                conn,
                shift=shift,
                pricing=pricing,
                assignment=assignment,
                ended_by="business",
                actor_user_id=user.user_id,
                now=now,
            )
        return await build_business_state(conn, shift_id, utc_now())


async def reissue_arrival_code(user: AuthenticatedUser, shift_id: UUID) -> BusinessLiveBooking:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await _owned_booking(conn, user, shift_id)
            current = await live_work_repository.get_current_assignment(conn, shift_id)
            if current is None or current["status"] not in ("confirmed", "en_route"):
                raise live_work_core.state_error()
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
