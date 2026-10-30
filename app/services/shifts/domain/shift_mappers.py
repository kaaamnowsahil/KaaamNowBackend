"""asyncpg records → response schemas for the shifts domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg

from app.config.settings import load_settings
from app.schemas.attendance.attendance_schemas import CompletionCodeView
from app.schemas.shifts.application_schemas import (
    ApplicantItem,
    ApplicantShiftSummary,
    BusinessApplicantItem,
    WorkerSummary,
)
from app.schemas.shifts.assignment_schemas import AttendanceSummary, RosterEntry
from app.schemas.shifts.shift_schemas import (
    BusinessCard,
    LiveSearchState,
    ShiftCostEstimate,
    ShiftResponse,
    WorkerShiftCard,
    WorkerShiftDetail,
)
from app.services.shifts.domain.shift_rules import shift_seat_pay
from app.utils.money import platform_fee


def live_search_state(row: asyncpg.Record, now: datetime) -> LiveSearchState:
    expires = row["search_expires_at"]
    seconds_left = max(int((expires - now).total_seconds()), 0) if expires else 0
    return LiveSearchState(
        search_radius_km=row["search_radius_km"],
        max_search_radius_km=row["max_search_radius_km"],
        search_started_at=row["search_started_at"],
        search_expires_at=expires,
        seconds_left=seconds_left if row["status"] == "searching" else 0,
    )


def shift_response(
    row: asyncpg.Record, estimate: ShiftCostEstimate, now: datetime
) -> ShiftResponse:
    data = dict(row)
    data["estimate"] = estimate
    data["live_search"] = live_search_state(row, now) if row["shift_type"] == "live" else None
    return ShiftResponse.model_validate(data)


def business_card(row: asyncpg.Record) -> BusinessCard:
    return BusinessCard(
        id=row["business_profile_id"],
        business_name=row["business_name"],
        logo_url=row["logo_url"],
        rating_avg=float(row["business_rating_avg"]),
        rating_count=row["business_rating_count"],
        verification_status=row["business_verification"],
    )


def _card_fields(row: asyncpg.Record) -> dict:
    worker_pct = Decimal(row["worker_fee_percentage"] or 0)
    hourly_rate = row["hourly_rate_minor"]
    gross_pay = shift_seat_pay(row)
    distance = row["distance_km"]
    return {
        "id": row["id"],
        "shift_type": row["shift_type"],
        "status": row["status"],
        "job_title": row["job_title"],
        "category_slug": row["category_slug"],
        "category_name": row["category_name"],
        "business": business_card(row),
        "workplace_name": row["workplace_name"],
        "address_text": row["address_text"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "distance_km": round(distance, 2) if distance is not None else None,
        "starts_at": row["starts_at"],
        "ends_at": row["ends_at"],
        "break_minutes": row["break_minutes"],
        "pricing_mode": row["pricing_mode"],
        "hourly_rate_minor": hourly_rate,
        "worker_hourly_rate_minor": hourly_rate - platform_fee(hourly_rate, worker_pct),
        "task_price_minor": row["task_price_minor"],
        "currency": row["currency"],
        "estimated_pay_minor": gross_pay - platform_fee(gross_pay, worker_pct),
        "spots_left": max(row["workers_required"] - row["booked_count"], 0),
        "my_application_id": row["my_application_id"],
        "my_application_status": row["my_application_status"],
        "my_assignment_id": row["my_assignment_id"],
        "my_assignment_status": row["my_assignment_status"],
    }


def worker_shift_card(row: asyncpg.Record) -> WorkerShiftCard:
    return WorkerShiftCard(**_card_fields(row))


def worker_shift_detail(row: asyncpg.Record) -> WorkerShiftDetail:
    return WorkerShiftDetail(
        **_card_fields(row),
        responsibilities=row["responsibilities"],
        requirements=row["requirements"],
        arrival_instructions=row["arrival_instructions"],
        site_contact_name=row["site_contact_name"],
        cancellation_cutoff_hours=row["cancellation_cutoff_hours"],
    )


def worker_summary(row: asyncpg.Record) -> WorkerSummary:
    rating = row["rating_avg"]
    return WorkerSummary(
        id=row["worker_id"],
        user_id=row["worker_user_id"],
        full_name=row["full_name"],
        photo_url=row["photo_url"],
        rating_avg=float(rating) if isinstance(rating, Decimal) else rating,
        rating_count=row["rating_count"],
        completed_shift_count=row["completed_shift_count"],
        verification_status=row["verification_status"],
    )


def attendance_summary(row: asyncpg.Record) -> AttendanceSummary | None:
    if row["attendance_id"] is None:
        return None
    return AttendanceSummary(
        checked_in_at=row["checked_in_at"],
        check_in_distance_m=row["check_in_distance_m"],
        checked_out_at=row["checked_out_at"],
        worker_note=row["worker_note"],
        recorded_minutes=row["recorded_minutes"],
        approved_minutes=row["approved_minutes"],
        business_note=row["business_note"],
        approved_at=row["approved_at"],
    )


def roster_entry(row: asyncpg.Record) -> RosterEntry:
    return RosterEntry(
        assignment_id=row["assignment_id"],
        status=row["status"],
        source=row["source"],
        confirmed_at=row["confirmed_at"],
        travel_started_at=row["travel_started_at"],
        late_cancellation=row["late_cancellation"],
        worker=worker_summary(row),
        attendance=attendance_summary(row),
        check_in_code=row["check_in_code"],
        extended_minutes=row["extended_minutes"],
        ended_reason=row["ended_reason"],
        completion_code=_roster_completion_code(row),
    )


def _roster_completion_code(row: asyncpg.Record) -> CompletionCodeView | None:
    if row["status"] != "checked_in" or row["completion_code"] is None:
        return None
    settings = load_settings()
    return CompletionCodeView(
        code=row["completion_code"],
        attempts_left=max(
            settings.completion_code_max_attempts - row["completion_failed_attempts"], 0
        ),
        locked=row["completion_locked_at"] is not None,
        can_reissue=row["completion_issued_count"] < settings.completion_code_max_reissues,
    )


def applicant_item(row: asyncpg.Record) -> ApplicantItem:
    return ApplicantItem(
        application_id=row["application_id"],
        status=row["status"],
        applied_at=row["applied_at"],
        decided_at=row["decided_at"],
        responded_at=row["responded_at"],
        confirm_by=row["confirm_by"],
        distance_km=round(row["distance_km"], 2) if row["distance_km"] is not None else None,
        cover_note=row["cover_note"],
        worker=worker_summary(row),
        assignment_id=row["assignment_id"],
    )


def business_applicant_item(row: asyncpg.Record) -> BusinessApplicantItem:
    return BusinessApplicantItem(
        **applicant_item(row).model_dump(),
        shift=ApplicantShiftSummary(
            id=row["shift_id"],
            shift_type=row["shift_type"],
            status=row["shift_status"],
            job_title=row["job_title"],
            workplace_name=row["workplace_name"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            workers_required=row["workers_required"],
            pricing_mode=row["pricing_mode"],
            hourly_rate_minor=row["hourly_rate_minor"],
            task_price_minor=row["task_price_minor"],
            currency=row["currency"],
        ),
    )
