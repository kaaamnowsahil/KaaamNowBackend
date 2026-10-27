"""Wire shapes shared across domains."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["shift_not_found"])
    message: str
    details: object | None = None
    request_id: str | None = Field(default=None, description="Quote this when contacting support.")


class OkResponse(BaseModel):
    ok: bool = True


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90, examples=[12.9352])
    longitude: float = Field(ge=-180, le=180, examples=[77.6245])


class MoneyAmount(BaseModel):
    amount_minor: int = Field(description="Integer minor units (paise).", examples=[189000])
    currency: str = Field(default="INR", examples=["INR"])
