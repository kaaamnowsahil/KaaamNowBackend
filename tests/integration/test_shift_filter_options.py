"""Admin-managed worker shift filter options."""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import httpx
import pytest

from tests.integration.conftest import login
from tests.integration.test_admin_crud import _admin

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1/shift-filter-options"


async def test_seeded_options_are_public(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get(API)

    assert response.status_code == 200
    options = response.json()
    assert all(option["is_active"] for option in options)
    assert {
        ("distance", "within-1-km"),
        ("minimum_pay", "130-per-hour"),
        ("shift_length", "up-to-4-hours"),
    } <= {(option["filter_type"], option["slug"]) for option in options}


async def test_shift_filter_options_require_admin_for_management(
    app_client: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    worker = await login(app_client)
    body = {
        "filter_type": "distance",
        "slug": f"test-{uuid4().hex[:8]}",
        "label": "Test distance",
        "min_value": None,
        "max_value": 8,
        "sort_order": 90,
        "is_active": True,
    }

    assert (await app_client.get(API, params={"include_inactive": "true"})).status_code == 401
    assert (
        await app_client.get(API, headers=worker.headers, params={"include_inactive": "true"})
    ).status_code == 403
    assert (await app_client.post(API, json=body)).status_code == 401
    assert (await app_client.post(API, headers=worker.headers, json=body)).status_code == 403

    admin = await _admin(app_client, db)
    created = await app_client.post(API, headers=admin.headers, json=body)
    assert created.status_code == 201, created.text
    item = created.json()

    duplicate = await app_client.post(API, headers=admin.headers, json=body)
    assert duplicate.status_code == 409

    updated = await app_client.patch(
        f"{API}/{item['id']}",
        headers=admin.headers,
        json={"label": "Updated distance", "max_value": 9},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["label"] == "Updated distance"
    assert updated.json()["max_value"] == 9

    deleted = await app_client.delete(f"{API}/{item['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    public_options = await app_client.get(API)
    assert item["id"] not in {option["id"] for option in public_options.json()}

    inactive_options = await app_client.get(
        API, headers=admin.headers, params={"include_inactive": "true"}
    )
    inactive = next(option for option in inactive_options.json() if option["id"] == item["id"])
    assert inactive["is_active"] is False

    restored = await app_client.patch(
        f"{API}/{item['id']}", headers=admin.headers, json={"is_active": True}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"] is True
