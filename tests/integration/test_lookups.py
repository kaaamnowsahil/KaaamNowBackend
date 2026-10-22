"""Work categories + business types CRUD: public reads, admin writes, effect on sign-up."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import asyncpg
import httpx
import pytest

from tests.integration.conftest import TEST_OTP, login, next_phone
from tests.integration.test_admin_crud import _admin

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"


def _worker_signup(slug: str) -> dict[str, Any]:
    return {
        "role": "worker",
        "worker": {
            "full_name": "Lookup Worker",
            "age": 23,
            "address_text": "Powai, Mumbai",
            "work_type_slugs": [slug],
        },
    }


def _business_signup(slug: str) -> dict[str, Any]:
    return {
        "role": "business",
        "business": {
            "business_name": "Lookup Cafe",
            "contact_name": "Owner",
            "address_text": "Bandra West, Mumbai",
            "business_type_slug": slug,
        },
    }


LOOKUPS = [
    pytest.param("work-categories", "work_category", _worker_signup, id="work-categories"),
    pytest.param("business-types", "business_type", _business_signup, id="business-types"),
]


async def _signup(client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
    phone = next_phone()
    await client.post(
        "/api/v1/auth/otp/send",
        json={"phone": phone, "intent": "sign_up", "role": payload["role"]},
    )
    return await client.post(
        "/api/v1/auth/signup", json={"phone": phone, "code": TEST_OTP, **payload}
    )


def _slugs(resp: httpx.Response) -> set[str]:
    return {item["slug"] for item in resp.json()}


@pytest.mark.parametrize(("path", "_prefix", "_signup_body"), LOOKUPS)
async def test_lookup_reads_public_writes_admin(
    app_client: httpx.AsyncClient, path: str, _prefix: str, _signup_body: Any
) -> None:
    base = f"{API}/{path}"
    listed = await app_client.get(base)
    assert listed.status_code == 200
    assert all(item["is_active"] for item in listed.json())

    user = await login(app_client)
    body = {"slug": "nope", "name": "Nope"}
    assert (await app_client.post(base, json=body)).status_code == 401
    assert (await app_client.post(base, headers=user.headers, json=body)).status_code == 403
    inactive = {"include_inactive": "true"}
    assert (await app_client.get(base, params=inactive)).status_code == 401
    forbidden = await app_client.get(base, headers=user.headers, params=inactive)
    assert forbidden.status_code == 403


@pytest.mark.parametrize(("path", "prefix", "signup_body"), LOOKUPS)
async def test_lookup_crud_drives_signup(
    app_client: httpx.AsyncClient,
    db: asyncpg.Connection,
    path: str,
    prefix: str,
    signup_body: Any,
) -> None:
    admin = await _admin(app_client, db)
    base = f"{API}/{path}"
    slug = f"test-{uuid4().hex[:6]}"

    created = await app_client.post(
        base, headers=admin.headers, json={"slug": slug, "name": "Test Item", "sort_order": 5}
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["is_active"] is True
    assert slug in _slugs(await app_client.get(base))
    assert (await app_client.get(f"{base}/{item['id']}")).status_code == 200

    duplicate = await app_client.post(base, headers=admin.headers, json={"slug": slug, "name": "x"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == f"{prefix}_slug_taken"
    bad_slug = await app_client.post(
        base, headers=admin.headers, json={"slug": "Bad Slug", "name": "x"}
    )
    assert bad_slug.status_code == 422

    updated = await app_client.patch(
        f"{base}/{item['id']}", headers=admin.headers, json={"name": "Renamed"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed"
    empty = await app_client.patch(f"{base}/{item['id']}", headers=admin.headers, json={})
    assert empty.status_code == 400

    searched = await app_client.get(base, params={"q": slug})
    assert [i["id"] for i in searched.json()] == [item["id"]]

    accepted = await _signup(app_client, signup_body(slug))
    assert accepted.status_code == 201, accepted.text

    deleted = await app_client.delete(f"{base}/{item['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    assert slug not in _slugs(await app_client.get(base))
    assert (await app_client.get(f"{base}/{item['id']}")).status_code == 404
    with_inactive = await app_client.get(
        base, headers=admin.headers, params={"q": slug, "include_inactive": "true"}
    )
    assert [i["id"] for i in with_inactive.json()] == [item["id"]]
    fetched = await app_client.get(f"{base}/{item['id']}", headers=admin.headers)
    assert fetched.json()["is_active"] is False

    rejected = await _signup(app_client, signup_body(slug))
    assert rejected.status_code == 400, rejected.text

    missing = await app_client.get(f"{base}/{uuid4()}", headers=admin.headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == f"{prefix}_not_found"
