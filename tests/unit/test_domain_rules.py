from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.exceptions.api_errors import ApiError
from app.security.permissions import (
    ACTION_READ,
    ACTION_WRITE,
    RESOURCE_EARNINGS,
    RESOURCE_SHIFTS,
    roles_allow,
)
from app.services.auth.auth_service import _reject_existing_role
from app.services.auth.validation.auth_validation_pipeline import (
    hash_otp_code,
    normalize_phone,
    otp_code_matches,
)
from app.services.billing.validation.webhook_signature import sign_payload, signature_matches
from app.services.shifts.domain.shift_rules import is_late_cancellation, paid_minutes
from app.utils.geo import haversine_km
from app.utils.money import pay_for_minutes, platform_fee


def test_pay_for_minutes_matches_figma_copy() -> None:
    assert pay_for_minutes(15000, 240) == 60000
    assert pay_for_minutes(10001, 1) == 167  # 166.68 rounds half-up


def test_platform_fee_rounds_half_up() -> None:
    assert platform_fee(180000, Decimal("5")) == 9000
    assert platform_fee(10, Decimal("5")) == 1  # 0.5 -> 1


def test_haversine_known_distance() -> None:
    # Connaught Place -> India Gate is about 2.4 km.
    assert 2.0 < haversine_km(28.6315, 77.2167, 28.6129, 77.2295) < 2.8
    assert haversine_km(19.0, 72.8, 19.0, 72.8) == 0


def test_otp_hash_is_bound_to_phone() -> None:
    digest = hash_otp_code("secret", "+919876543210", "123456")
    assert otp_code_matches("secret", "+919876543210", "123456", digest)
    assert not otp_code_matches("secret", "+919876543211", "123456", digest)
    assert not otp_code_matches("other", "+919876543210", "123456", digest)


def test_normalize_phone() -> None:
    assert normalize_phone("+91 98765-43210") == "+919876543210"
    with pytest.raises(ApiError):
        normalize_phone("abc")


def test_existing_phone_cannot_register_a_second_role() -> None:
    with pytest.raises(ApiError) as error:
        _reject_existing_role(["worker"], "business")

    assert error.value.code == "phone_registered"


def test_permissions_matrix() -> None:
    assert roles_allow(("business",), RESOURCE_SHIFTS, ACTION_WRITE)
    assert not roles_allow(("business",), RESOURCE_EARNINGS, ACTION_READ)
    assert roles_allow(("worker",), RESOURCE_EARNINGS, ACTION_WRITE)
    assert not roles_allow((), RESOURCE_SHIFTS, ACTION_READ)


def test_shift_rules() -> None:
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    assert paid_minutes(start, start + timedelta(hours=4), 30) == 210
    assert is_late_cancellation(start, 12, start - timedelta(hours=11))
    assert not is_late_cancellation(start, 12, start - timedelta(hours=13))


def test_webhook_signature() -> None:
    body = b'{"event":"payment.succeeded"}'
    signature = sign_payload("whsec", body)
    assert signature_matches("whsec", body, signature)
    assert signature_matches("whsec", body, signature.upper())
    assert not signature_matches("whsec", body + b" ", signature)
    assert not signature_matches("", body, signature)
    assert not signature_matches("whsec", body, None)
