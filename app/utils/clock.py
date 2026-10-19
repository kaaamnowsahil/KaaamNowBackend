"""Single source of "now" so services and tests agree on UTC-aware timestamps."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def minutes_between(start: datetime, end: datetime) -> int:
    """Whole minutes from ``start`` to ``end`` (never negative)."""
    return max(int((end - start).total_seconds() // 60), 0)
