"""Phone OTP / Firebase phone login, refresh-token rotation and logout."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from app.config.settings import load_settings
from app.constants.auth.auth_route_strings import (
    MSG_ACCOUNT_DISABLED,
    MSG_OTP_ATTEMPTS_EXCEEDED,
    MSG_OTP_COOLDOWN,
    MSG_OTP_INVALID,
    MSG_OTP_RATE_LIMITED,
    MSG_OTP_SENT_BY_FIREBASE,
    MSG_REFRESH_INVALID,
    MSG_REFRESH_REUSED,
    OTP_PROVIDER_FIREBASE,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import (
    AuthenticationError,
    bad_request,
    forbidden,
    too_many_requests,
)
from app.repositories.auth import auth_repository
from app.repositories.users import user_repository
from app.schemas.auth.auth_schemas import OtpSendResponse, OtpVerifyResponse, TokenPair
from app.security.jwt_tokens import hash_refresh_token
from app.services.auth.domain.token_issuer import issue_token_pair
from app.services.auth.sources.firebase_token_verifier import verify_firebase_phone_token
from app.services.auth.sources.otp_sender_factory import get_otp_sender
from app.services.auth.validation.auth_validation_pipeline import (
    hash_otp_code,
    normalize_phone,
    otp_code_matches,
)
from app.services.users import user_service
from app.utils.clock import utc_now
from app.utils.references import new_numeric_code


async def send_otp(phone: str, request_ip: str | None) -> OtpSendResponse:
    settings = load_settings()
    if settings.otp_provider == OTP_PROVIDER_FIREBASE:
        raise bad_request("otp_sent_by_firebase", MSG_OTP_SENT_BY_FIREBASE)
    phone = normalize_phone(phone)
    now = utc_now()
    code = new_numeric_code(settings.otp_length)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            stats = await auth_repository.count_otp_sends_since(
                conn, phone, now - timedelta(hours=1)
            )
            if stats["sends"] >= settings.otp_max_sends_per_hour:
                raise too_many_requests("otp_rate_limited", MSG_OTP_RATE_LIMITED)
            cooldown = timedelta(seconds=settings.otp_resend_cooldown_seconds)
            last_sent_at = stats["last_sent_at"]
            if last_sent_at is not None and now - last_sent_at < cooldown:
                retry_after = int((cooldown - (now - last_sent_at)).total_seconds()) + 1
                raise too_many_requests(
                    "otp_cooldown", MSG_OTP_COOLDOWN, {"retry_after_seconds": retry_after}
                )
            await auth_repository.replace_otp_challenge(
                conn,
                phone=phone,
                code_hash=hash_otp_code(settings.jwt_secret_key, phone, code),
                expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
                request_ip=request_ip,
                now=now,
            )
    await get_otp_sender().send(phone, code)
    return OtpSendResponse(
        phone=phone,
        expires_in_seconds=settings.otp_ttl_seconds,
        resend_after_seconds=settings.otp_resend_cooldown_seconds,
    )


async def _consume_otp(phone: str, code: str) -> None:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            challenge = await auth_repository.lock_latest_open_otp_challenge(conn, phone)
            if challenge is None or challenge["expires_at"] <= now:
                raise bad_request("otp_invalid", MSG_OTP_INVALID)
            if challenge["attempts"] >= settings.otp_max_attempts:
                raise too_many_requests("otp_attempts_exceeded", MSG_OTP_ATTEMPTS_EXCEEDED)
            matched = otp_code_matches(settings.jwt_secret_key, phone, code, challenge["code_hash"])
            await auth_repository.record_otp_attempt(
                conn, challenge["id"], matched=matched, now=now
            )
    if not matched:
        raise bad_request("otp_invalid", MSG_OTP_INVALID)


async def verify_otp(phone: str, code: str) -> OtpVerifyResponse:
    phone = normalize_phone(phone)
    await _consume_otp(phone, code)
    return await _sign_in(phone)


async def verify_firebase(id_token: str) -> OtpVerifyResponse:
    phone = normalize_phone(await verify_firebase_phone_token(id_token))
    return await _sign_in(phone)


async def _sign_in(phone: str) -> OtpVerifyResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            user = await user_repository.upsert_user_by_phone(conn, phone)
            if user is None:  # concurrent first login — row committed by the other request
                user = await user_repository.upsert_user_by_phone(conn, phone)
            if not user["is_active"]:
                raise forbidden("account_disabled", MSG_ACCOUNT_DISABLED)
            await user_repository.touch_last_login(conn, user["id"], utc_now())
            tokens, _ = await issue_token_pair(conn, user_id=user["id"], phone=phone)
            me = await user_service.build_me(conn, user["id"])
    return OtpVerifyResponse(
        tokens=tokens,
        is_new_user=bool(user["created"]),
        needs_role_selection=not me.roles,
        me=me,
    )


async def refresh_tokens(refresh_token: str) -> TokenPair:
    """Rotate: old token is revoked and linked to its replacement. Reuse revokes the family."""
    now = utc_now()
    token_hash = hash_refresh_token(refresh_token)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            row = await auth_repository.lock_refresh_token(conn, token_hash)
            if row is None or row["expires_at"] <= now:
                raise AuthenticationError(MSG_REFRESH_INVALID, code="refresh_invalid")
            if row["revoked_at"] is not None:
                await auth_repository.revoke_refresh_token_family(conn, row["family_id"], now)
                reuse = row["replaced_by_id"] is not None
                code = "refresh_reused" if reuse else "refresh_invalid"
                message = MSG_REFRESH_REUSED if reuse else MSG_REFRESH_INVALID
                # Commit the family revocation before rejecting.
                return_error = AuthenticationError(message, code=code)
            else:
                return_error = None
                user = await user_repository.get_user(conn, row["user_id"])
                if user is None or not user["is_active"]:
                    raise forbidden("account_disabled", MSG_ACCOUNT_DISABLED)
                tokens, new_id = await issue_token_pair(
                    conn, user_id=user["id"], phone=user["phone"], family_id=row["family_id"]
                )
                await auth_repository.mark_refresh_token_rotated(
                    conn, row["id"], replaced_by_id=new_id, now=now
                )
    if return_error is not None:
        raise return_error
    return tokens


async def logout(user_id: UUID, refresh_token: str) -> None:
    async with get_pool().acquire() as conn:
        await auth_repository.revoke_refresh_token(
            conn, hash_refresh_token(refresh_token), user_id=user_id, now=utc_now()
        )
