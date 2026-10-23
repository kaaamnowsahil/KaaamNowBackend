"""App onboarding: one-call signup, sign-in intent, profile fields, content and payout edits."""

from __future__ import annotations

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from tests.integration.conftest import TEST_OTP, next_phone

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"

WORKER_DETAILS = {
    "full_name": "Ravi Kumar",
    "email": "ravi@example.com",
    "age": 24,
    "address_text": "12 MG Road, Indiranagar, Bengaluru 560038",
    "latitude": 12.9784,
    "longitude": 77.6408,
    "work_type_slugs": ["cook", "hotel-staff"],
}

BUSINESS_DETAILS = {
    "business_name": "Cafe Aroma",
    "contact_name": "Priya Shah",
    "email": "priya@cafearoma.in",
    "address_text": "Shop 4, Koramangala, Bengaluru",
    "business_type_slug": "hospitality",
}


async def _send(client: httpx.AsyncClient, phone: str, intent: str | None = None) -> httpx.Response:
    body = {"phone": phone} | ({"intent": intent} if intent else {})
    return await client.post(f"{API}/auth/otp/send", json=body)


async def _signup(
    client: httpx.AsyncClient, phone: str, role: str, details: dict
) -> httpx.Response:
    return await client.post(
        f"{API}/auth/signup",
        json={
            "phone": phone,
            "code": TEST_OTP,
            "password": "TestPassword123",
            "role": role,
            role: details,
        },
    )


async def test_worker_signup_and_sign_in_intent(app_client: httpx.AsyncClient) -> None:
    phone = next_phone()
    check = await app_client.post(f"{API}/auth/phone/check", json={"phone": phone})
    assert check.json() == {"phone": phone, "registered": False, "roles": []}

    missing = await _send(app_client, phone, "sign_in")
    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "account_not_found"

    assert (await _send(app_client, phone, "sign_up")).status_code == 200
    bad = await _signup(app_client, phone, "worker", WORKER_DETAILS | {"work_type_slugs": ["x"]})
    assert bad.status_code == 400, bad.text

    created = await _signup(app_client, phone, "worker", WORKER_DETAILS)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_new_user"] is True and body["needs_role_selection"] is False
    assert body["me"]["roles"] == ["worker"] and body["me"]["active_role"] == "worker"
    assert body["me"]["full_name"] == "Ravi Kumar"
    headers = {"Authorization": f"Bearer {body['tokens']['access_token']}"}

    body = (await app_client.get(f"{API}/me/profile", headers=headers)).json()
    assert body["profile_type"] == "worker" and body["business"] is None
    profile = body["worker"]
    assert profile["age"] == 24 and profile["email"] == "ravi@example.com"
    assert profile["locality"] == "Indiranagar"
    assert profile["category_slugs"] == ["cook", "hotel-staff"]

    patched = await app_client.patch(
        f"{API}/me/profile",
        json={"full_name": "Ravi K", "age": 25, "address_text": "Sector 5, HSR Layout, Bengaluru"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    worker = patched.json()["worker"]
    assert worker["full_name"] == "Ravi K" and patched.json()["account"]["full_name"] == "Ravi K"
    assert worker["age"] == 25 and worker["locality"] == "HSR Layout"
    too_young = await app_client.patch(f"{API}/me/profile", json={"age": 15}, headers=headers)
    assert too_young.status_code == 422

    taken = await _send(app_client, phone, "sign_up")
    assert taken.status_code == 409 and taken.json()["code"] == "phone_registered"
    check = await app_client.post(f"{API}/auth/phone/check", json={"phone": phone})
    assert check.json()["registered"] is True


async def test_password_login_and_otp_password_reset(app_client: httpx.AsyncClient) -> None:
    phone = next_phone()
    assert (await _send(app_client, phone, "sign_up")).status_code == 200
    created = await app_client.post(
        f"{API}/auth/signup",
        json={
            "phone": phone,
            "code": TEST_OTP,
            "role": "worker",
            "password": "SecurePass123",
            "worker": WORKER_DETAILS,
        },
    )
    assert created.status_code == 201, created.text

    wrong = await app_client.post(
        f"{API}/auth/password/login", json={"phone": phone, "password": "WrongPass123"}
    )
    assert wrong.status_code == 401
    logged_in = await app_client.post(
        f"{API}/auth/password/login", json={"phone": phone, "password": "SecurePass123"}
    )
    assert logged_in.status_code == 200, logged_in.text

    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE otp_challenges SET created_at = now() - interval '1 hour' WHERE phone = $1",
            phone,
        )
    reset_request = await app_client.post(
        f"{API}/auth/otp/send",
        json={"phone": phone, "intent": "password_reset"},
    )
    assert reset_request.status_code == 200, reset_request.text
    reset = await app_client.post(
        f"{API}/auth/password/reset/confirm",
        json={"phone": phone, "code": TEST_OTP, "new_password": "NewSecure123"},
    )
    assert reset.status_code == 204, reset.text
    reused = await app_client.post(
        f"{API}/auth/password/reset/confirm",
        json={"phone": phone, "code": TEST_OTP, "new_password": "AnotherPass123"},
    )
    assert reused.status_code == 400
    old_password = await app_client.post(
        f"{API}/auth/password/login", json={"phone": phone, "password": "SecurePass123"}
    )
    assert old_password.status_code == 401
    assert (
        await app_client.post(
            f"{API}/auth/password/login", json={"phone": phone, "password": "NewSecure123"}
        )
    ).status_code == 200

    anonymous_reset = await app_client.post(
        f"{API}/auth/otp/send",
        json={"phone": next_phone(), "intent": "password_reset"},
    )
    assert anonymous_reset.status_code == 200


async def test_business_signup_logo_and_catalog(app_client: httpx.AsyncClient) -> None:
    types = (await app_client.get(f"{API}/business-types")).json()
    slugs = [t["slug"] for t in types]
    assert slugs[:3] == ["household", "personal-residence", "apartment"]
    assert slugs[-1] == "other" and len(slugs) == 43
    names = {t["slug"]: t["name"] for t in types}
    assert names["real-estate"] == "Real Estate / Property Management"
    assert names["laundry"] == "Laundry / Dry Cleaning"
    work_types = (await app_client.get(f"{API}/work-categories")).json()
    assert len(work_types) == 75 and work_types[-1]["slug"] == "other"
    assert {"mason", "barista", "waste-collection"} <= {t["slug"] for t in work_types}

    phone = next_phone()
    assert (await _send(app_client, phone, "sign_up")).status_code == 200
    wrong_block = await app_client.post(
        f"{API}/auth/signup",
        json={"phone": phone, "code": TEST_OTP, "role": "business", "worker": WORKER_DETAILS},
    )
    assert wrong_block.status_code == 422

    created = await _signup(app_client, phone, "business", BUSINESS_DETAILS)
    assert created.status_code == 201, created.text
    headers = {"Authorization": f"Bearer {created.json()['tokens']['access_token']}"}
    body = (await app_client.get(f"{API}/me/profile", headers=headers)).json()
    assert body["profile_type"] == "business" and body["worker"] is None
    profile = body["business"]
    assert profile["business_name"] == "Cafe Aroma"
    assert profile["contact_name"] == "Priya Shah" and profile["owner_name"] == "Priya Shah"
    assert profile["business_type_slug"] == "hospitality"
    assert profile["locality"] == "Koramangala"

    patched = await app_client.patch(
        f"{API}/me/profile", json={"business_type_slug": "retail"}, headers=headers
    )
    assert patched.json()["business"]["business_type_slug"] == "retail"

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    logo = await app_client.post(
        f"{API}/me/profile/image",
        files={"file": ("logo.png", png, "image/png")},
        headers=headers,
    )
    assert logo.status_code == 200, logo.text
    assert logo.json()["business"]["logo_url"]
    assert logo.json()["account"]["photo_url"] is None

    again = await _signup(app_client, phone, "business", BUSINESS_DETAILS)
    assert again.status_code in (400, 409)


async def test_content_sections_and_audience(app_client: httpx.AsyncClient) -> None:
    terms = (await app_client.get(f"{API}/content/terms")).json()
    assert terms["audience"] == "worker"
    assert terms["sections"][0]["title"] == "1. Using KaaamNow"
    assert terms["sections"][0]["id"] == "1-using-kaaamnow"

    faqs = (await app_client.get(f"{API}/content/faqs", params={"audience": "business"})).json()
    assert faqs["items"][0]["slug"] == "how-do-i-pay-for-a-shift"
    assert len(faqs["support_emails"]) == 2


async def test_payout_account_edit(app_client: httpx.AsyncClient) -> None:
    phone = next_phone()
    await _send(app_client, phone, "sign_up")
    created = await _signup(app_client, phone, "worker", WORKER_DETAILS)
    headers = {"Authorization": f"Bearer {created.json()['tokens']['access_token']}"}

    account = await app_client.post(
        f"{API}/worker/payout-accounts",
        json={"account_type": "upi", "upi_id": "ravi@okaxis"},
        headers=headers,
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]
    assert account.json()["is_verified"] is False

    edited = await app_client.patch(
        f"{API}/worker/payout-accounts/{account_id}",
        json={"upi_id": "ravi@ybl", "account_holder_name": "Ravi Kumar"},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["upi_id"] == "ravi@ybl"
    wrong_field = await app_client.patch(
        f"{API}/worker/payout-accounts/{account_id}",
        json={"bank_ifsc": "HDFC0001234"},
        headers=headers,
    )
    assert wrong_field.status_code == 400


async def _verify(
    client: httpx.AsyncClient, phone: str, role: str | None = None, intent: str | None = None
) -> httpx.Response:
    body = {"phone": phone, "code": TEST_OTP}
    body |= {"role": role} if role else {}
    body |= {"intent": intent} if intent else {}
    return await client.post(f"{API}/auth/otp/verify", json=body)


async def test_one_phone_cannot_have_both_roles(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    phone = next_phone()
    await _send(app_client, phone, "sign_up")
    worker = await _signup(app_client, phone, "worker", WORKER_DETAILS)
    assert worker.status_code == 201, worker.text
    headers = {"Authorization": f"Bearer {worker.json()['tokens']['access_token']}"}

    second_role = await app_client.post(
        f"{API}/auth/signup",
        json={
            "phone": phone,
            "code": TEST_OTP,
            "role": "business",
            "password": "SecurePass123",
            "business": BUSINESS_DETAILS,
        },
    )
    assert second_role.status_code == 409
    assert second_role.json()["code"] == "phone_registered"

    profile = await app_client.get(f"{API}/me/profile", headers=headers)
    assert profile.json()["account"]["roles"] == ["worker"]
    assert profile.status_code == 200 and profile.json()["profile_type"] == "worker"


async def test_role_login_does_not_create_accounts(app_client: httpx.AsyncClient) -> None:
    phone = next_phone()
    sent = await _send(app_client, phone, "sign_in")
    assert sent.status_code == 404 and sent.json()["code"] == "account_not_found"
    check = await app_client.post(f"{API}/auth/phone/check", json={"phone": phone})
    assert check.json()["registered"] is False
