"""Integration harness: local Postgres (``<dev db>_test``, recreated per run) + ASGI app."""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.services.auth import auth_service

TEST_OTP = "123456"
BUSINESS_LAT, BUSINESS_LNG = 28.6315, 77.2167  # Connaught Place
NEAR_LAT, NEAR_LNG = 28.6330, 77.2180  # ~200 m away

_phone_counter = itertools.count(1)


def next_phone() -> str:
    return f"+9190000{next(_phone_counter):05d}"


async def _recreate_database(url: str) -> None:
    parts = urlsplit(url)
    db_name = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    settings = load_settings()
    await _recreate_database(settings.database_url)
    auth_service.new_numeric_code = lambda _length: TEST_OTP  # type: ignore[assignment]

    from app.kaaamnow_api_server import kaaamnow_api_application as app

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()


@dataclass
class Actor:
    phone: str
    user_id: UUID
    headers: dict[str, str]
    profile_id: UUID | None = None


async def login(client: httpx.AsyncClient, phone: str | None = None) -> Actor:
    phone = phone or next_phone()
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO users (phone) VALUES ($1) ON CONFLICT (phone) DO NOTHING", phone
        )
    sent = await client.post("/api/v1/auth/otp/send", json={"phone": phone})
    assert sent.status_code == 200, sent.text
    verified = await client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": TEST_OTP})
    assert verified.status_code == 200, verified.text
    body = verified.json()
    return Actor(
        phone=phone,
        user_id=UUID(body["me"]["id"]),
        headers={"Authorization": f"Bearer {body['tokens']['access_token']}"},
    )


async def pay_deposit(client: httpx.AsyncClient, business: Actor, shift_id: str) -> dict:
    """Pay a published scheduled shift's deposit with the fake provider; returns the shift."""
    shift = await client.get(f"/api/v1/business/shifts/{shift_id}", headers=business.headers)
    assert shift.status_code == 200, shift.text
    assert shift.json()["status"] == "awaiting_payment"
    payment = await client.post(
        f"/api/v1/business/invoices/{shift.json()['deposit_invoice_id']}/payments",
        json={"method": "upi_qr"},
        headers=business.headers,
    )
    assert payment.status_code == 201, payment.text
    confirmed = await client.post(
        f"/api/v1/business/payments/{payment.json()['id']}/confirm", headers=business.headers
    )
    assert confirmed.json()["status"] == "succeeded", confirmed.text
    shift = await client.get(f"/api/v1/business/shifts/{shift_id}", headers=business.headers)
    assert shift.json()["status"] == "open", shift.text
    return shift.json()


async def signup(
    client: httpx.AsyncClient,
    role: str,
    details: dict,
    phone: str | None = None,
    *,
    accept_terms: bool = True,
) -> Actor:
    """Register a role the only supported way: OTP ``sign_up`` + ``POST /auth/signup``."""
    phone = phone or next_phone()
    sent = await client.post("/api/v1/auth/otp/send", json={"phone": phone, "intent": "sign_up"})
    assert sent.status_code == 200, sent.text
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "phone": phone,
            "code": TEST_OTP,
            "password": "TestPassword123",
            "role": role,
            role: details,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    profile = body["me"][f"{role}_profile"]
    actor = Actor(
        phone=phone,
        user_id=UUID(body["me"]["id"]),
        headers={"Authorization": f"Bearer {body['tokens']['access_token']}"},
        profile_id=UUID(profile["id"]),
    )
    terms = (await client.get("/api/v1/me/terms", headers=actor.headers)).json()
    if accept_terms and any(t["audience"] == role and t["version"] for t in terms):
        accepted = await client.post(
            "/api/v1/me/terms/accept", json={"audience": role}, headers=actor.headers
        )
        assert accepted.status_code == 200, accepted.text
    return actor


@pytest.fixture
def make_business(app_client: httpx.AsyncClient):  # type: ignore[no-untyped-def]
    async def _make(name: str = "Cafe Bloom") -> Actor:
        return await signup(
            app_client,
            "business",
            {
                "business_name": name,
                "contact_name": "Owner",
                "business_type_slug": "hospitality",
                "category_slug": "hospitality",
                "address_text": "Block A, Connaught Place",
                "locality": "Connaught Place",
                "latitude": BUSINESS_LAT,
                "longitude": BUSINESS_LNG,
            },
        )

    return _make


@pytest.fixture
def make_worker(app_client: httpx.AsyncClient, db: asyncpg.Connection):  # type: ignore[no-untyped-def]
    async def _make(name: str = "Aarav", *, online: bool = True) -> Actor:
        actor = await signup(
            app_client,
            "worker",
            {
                "full_name": name,
                "age": 25,
                "address_text": "Connaught Place, New Delhi",
                "locality": "Connaught Place",
                "latitude": NEAR_LAT,
                "longitude": NEAR_LNG,
                "work_type_slugs": ["hospitality", "house-help"],
            },
        )
        await db.execute(
            "UPDATE worker_profiles SET verification_status = 'verified', verified_at = now() "
            "WHERE id = $1",
            actor.profile_id,
        )
        if online:
            resp = await app_client.put(
                "/api/v1/me/availability",
                json={"is_available": True, "latitude": NEAR_LAT, "longitude": NEAR_LNG},
                headers=actor.headers,
            )
            assert resp.status_code == 200, resp.text
        return actor

    return _make
