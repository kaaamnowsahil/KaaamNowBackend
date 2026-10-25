"""Admin-only CRUD for FAQ entries and Terms & Conditions, reflected in the public reads."""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import httpx
import pytest

from tests.integration.conftest import login
from tests.integration.test_admin_crud import _admin

pytestmark = pytest.mark.asyncio(loop_scope="session")

ADMIN = "/api/v1/admin"
PUBLIC = "/api/v1/content"


async def test_faq_crud_is_admin_only(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    worker = await login(app_client)
    body = {"audience": "worker", "question": f"How do I test {uuid4().hex[:6]}?", "answer": "A"}
    assert (await app_client.get(f"{ADMIN}/faqs")).status_code == 401
    assert (
        await app_client.post(f"{ADMIN}/faqs", json=body, headers=worker.headers)
    ).status_code == 403

    admin = await _admin(app_client, db)
    created = await app_client.post(f"{ADMIN}/faqs", json=body, headers=admin.headers)
    assert created.status_code == 201, created.text
    faq = created.json()
    duplicate = await app_client.post(f"{ADMIN}/faqs", json=body, headers=admin.headers)
    assert duplicate.status_code == 409

    public = await app_client.get(f"{PUBLIC}/faqs", params={"audience": "worker"})
    assert faq["id"] in [item["id"] for item in public.json()["items"]]

    hidden = await app_client.patch(
        f"{ADMIN}/faqs/{faq['id']}",
        json={"is_active": False, "answer": "Updated"},
        headers=admin.headers,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["answer"] == "Updated"
    public = await app_client.get(f"{PUBLIC}/faqs", params={"audience": "worker"})
    assert faq["id"] not in [item["id"] for item in public.json()["items"]]
    listed = await app_client.get(f"{ADMIN}/faqs", headers=admin.headers)
    assert faq["id"] in [item["id"] for item in listed.json()]

    deleted = await app_client.delete(f"{ADMIN}/faqs/{faq['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    gone = await app_client.delete(f"{ADMIN}/faqs/{faq['id']}", headers=admin.headers)
    assert gone.status_code == 404


async def test_terms_upsert_is_admin_only(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    worker = await login(app_client)
    body = {
        "title": "Business terms",
        "body_markdown": "## Payments\nPay on time.\n\n## Cancellations\nCancel early.",
        "effective_date": "2026-11-01",
    }
    assert (
        await app_client.put(f"{ADMIN}/terms/business", json=body, headers=worker.headers)
    ).status_code == 403

    admin = await _admin(app_client, db)
    saved = await app_client.put(f"{ADMIN}/terms/business", json=body, headers=admin.headers)
    assert saved.status_code == 200, saved.text
    body["title"] = "Business terms v2"
    replaced = await app_client.put(f"{ADMIN}/terms/business", json=body, headers=admin.headers)
    assert replaced.json()["id"] == saved.json()["id"]

    public = (await app_client.get(f"{PUBLIC}/terms", params={"audience": "business"})).json()
    assert public["title"] == "Business terms v2"
    assert [s["title"] for s in public["sections"]] == ["Payments", "Cancellations"]
    listed = await app_client.get(f"{ADMIN}/terms", headers=admin.headers)
    assert "business" in [page["audience"] for page in listed.json()]

    deleted = await app_client.delete(f"{ADMIN}/terms/business", headers=admin.headers)
    assert deleted.status_code == 204
