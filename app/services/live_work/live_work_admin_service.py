"""Admin Live Work monitor: bookings, cancellations, refunds. Never returns arrival codes or
precise Worker location."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.pool import get_pool
from app.exceptions.api_errors import not_found
from app.pagination import clamp_page_limit
from app.repositories.live_work import live_work_repository
from app.schemas.live_work.live_work_schemas import (
    AdminLiveBookingDetail,
    AdminLiveBookingItem,
    AdminLiveBookingPage,
    AdminLiveCancellation,
    AdminLiveRefund,
    AdminLiveRefundPage,
)
from app.services.live_work import live_refund_service, live_work_core
from app.services.live_work.live_work_views import (
    booking_breakdown,
    extension_view,
    invoice_summary,
)


def _booking_item(row: asyncpg.Record) -> AdminLiveBookingItem:
    return AdminLiveBookingItem(
        booking_id=row["shift_id"],
        shift_status=row["shift_status"],
        job_title=row["job_title"],
        category_name=row["category_name"],
        business_name=row["business_name"],
        worker_name=row["worker_name"],
        assignment_status=row["assignment_status"],
        reserved_minutes=row["reserved_minutes"],
        total_minor=row["total_minor"],
        commission_minor=row["commission_minor"],
        tax_minor=row["tax_minor"],
        refunded_minor=row["refunded_minor"],
        open_refunds=row["open_refunds"],
        currency=row["currency"],
        created_at=row["created_at"],
    )


def _refund(row: asyncpg.Record) -> AdminLiveRefund:
    return AdminLiveRefund(
        id=row["id"],
        booking_id=row["shift_id"],
        job_title=row["job_title"],
        amount_minor=row["amount_minor"],
        currency=row["currency"],
        reason=row["reason"],
        status=row["status"],
        provider=row["provider"],
        provider_refund_id=row["provider_refund_id"],
        failure_reason=row["failure_reason"],
        attempts=row["attempts"],
        created_at=row["created_at"],
        processed_at=row["processed_at"],
    )


def _cancellation(row: asyncpg.Record) -> AdminLiveCancellation:
    return AdminLiveCancellation(
        party=row["party"],
        event=row["event"],
        fee_minor=row["fee_minor"],
        worker_compensation_minor=row["worker_compensation_minor"],
        business_refund_minor=row["business_refund_minor"],
        business_retained_minor=row["business_retained_minor"],
        strike_weight=float(row["strike_weight"]),
        created_at=row["created_at"],
    )


async def list_bookings(status: str | None, limit: int | None, offset: int) -> AdminLiveBookingPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        rows = await live_work_repository.admin_list_bookings(conn, status, page_limit, offset)
        total = await live_work_repository.admin_count_bookings(conn, status)
    return AdminLiveBookingPage(
        items=[_booking_item(r) for r in rows], total=total, limit=page_limit, offset=offset
    )


async def booking_detail(shift_id: UUID) -> AdminLiveBookingDetail:
    async with get_pool().acquire() as conn:
        row = await live_work_repository.admin_get_booking(conn, shift_id)
        if row is None:
            raise live_work_core.not_found_error()
        extensions = await live_work_repository.list_extensions(conn, shift_id)
        invoices = await live_work_repository.list_shift_invoices(conn, shift_id)
        refunds = await live_work_repository.admin_list_shift_refunds(conn, shift_id)
        cancellations = await live_work_repository.admin_list_cancellations(conn, shift_id)
    return AdminLiveBookingDetail(
        booking=_booking_item(row),
        pricing=booking_breakdown(row),
        work_address=row["address_text"] or "",
        assignment_status=row["assignment_status"],
        extensions=[extension_view(e) for e in extensions],
        invoices=[invoice_summary(i) for i in invoices],
        refunds=[_refund(r) for r in refunds],
        cancellations=[_cancellation(c) for c in cancellations],
    )


async def list_refunds(status: str | None, limit: int | None, offset: int) -> AdminLiveRefundPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        rows = await live_work_repository.admin_list_refunds(conn, status, page_limit, offset)
        total = await live_work_repository.admin_count_refunds(conn, status)
    return AdminLiveRefundPage(
        items=[_refund(r) for r in rows], total=total, limit=page_limit, offset=offset
    )


async def retry_refund(refund_id: UUID) -> AdminLiveRefund:
    await live_refund_service.admin_retry(refund_id)
    async with get_pool().acquire() as conn:
        row = await live_work_repository.admin_get_refund(conn, refund_id)
    if row is None:
        raise not_found("refund_not_found", "Refund not found.")
    return _refund(row)
