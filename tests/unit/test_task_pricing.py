"""Task (fixed-price) pricing rules, request validation and the completion-code view."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.attendance.attendance_schemas import CheckOutRequest
from app.schemas.live_work.live_work_schemas import LiveWorkQuoteRequest
from app.schemas.shifts.shift_schemas import ShiftEstimateRequest
from app.services.attendance.completion_codes import view
from app.services.live_work.live_pricing import (
    TAX_BASE_SUBTOTAL,
    LiveRates,
    booking_charge,
    live_terms,
    terms_from_pricing,
)
from app.services.shifts.domain.shift_rules import seat_pay_minor, shift_seat_pay

RATES = LiveRates(
    version=1,
    commission_pct=Decimal("4"),
    tax_pct=Decimal("2"),
    tax_label="Tax",
    tax_base=TAX_BASE_SUBTOTAL,
    extension_surcharge_pct=Decimal("30"),
)


def test_seat_pay_task_ignores_time():
    for minutes in (0, 60, 600):
        assert (
            seat_pay_minor(
                pricing_mode="task", hourly_rate_minor=0, task_price_minor=60_000, minutes=minutes
            )
            == 60_000
        )
    assert (
        seat_pay_minor(
            pricing_mode="hourly", hourly_rate_minor=12_000, task_price_minor=None, minutes=270
        )
        == 54_000
    )


def test_shift_seat_pay_reads_the_mode_from_the_row():
    starts = datetime(2026, 10, 1, 9, tzinfo=UTC)
    hourly = {
        "pricing_mode": "hourly",
        "hourly_rate_minor": 12_000,
        "task_price_minor": None,
        "starts_at": starts,
        "ends_at": starts + timedelta(hours=5),
        "break_minutes": 30,
    }
    assert shift_seat_pay(hourly) == 54_000
    assert shift_seat_pay(hourly, 10_000) == 45_000
    task = {**hourly, "pricing_mode": "task", "hourly_rate_minor": 0, "task_price_minor": 80_000}
    assert shift_seat_pay(task) == 80_000


def test_live_terms_task_reserves_the_window_and_bills_the_price():
    terms = live_terms(
        pricing_mode="task",
        hourly_rate_minor=50_000,
        duration_minutes=120,
        task_price_minor=80_000,
        task_window_minutes=720,
    )
    assert terms.is_task
    assert (terms.hourly_rate_minor, terms.reserved_minutes, terms.base_minor) == (0, 720, 80_000)
    hourly = live_terms(
        pricing_mode="hourly",
        hourly_rate_minor=50_000,
        duration_minutes=120,
        task_price_minor=None,
        task_window_minutes=720,
    )
    assert not hourly.is_task and hourly.base_minor == 100_000
    row = {
        "pricing_mode": "task",
        "hourly_rate_minor": 0,
        "reserved_minutes": 720,
        "task_price_minor": 80_000,
    }
    assert terms_from_pricing(row) == terms


def test_task_booking_charge_uses_the_fixed_base():
    # ₹800 task; 4% commission = ₹32; 2% tax on ₹832 = ₹16.64.
    charge = booking_charge(0, 720, RATES, task_price_minor=80_000)
    assert charge.base_amount_minor == 80_000
    assert charge.commission_minor == 3_200
    assert charge.tax_minor == 1_664
    assert charge.total_minor == 84_864


def test_shift_estimate_request_needs_the_matching_price():
    ShiftEstimateRequest(pricing_mode="task", task_price_minor=60_000, workers_required=1)
    ShiftEstimateRequest(hourly_rate_minor=12_000, workers_required=1, duration_minutes=240)
    with pytest.raises(ValidationError):
        ShiftEstimateRequest(pricing_mode="task", workers_required=1)
    with pytest.raises(ValidationError):
        ShiftEstimateRequest(pricing_mode="hourly", workers_required=1, duration_minutes=240)


def test_live_quote_request_needs_the_matching_price():
    LiveWorkQuoteRequest(pricing_mode="task", task_price_minor=80_000)
    LiveWorkQuoteRequest(hourly_rate_minor=50_000, duration_minutes=120)
    with pytest.raises(ValidationError):
        LiveWorkQuoteRequest(pricing_mode="task")
    with pytest.raises(ValidationError):
        LiveWorkQuoteRequest(pricing_mode="hourly", duration_minutes=120)


def test_check_out_requires_a_numeric_completion_code():
    assert CheckOutRequest(completion_code="123456").completion_code == "123456"
    for bad in ({}, {"completion_code": "12ab56"}, {"completion_code": "12"}):
        with pytest.raises(ValidationError):
            CheckOutRequest(**bad)


def _code_row(**overrides: object) -> dict:
    row: dict = {
        "code": "482913",
        "failed_attempts": 0,
        "locked_at": None,
        "verified_at": None,
        "issued_count": 1,
    }
    row.update(overrides)
    return row


def test_completion_code_view_hides_the_code_from_the_worker():
    business = view(_code_row(), for_business=True)  # type: ignore[arg-type]
    worker = view(_code_row(failed_attempts=2), for_business=False)  # type: ignore[arg-type]
    assert business is not None and business.code == "482913" and business.can_reissue
    assert worker is not None and worker.code is None and not worker.can_reissue
    assert worker.attempts_left == 3


def test_completion_code_view_states():
    now = datetime.now(UTC)
    assert view(None, for_business=True) is None
    assert view(_code_row(verified_at=now), for_business=True) is None  # type: ignore[arg-type]
    locked = view(_code_row(locked_at=now, failed_attempts=5), for_business=True)  # type: ignore[arg-type]
    assert locked is not None and locked.locked and locked.attempts_left == 0
    spent = view(_code_row(issued_count=10), for_business=True)  # type: ignore[arg-type]
    assert spent is not None and not spent.can_reissue
