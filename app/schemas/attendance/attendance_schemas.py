"""Figma "Ready to check in?", "Finish your shift?", "Review attendance"."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    check_in_code: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class CheckOutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    note: str = Field(default="", max_length=500)


class AttendanceApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_minutes: int | None = Field(
        default=None, ge=0, description="Defaults to the worker's recorded minutes."
    )
    note: str = Field(default="", max_length=500)
