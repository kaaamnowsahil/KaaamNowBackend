"""Phone OTP login (Figma "Welcome back" / "Verify your phone") and token lifecycle."""

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
    PATH_LOGOUT,
    PATH_OTP_SEND,
    PATH_OTP_VERIFY,
    PATH_TOKEN_REFRESH,
)
from app.dependencies import CurrentUser
from app.schemas.auth.auth_schemas import (
    OtpSendRequest,
    OtpSendResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    RefreshRequest,
    TokenPair,
)
from app.services.auth import auth_service

router = APIRouter(prefix=AUTH_ROUTE_PREFIX, tags=[OPENAPI_TAG_AUTH])


@router.post(
    PATH_OTP_SEND,
    response_model=OtpSendResponse,
    summary=swagger_summary("Send login OTP", SWAGGER_ROLE_PUBLIC),
)
async def send_otp(body: OtpSendRequest, request: Request) -> OtpSendResponse:
    client_ip = request.client.host if request.client else None
    return await auth_service.send_otp(body.phone, client_ip)


@router.post(
    PATH_OTP_VERIFY,
    response_model=OtpVerifyResponse,
    summary=swagger_summary("Verify OTP and sign in", SWAGGER_ROLE_PUBLIC),
)
async def verify_otp(body: OtpVerifyRequest) -> OtpVerifyResponse:
    return await auth_service.verify_otp(body.phone, body.code)


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
