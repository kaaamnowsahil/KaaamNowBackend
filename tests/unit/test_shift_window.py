"""Shift window rules: when a shift may start/end and how long it may be."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.exceptions.api_errors import ApiError
from app.services.shifts.domain.shift_rules import paid_minutes, resolve_window, validate_window

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _code(fn, **kwargs) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(ApiError) as exc:
        fn(**kwargs)
    return exc.value.code


def test_live_shift_without_a_start_starts_now():
    starts, ends = resolve_window(
        shift_type="live", starts_at=None, ends_at=None, duration_minutes=90, now=NOW
    )
    assert (starts, ends) == (NOW, NOW + timedelta(minutes=90))


def test_scheduled_shift_needs_a_start():
    assert (
        _code(
            resolve_window,
            shift_type="scheduled",
            starts_at=None,
            ends_at=None,
            duration_minutes=60,
            now=NOW,
        )
        == "starts_at_required"
    )


def test_end_needs_ends_at_or_duration():
    assert (
        _code(
            resolve_window,
            shift_type="scheduled",
            starts_at=NOW + 24 * HOUR,
            ends_at=None,
            duration_minutes=None,
            now=NOW,
        )
        == "ends_at_required"
    )


def test_explicit_end_is_kept():
    start, end = NOW + 24 * HOUR, NOW + 27 * HOUR
    assert resolve_window(
        shift_type="scheduled", starts_at=start, ends_at=end, duration_minutes=None, now=NOW
    ) == (start, end)


def _window(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "shift_type": "scheduled",
        "starts_at": NOW + 24 * HOUR,
        "ends_at": NOW + 28 * HOUR,
        "break_minutes": 30,
        "now": NOW,
    }
    return {**values, **overrides}


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"ends_at": NOW + 24 * HOUR}, "shift_window_invalid"),
        ({"ends_at": NOW + 24 * HOUR + timedelta(minutes=59)}, "shift_too_short"),
        ({"ends_at": NOW + 41 * HOUR}, "shift_too_long"),
        ({"break_minutes": 240}, "break_too_long"),
        ({"starts_at": NOW, "ends_at": NOW + 4 * HOUR}, "shift_in_past"),
        ({"min_lead_hours": 48}, "shift_too_soon"),
        (
            {"starts_at": NOW + timedelta(days=61), "ends_at": NOW + timedelta(days=61) + 4 * HOUR},
            "shift_too_far",
        ),
        (
            {"shift_type": "live", "starts_at": NOW + HOUR, "ends_at": NOW + 5 * HOUR},
            "live_start_now",
        ),
    ],
)
def test_invalid_windows_are_rejected(overrides, code):  # type: ignore[no-untyped-def]
    assert _code(validate_window, **_window(**overrides)) == code


def test_valid_scheduled_and_live_windows_pass():
    validate_window(**_window(min_lead_hours=12))
    validate_window(
        **_window(
            shift_type="live",
            starts_at=NOW + timedelta(minutes=10),
            ends_at=NOW + 4 * HOUR,
        )
    )


def test_paid_minutes_subtracts_the_break_and_never_goes_negative():
    assert paid_minutes(NOW, NOW + 4 * HOUR, 30) == 210
    assert paid_minutes(NOW, NOW + HOUR, 90) == 0
