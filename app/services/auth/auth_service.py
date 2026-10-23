"""Phone OTP login, refresh-token rotation and logout."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.application.application_constants import ROLE_BUSINESS, ROLE_WORKER
from app.constants.auth.auth_route_strings import (
    INTENT_PASSWORD_RESET,
    INTENT_SIGN_IN,
    INTENT_SIGN_UP,
    MSG_ACCOUNT_DISABLED,
    MSG_ACCOUNT_NOT_FOUND,
    MSG_OTP_ATTEMPTS_EXCEEDED,
    MSG_OTP_COOLDOWN,
    MSG_OTP_INVALID,
    MSG_OTP_RATE_LIMITED,
    MSG_OTP_SENT_BY_FIREBASE,
    MSG_PHONE_REGISTERED,
    MSG_REFRESH_INVALID,
    MSG_REFRESH_REUSED,
    MSG_ROLE_NOT_REGISTERED,
    MSG_ROLE_REGISTERED,
    OTP_PROVIDER_FIREBASE,
)
from app.constants.users.user_route_strings import MSG_LANGUAGE_UNKNOWN
from app.db.pool import get_pool
from app.exceptions.api_errors import (
    AuthenticationError,
    bad_request,
    conflict,
    forbidden,
    not_found,
    too_many_requests,
)
from app.repositories.auth import auth_repository
from app.repositories.profiles import profile_repository
from app.repositories.users import user_repository
from app.schemas.auth.auth_schemas import (
    OtpSendResponse,
    OtpVerifyResponse,
    PasswordLoginRequest,
    PasswordResetConfirmRequest,
    PhoneCheckResponse,
    SignupRequest,
    TokenPair,
)
from app.security.jwt_tokens import hash_refresh_token
from app.security.password_hash import burn_password_check, hash_password, verify_password
from app.services.auth.domain.token_issuer import issue_token_pair
from app.services.auth.sources.firebase_token_verifier import verify_firebase_phone_token
from app.services.auth.sources.otp_sender_factory import get_otp_sender
from app.services.auth.validation.auth_validation_pipeline import (
    hash_otp_code,
    normalize_phone,
    otp_code_matches,
)
from app.services.catalog import catalog_service
from app.services.users import user_service
from app.utils.address import resolve_locality
from app.utils.clock import utc_now
from app.utils.references import new_numeric_code


async def _registered_roles(conn: asyncpg.Connection, phone: str) -> list[str]:
    row = await user_repository.get_phone_status(conn, phone)
    return list(row["roles"]) if row is not None else []


def _require_role(roles: list[str], role: str) -> None:
    if role not in roles:
        raise not_found("role_not_registered", MSG_ROLE_NOT_REGISTERED.format(role=role))


def _reject_existing_role(roles: list[str], role: str | None) -> None:
    if not roles:
        return
    if role is not None and role in roles:
        raise conflict("role_registered", MSG_ROLE_REGISTERED.format(role=role))
    raise conflict("phone_registered", MSG_PHONE_REGISTERED)


async def _enforce_intent(phone: str, intent: str | None, role: str | None = None) -> None:
    """sign_in needs an account (with ``role`` if given); sign_up needs that role to be free."""
    if intent is None:
        return
    async with get_pool().acquire() as conn:
        roles = await _registered_roles(conn, phone)
    if intent == INTENT_SIGN_IN:
        if not roles:
            raise not_found("account_not_found", MSG_ACCOUNT_NOT_FOUND)
        if role is not None:
            _require_role(roles, role)
    elif intent == INTENT_SIGN_UP:
        _reject_existing_role(roles, role)


async def check_phone(phone: str) -> PhoneCheckResponse:
    phone = normalize_phone(phone)
    async with get_pool().acquire() as conn:
        row = await user_repository.get_phone_status(conn, phone)
    roles = list(row["roles"]) if row is not None else []
    return PhoneCheckResponse(phone=phone, registered=bool(roles), roles=roles)


async def send_otp(
    phone: str, request_ip: str | None, intent: str | None = None, role: str | None = None
) -> OtpSendResponse:
    settings = load_settings()
    phone = normalize_phone(phone)
    if settings.otp_provider == OTP_PROVIDER_FIREBASE:
        raise bad_request("otp_sent_by_firebase", MSG_OTP_SENT_BY_FIREBASE)
    purpose = intent or INTENT_SIGN_IN
    if purpose == INTENT_PASSWORD_RESET:
        async with get_pool().acquire() as conn:
            account_exists = await user_repository.get_auth_credentials(conn, phone) is not None
        if not account_exists:
            return OtpSendResponse(
                phone=phone,
                expires_in_seconds=settings.otp_ttl_seconds,
                resend_after_seconds=settings.otp_resend_cooldown_seconds,
            )
    else:
        await _enforce_intent(phone, intent, role)
    otp_sender = get_otp_sender()
    otp_sender.ensure_configured()
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
                purpose=purpose,
                code_hash=hash_otp_code(settings.jwt_secret_key, phone, code),
                expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
                request_ip=request_ip,
                now=now,
            )
    await otp_sender.send(phone, code)
    return OtpSendResponse(
        phone=phone,
        expires_in_seconds=settings.otp_ttl_seconds,
        resend_after_seconds=settings.otp_resend_cooldown_seconds,
    )


async def _consume_otp(phone: str, code: str, purpose: str = INTENT_SIGN_IN) -> None:
    settings = load_settings()
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            challenge = await auth_repository.lock_latest_open_otp_challenge(conn, phone, purpose)
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


async def verify_otp(
    phone: str, code: str, intent: str | None = None, role: str | None = None
) -> OtpVerifyResponse:
    phone = normalize_phone(phone)
    await _consume_otp(phone, code, intent or INTENT_SIGN_IN)
    await _enforce_intent(phone, intent, role)
    return await _sign_in(phone, role)


async def verify_firebase(
    id_token: str, intent: str | None = None, role: str | None = None
) -> OtpVerifyResponse:
    phone = normalize_phone(await verify_firebase_phone_token(id_token))
    await _enforce_intent(phone, intent, role)
    return await _sign_in(phone, role)


async def signup(body: SignupRequest) -> OtpVerifyResponse:
    """Verify Firebase phone proof and create the account + role + profile."""
    async with get_pool().acquire() as conn:
        if body.language_code and not await user_repository.language_is_active(
            conn, body.language_code
        ):
            raise bad_request("language_unknown", MSG_LANGUAGE_UNKNOWN)
        if body.worker is not None:
            category_ids = await catalog_service.resolve_category_ids(
                conn, body.worker.work_type_slugs
            )
        if body.business is not None:
            business_type_ids = await catalog_service.resolve_business_type_ids(
                conn, body.business.chosen_business_type_slugs() or []
            )
            category_id = (
                await catalog_service.resolve_category_id(conn, body.business.category_slug)
                if body.business.category_slug
                else None
            )

    if body.id_token is not None:
        phone = normalize_phone(await verify_firebase_phone_token(body.id_token))
    else:
        phone = normalize_phone(body.phone or "")
    await _enforce_intent(phone, INTENT_SIGN_UP, body.role)
    if body.id_token is None:
        await _consume_otp(phone, body.code or "", INTENT_SIGN_UP)

    async with get_pool().acquire() as conn:
        async with conn.transaction():
            user = await user_repository.upsert_user_by_phone(conn, phone)
            if user is None:
                user = await user_repository.upsert_user_by_phone(conn, phone)
            if not user["is_active"]:
                raise forbidden("account_disabled", MSG_ACCOUNT_DISABLED)
            await user_repository.lock_user(conn, user["id"])
            existing_roles = await user_repository.list_active_roles(conn, user["id"])
            _reject_existing_role(existing_roles, body.role)
            user_id = user["id"]
            await user_repository.set_password_if_missing(
                conn, user_id, hash_password(body.password)
            )
            # Adding a second role must not overwrite the name/email of the existing account.
            is_first_role = not existing_roles
            if body.worker is not None:
                worker = body.worker
                await user_repository.update_user_fields(
                    conn,
                    user_id,
                    full_name=worker.full_name.strip() if is_first_role else None,
                    email_set=worker.email is not None and is_first_role,
                    email=worker.email,
                    language_code=body.language_code,
                    theme_preference=None,
                )
                await user_repository.grant_role(conn, user_id, ROLE_WORKER)
                await profile_repository.ensure_worker_profile(conn, user_id)
                await profile_repository.update_worker_profile(
                    conn,
                    user_id,
                    address_text=worker.address_text.strip(),
                    locality=resolve_locality(worker.address_text, worker.locality),
                    latitude=worker.latitude,
                    longitude=worker.longitude,
                    age=worker.age,
                )
                profile = await profile_repository.get_worker_profile_by_user(conn, user_id)
                await profile_repository.replace_worker_categories(
                    conn, profile["id"], category_ids
                )
                role = ROLE_WORKER
            else:
                business = body.business
                assert business is not None
                await user_repository.update_user_fields(
                    conn,
                    user_id,
                    full_name=business.contact_name.strip() if is_first_role else None,
                    email_set=business.email is not None and is_first_role,
                    email=business.email,
                    language_code=body.language_code,
                    theme_preference=None,
                )
                await user_repository.grant_role(conn, user_id, ROLE_BUSINESS)
                await profile_repository.ensure_business_profile(conn, user_id)
                primary = await profile_repository.get_business_profile_by_user(conn, user_id)
                await profile_repository.update_business_profile(
                    conn,
                    primary["id"],
                    business_name=business.business_name.strip(),
                    category_id=category_id,
                    address_text=business.address_text.strip(),
                    locality=resolve_locality(business.address_text, business.locality),
                    latitude=business.latitude,
                    longitude=business.longitude,
                    contact_name=business.contact_name.strip(),
                    email=business.email,
                )
                await profile_repository.replace_business_types(
                    conn, primary["id"], business_type_ids
                )
                role = ROLE_BUSINESS
            await user_repository.set_active_role(conn, user_id, role)
            await user_repository.touch_last_login(conn, user_id, utc_now())
            tokens, _ = await issue_token_pair(conn, user_id=user_id, phone=phone)
            me = await user_service.build_me(conn, user_id)
    return OtpVerifyResponse(
        tokens=tokens, is_new_user=is_first_role, needs_role_selection=False, me=me
    )


async def _sign_in(phone: str, role: str | None = None) -> OtpVerifyResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            user = await user_repository.get_auth_credentials(conn, phone)
            if user is None:
                raise AuthenticationError(
                    "Invalid phone number or password.", code="credentials_invalid"
                )
            if not user["is_active"]:
                raise forbidden("account_disabled", MSG_ACCOUNT_DISABLED)
            if role is not None:
                _require_role(await user_repository.list_active_roles(conn, user["id"]), role)
                await user_repository.set_active_role(conn, user["id"], role)
            await user_repository.touch_last_login(conn, user["id"], utc_now())
            tokens, _ = await issue_token_pair(conn, user_id=user["id"], phone=phone)
            me = await user_service.build_me(conn, user["id"])
    return OtpVerifyResponse(
        tokens=tokens,
        is_new_user=False,
        needs_role_selection=not me.roles,
        me=me,
    )


async def password_login(body: PasswordLoginRequest) -> OtpVerifyResponse:
    phone = normalize_phone(body.phone)
    async with get_pool().acquire() as conn:
        user = await user_repository.get_auth_credentials(conn, phone)
    if user is None:
        burn_password_check(body.password)
        raise AuthenticationError("Invalid phone number or password.", code="credentials_invalid")
    if not user["password_hash"]:
        burn_password_check(body.password)
        raise AuthenticationError("Invalid phone number or password.", code="credentials_invalid")
    if not verify_password(body.password, user["password_hash"]):
        raise AuthenticationError("Invalid phone number or password.", code="credentials_invalid")
    if not user["is_active"]:
        raise AuthenticationError("Invalid phone number or password.", code="credentials_invalid")
    if body.role is not None:
        _require_role(list(user["roles"]), body.role)
    return await _sign_in(phone, body.role)


async def confirm_password_reset(body: PasswordResetConfirmRequest) -> None:
    phone = normalize_phone(await verify_firebase_phone_token(body.id_token))
    async with get_pool().acquire() as conn:
        updated = await user_repository.set_password_by_phone(
            conn, phone, hash_password(body.new_password)
        )
    if not updated:
        raise AuthenticationError("The code is invalid or expired.", code="otp_invalid")


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
