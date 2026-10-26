"""Multi-date shift posting: bulk create and bulk publish of saved drafts are all-or-nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"


def _day(days: int, hour: int = 9) -> datetime:
    base = (datetime.now(UTC) + timedelta(days=days)).replace(microsecond=0)
    return base.replace(hour=hour, minute=0, second=0)


def _item(days: int, **overrides) -> dict:  # type: ignore[no-untyped-def]
    starts = _day(days)
    item = {
        "category_slug": "hospitality",
        "job_title": "Waiter",
        "responsibilities": "Serve tables",
        "workers_required": 2,
        "hourly_rate_minor": 15000,
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=6)).isoformat(),
        "break_minutes": 30,
    }
    item.update(overrides)
    return item


async def _shift_count(db: asyncpg.Connection, business_user_id) -> int:  # type: ignore[no-untyped-def]
    return await db.fetchval(
        "SELECT count(*) FROM shifts s JOIN business_profiles bp ON bp.id = s.business_profile_id "
        "WHERE bp.user_id = $1",
        business_user_id,
    )


async def test_bulk_create_drafts_keeps_per_date_details(
    app_client: httpx.AsyncClient, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Bulk Cafe")
    resp = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={
            "shifts": [
                _item(2),
                _item(
                    3,
                    job_title="Cook",
                    category_slug="cooking",
                    workers_required=1,
                    hourly_rate_minor=20000,
                    break_minutes=0,
                    responsibilities="Prep",
                ),
                _item(4, break_minutes=45),
            ]
        },
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    items = resp.json()["items"]
    assert [i["status"] for i in items] == ["draft", "draft", "draft"]
    assert [i["break_minutes"] for i in items] == [30, 0, 45]
    assert items[1]["job_title"] == "Cook"
    assert items[1]["category_slug"] == "cooking"
    assert items[1]["workers_required"] == 1
    assert items[1]["hourly_rate_minor"] == 20000
    assert items[1]["responsibilities"] == "Prep"
    assert all(i["shift_type"] == "scheduled" for i in items)


async def test_bulk_create_failure_rolls_back_every_date(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Rollback Cafe")
    before = await _shift_count(db, business.user_id)
    resp = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={
            "publish": True,
            "shifts": [_item(2), _item(3), _item(4, category_slug="no-such-category")],
        },
        headers=business.headers,
    )
    assert resp.status_code >= 400, resp.text
    assert resp.json()["details"]["index"] == 2
    assert await _shift_count(db, business.user_id) == before


async def test_bulk_publish_posts_existing_drafts(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Draft Cafe")
    created = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"shifts": [_item(2), _item(5)]},
        headers=business.headers,
    )
    draft_ids = [i["id"] for i in created.json()["items"]]
    before = await _shift_count(db, business.user_id)

    resp = await app_client.post(
        f"{API}/business/shifts/bulk-publish",
        json={"shift_ids": draft_ids},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["id"] for i in items] == draft_ids
    assert {i["status"] for i in items} == {"awaiting_payment"}
    assert await _shift_count(db, business.user_id) == before


async def test_bulk_publish_is_all_or_nothing(app_client: httpx.AsyncClient, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Partial Cafe")
    created = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"shifts": [_item(2), _item(3)]},
        headers=business.headers,
    )
    first, second = (i["id"] for i in created.json()["items"])
    published = await app_client.post(
        f"{API}/business/shifts/{second}/publish", headers=business.headers
    )
    assert published.status_code == 200, published.text

    resp = await app_client.post(
        f"{API}/business/shifts/bulk-publish",
        json={"shift_ids": [first, second]},
        headers=business.headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["details"] == {"index": 1, "shift_id": second}
    still = await app_client.get(f"{API}/business/shifts/{first}", headers=business.headers)
    assert still.json()["status"] == "draft"


async def test_bulk_publish_rejects_other_business_and_duplicates(
    app_client: httpx.AsyncClient, make_business
) -> None:  # type: ignore[no-untyped-def]
    owner = await make_business("Owner Cafe")
    other = await make_business("Other Cafe")
    created = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"shifts": [_item(2)]},
        headers=owner.headers,
    )
    draft_id = created.json()["items"][0]["id"]

    foreign = await app_client.post(
        f"{API}/business/shifts/bulk-publish",
        json={"shift_ids": [draft_id]},
        headers=other.headers,
    )
    assert foreign.status_code == 404, foreign.text
    assert foreign.json()["details"]["index"] == 0

    duplicate = await app_client.post(
        f"{API}/business/shifts/bulk-publish",
        json={"shift_ids": [draft_id, draft_id]},
        headers=owner.headers,
    )
    assert duplicate.status_code == 422, duplicate.text
    mine = await app_client.get(f"{API}/business/shifts/{draft_id}", headers=owner.headers)
    assert mine.json()["status"] == "draft"


async def test_shift_site_location_does_not_need_profile_location(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Home Office Events")
    await db.execute(
        "UPDATE business_profiles SET latitude = NULL, longitude = NULL WHERE id = $1",
        business.profile_id,
    )
    site = _item(
        2,
        address_text="Thazhambur, Chennai, Tamil Nadu 600130",
        latitude=12.8454,
        longitude=80.1995,
    )
    resp = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"publish": True, "shifts": [site]},
        headers=business.headers,
    )
    assert resp.status_code == 201, resp.text
    shift = resp.json()["items"][0]
    assert shift["status"] == "awaiting_payment"
    assert shift["address_text"] == site["address_text"]

    missing = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"shifts": [_item(3)]},
        headers=business.headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["code"] == "shift_location_required"
