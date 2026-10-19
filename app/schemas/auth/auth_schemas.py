"""Phone OTP login + token request/response schemas (Figma "Welcome back" / "Verify your phone")."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.constants.auth.auth_route_strings import TOKEN_TYPE_BEARER
from app.schemas.users.user_schemas import MeResponse


class OtpSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20, examples=["+919876543210"])


class OtpSendResponse(BaseModel):
    phone: str
    expires_in_seconds: int
    resend_after_seconds: int


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20, examples=["+919876543210"])
    code: str = Field(min_length=4, max_length=8, pattern=r"^\d+$", examples=["123456"])


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = TOKEN_TYPE_BEARER
    expires_in: int = Field(description="Access token lifetime in seconds.")


class OtpVerifyResponse(BaseModel):
    tokens: TokenPair
    is_new_user: bool
    needs_role_selection: bool = Field(
        description="True until the user picks Business or Worker (Figma role screen)."
    )
    me: MeResponse


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=200)
