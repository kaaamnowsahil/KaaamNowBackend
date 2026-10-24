"""Phone OTP login (Figma "Welcome back" / "Verify your phone") and tokens."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.constants.application.application_common import (
    SWAGGER_ROLE_ANY_USER,
    SWAGGER_ROLE_PUBLIC,
    swagger_summary,
)
from app.constants.auth.auth_route_strings import (
    AUTH_ROUTE_PREFIX,
    OPENAPI_TAG_AUTH,
    PATH_ADMIN_LOGIN,
    PATH_FIREBASE_VERIFY,
    PATH_LOGOUT,
    PATH_OTP_SEND,
    PATH_OTP_VERIFY,
    PATH_PASSWORD_LOGIN,
    PATH_PASSWORD_RESET_CONFIRM,
    PATH_PHONE_CHECK,
    PATH_SIGNUP,
    PATH_TOKEN_REFRESH,
)
from app.dependencies import CurrentUser
from app.schemas.auth.auth_schemas import (
    AdminLoginRequest,
    FirebaseVerifyRequest,
    OtpSendRequest,
    OtpSendResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    PasswordLoginRequest,
    PasswordResetConfirmRequest,
    PhoneCheckRequest,
    PhoneCheckResponse,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.services.auth import auth_service

router = APIRouter(prefix=AUTH_ROUTE_PREFIX, tags=[OPENAPI_TAG_AUTH])


@router.post(
    PATH_OTP_SEND,
    response_model=OtpSendResponse,
    summary=swagger_summary("Send backend OTP (dev/testing only)", SWAGGER_ROLE_PUBLIC),
)
async def send_otp(body: OtpSendRequest, request: Request) -> OtpSendResponse:
    client_ip = request.client.host if request.client else None
    return await auth_service.send_otp(body.phone, client_ip, body.intent, body.role)


@router.post(
    PATH_OTP_VERIFY,
    response_model=OtpVerifyResponse,
    summary=swagger_summary("Verify OTP and sign in", SWAGGER_ROLE_PUBLIC),
)
async def verify_otp(body: OtpVerifyRequest) -> OtpVerifyResponse:
    return await auth_service.verify_otp(body.phone, body.code, body.intent, body.role)


@router.post(
    PATH_FIREBASE_VERIFY,
    response_model=OtpVerifyResponse,
    summary=swagger_summary("Verify Firebase phone token and sign in", SWAGGER_ROLE_PUBLIC),
)
async def verify_firebase(body: FirebaseVerifyRequest) -> OtpVerifyResponse:
    return await auth_service.verify_firebase(body.id_token, body.intent, body.role)


@router.post(
    PATH_PHONE_CHECK,
    response_model=PhoneCheckResponse,
    summary=swagger_summary("Is this phone already registered?", SWAGGER_ROLE_PUBLIC),
)
async def check_phone(body: PhoneCheckRequest) -> PhoneCheckResponse:
    return await auth_service.check_phone(body.phone)


@router.post(
    PATH_SIGNUP,
    response_model=OtpVerifyResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary(
        "Register in one call (Firebase phone proof + role + profile)", SWAGGER_ROLE_PUBLIC
    ),
)
async def signup(body: SignupRequest) -> OtpVerifyResponse:
    return await auth_service.signup(body)


@router.post(
    PATH_PASSWORD_LOGIN,
    response_model=OtpVerifyResponse,
    summary=swagger_summary("Sign in with phone and password", SWAGGER_ROLE_PUBLIC),
)
async def password_login(body: PasswordLoginRequest) -> OtpVerifyResponse:
    return await auth_service.password_login(body)


@router.post(
    PATH_ADMIN_LOGIN,
    response_model=OtpVerifyResponse,
    summary=swagger_summary("Admin panel sign in with email and password", SWAGGER_ROLE_PUBLIC),
)
async def admin_login(body: AdminLoginRequest) -> OtpVerifyResponse:
    return await auth_service.admin_login(body)


@router.post(
    PATH_PASSWORD_RESET_CONFIRM,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Verify Firebase phone token and set password", SWAGGER_ROLE_PUBLIC),
)
async def confirm_password_reset(body: PasswordResetConfirmRequest) -> None:
    await auth_service.confirm_password_reset(body)


@router.post(
    PATH_TOKEN_REFRESH,
    response_model=TokenPair,
    summary=swagger_summary("Rotate refresh token", SWAGGER_ROLE_PUBLIC),
)
async def refresh(body: RefreshRequest) -> TokenPair:
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post(
    PATH_LOGOUT,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Log out (revoke refresh token)", SWAGGER_ROLE_ANY_USER),
)
async def logout(body: RefreshRequest, user: CurrentUser) -> None:
    await auth_service.logout(user.user_id, body.refresh_token)
