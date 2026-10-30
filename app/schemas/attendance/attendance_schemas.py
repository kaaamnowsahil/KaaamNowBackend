"""Figma "Ready to check in?", "Finish your shift?", "Review attendance"."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    check_in_code: str = Field(
        min_length=4,
        max_length=8,
        pattern=r"^[A-Za-z0-9]+$",
        description="4-character code shown in the business app for this booking.",
    )


def completion_code_field():  # type: ignore[no-untyped-def]
    return Field(
        min_length=4,
        max_length=8,
        pattern=r"^\d+$",
        description="Completion code shown in the Business app for this booking.",
    )


class CompletionCodeView(BaseModel):
    """``code`` is shown to the Business only; the Worker sees attempts left / locked."""

    code: str | None = None
    attempts_left: int
    locked: bool
    can_reissue: bool = False


class CheckOutRequest(BaseModel):
    """Finish work: the Worker enters the Business's completion code (any time while checked
    in). Hourly bookings ended before the booked end are paid for the time worked."""

    model_config = ConfigDict(extra="forbid")

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    note: str = Field(default="", max_length=500)
    completion_code: str = completion_code_field()


class AttendanceApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_minutes: int | None = Field(
        default=None, ge=0, description="Defaults to the worker's recorded minutes."
    )
    note: str = Field(default="", max_length=500)


class EarlyEndRequest(BaseModel):
    """The side ending early enters the PIN shown in the other side's app."""

    model_config = ConfigDict(extra="forbid")

    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    note: str = Field(default="", max_length=500)


class StopWorkRequest(BaseModel):
    """Business ends without the worker's PIN. ``business_stopped``: business pays the full
    booking, worker gets 80%. ``worker_left``: actual hours (nothing for a task-priced job),
    worker walk-off fee."""

    model_config = ConfigDict(extra="forbid")

    reason: Literal["business_stopped", "worker_left"]
    note: str = Field(default="", max_length=500)


class ExtensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extra_minutes: int = Field(ge=15, le=240, description="Paid at the overtime rate (130%).")


class ExtensionView(BaseModel):
    id: UUID
    extra_minutes: int
    status: Literal["requested", "accepted", "declined", "cancelled", "expired"]
    requested_at: datetime
    responded_at: datetime | None = None
