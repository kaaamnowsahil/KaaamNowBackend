"""Phone OTP login + token request/response schemas (Figma "Welcome back" / "Verify your phone")."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.auth.auth_route_strings import (
    MSG_SIGNUP_DETAILS,
    MSG_SIGNUP_IDENTITY,
    TOKEN_TYPE_BEARER,
)
from app.schemas.profiles.profile_schemas import (
    EMAIL_PATTERN,
    WORKER_MAX_AGE,
    WORKER_MIN_AGE,
    OptionalLatitude,
    OptionalLongitude,
    _CoordinatesPair,
    _RequiredBusinessTypeChoice,
)
from app.schemas.users.user_schemas import MeResponse, SelfServiceRole

AuthIntent = Literal["sign_in", "sign_up", "password_reset"]


def _validate_password_strength(value: str) -> str:
    has_letter = any(char.isalpha() for char in value)
    has_number = any(char.isdigit() for char in value)
    if len(value) < 8 or not has_letter or not has_number:
        raise ValueError(
            "Password must be at least 8 characters and include a letter and a number."
        )
    return value


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    role: SelfServiceRole | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=20, max_length=4096)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class OtpSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20, examples=["+919876543210"])
    intent: AuthIntent | None = Field(
        default=None,
        description="sign_in: 404 if no account. sign_up: 409 if the number already has one.",
    )
    role: SelfServiceRole | None = Field(
        default=None,
        description="With intent: check the account for this role (worker or business, "
        "shown as Business / Work).",
    )


class OtpSendResponse(BaseModel):
    phone: str
    expires_in_seconds: int
    resend_after_seconds: int


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20, examples=["+919876543210"])
    code: str = Field(min_length=4, max_length=8, pattern=r"^\d+$", examples=["123456"])
    intent: Literal["sign_in"] | None = Field(
        default=None, description="sign_in: 404 instead of creating a new account."
    )
    role: SelfServiceRole | None = Field(
        default=None,
        description="Log in as this role: 404 role_not_registered if the account lacks it; "
        "otherwise it becomes the active role.",
    )


class FirebaseVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=20, max_length=4096)
    intent: Literal["sign_in"] | None = None
    role: SelfServiceRole | None = None


class PhoneCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20, examples=["+919876543210"])


class PhoneCheckResponse(BaseModel):
    phone: str
    registered: bool
    roles: list[str]


class SignupWorkerDetails(_CoordinatesPair):
    """App worker signup step 2 ("Tell us about you")."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    age: int = Field(ge=WORKER_MIN_AGE, le=WORKER_MAX_AGE)
    address_text: str = Field(min_length=3, max_length=500)
    locality: str | None = Field(default=None, max_length=160)
    latitude: float | None = OptionalLatitude
    longitude: float | None = OptionalLongitude
    work_type_slugs: list[str] = Field(min_length=1, max_length=20)


class SignupBusinessDetails(_CoordinatesPair, _RequiredBusinessTypeChoice):
    """App Business / Work signup step 2: the first (primary) Business / Work entity.

    ``business_type_slugs`` come from GET /api/v1/business-types (pick ``household`` for a
    home); the legacy single ``business_type_slug`` is still accepted. At least one is required.
    """

    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(min_length=1, max_length=160)
    contact_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    address_text: str = Field(min_length=3, max_length=500)
    locality: str | None = Field(default=None, max_length=160)
    latitude: float | None = OptionalLatitude
    longitude: float | None = OptionalLongitude
    category_slug: str | None = Field(default=None, max_length=64)


class SignupRequest(BaseModel):
    """One-call registration: verifies the phone OTP and creates the account + role profile."""

    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, min_length=8, max_length=20)
    code: str | None = Field(default=None, min_length=4, max_length=8, pattern=r"^\d+$")
    id_token: str | None = Field(default=None, min_length=20, max_length=4096)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)

    role: SelfServiceRole
    language_code: str | None = Field(default=None, min_length=2, max_length=8)
    worker: SignupWorkerDetails | None = None
    business: SignupBusinessDetails | None = None

    @model_validator(mode="after")
    def _identity_and_details(self) -> SignupRequest:
        uses_otp = self.phone is not None and self.code is not None
        if uses_otp == (self.id_token is not None):
            raise ValueError(MSG_SIGNUP_IDENTITY)
        details = self.worker if self.role == "worker" else self.business
        other = self.business if self.role == "worker" else self.worker
        if details is None or other is not None:
            raise ValueError(MSG_SIGNUP_DETAILS)
        return self


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = TOKEN_TYPE_BEARER
    expires_in: int = Field(description="Access token lifetime in seconds.")


class OtpVerifyResponse(BaseModel):
    tokens: TokenPair
    is_new_user: bool
    needs_role_selection: bool = Field(
        description="True until the user picks Business / Work or Worker (Figma role screen)."
    )
    me: MeResponse


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=200)
