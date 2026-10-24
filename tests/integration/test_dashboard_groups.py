"""Business / Work Home groups shifts into Completed, Coming up, In progress and Expired."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
GROUP_ORDER = ["completed", "upcoming", "in_progress", "expired"]


def _item(days: int) -> dict:
    starts = (datetime.now(UTC) + timedelta(days=days)).replace(microsecond=0)
    return {
        "category_slug": "hospitality",
        "job_title": f"Waiter day {days}",
        "workers_required": 1,
        "hourly_rate_minor": 15000,
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=6)).isoformat(),
    }


async def _dashboard(client: httpx.AsyncClient, headers: dict) -> dict:
    resp = await client.get(
        f"{API}/business/dashboard", params={"tab": "scheduled"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_empty_dashboard_still_returns_every_group(
    app_client: httpx.AsyncClient, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Empty Cafe")
    body = await _dashboard(app_client, business.headers)
    assert [g["key"] for g in body["groups"]] == GROUP_ORDER
    assert [g["title"] for g in body["groups"]] == [
        "Completed",
        "Coming up",
        "In progress",
        "Expired",
    ]
    assert all(g["shifts"] == [] for g in body["groups"])
    assert body["shifts"] == []


async def test_scheduled_tab_shows_next_two_upcoming_only(
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_business
) -> None:  # type: ignore[no-untyped-def]
    business = await make_business("Group Cafe")
    created = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"publish": True, "shifts": [_item(d) for d in (1, 2, 3, 4, 5, 6)]},
        headers=business.headers,
    )
    assert created.status_code == 201, created.text
    done, cancelled, filled, nxt, later, expired = (s["id"] for s in created.json()["items"])
    draft = await app_client.post(
        f"{API}/business/shifts/bulk",
        json={"shifts": [_item(1)]},
        headers=business.headers,
    )
    assert draft.status_code == 201, draft.text

    now = datetime.now(UTC)
    await db.execute("UPDATE shifts SET status = 'completed' WHERE id = $1", done)
    await db.execute("UPDATE shifts SET status = 'cancelled' WHERE id = $1", cancelled)
    await db.execute("UPDATE shifts SET status = 'filled' WHERE id = $1", filled)
    await db.execute(
        "UPDATE shifts SET status = 'expired', starts_at = $2, ends_at = $3 WHERE id = $1",
        expired,
        now - timedelta(hours=8),
        now - timedelta(hours=2),
    )

    body = await _dashboard(app_client, business.headers)
    assert [(s["id"], s["status"]) for s in body["shifts"]] == [
        (filled, "filled"),
        (nxt, "open"),
    ]
    by_group = {g["key"]: [s["id"] for s in g["shifts"]] for g in body["groups"]}
    assert by_group == {
        "completed": [],
        "upcoming": [filled, nxt],
        "in_progress": [],
        "expired": [],
    }
    assert set(body["summary"]) == {
        "active_shifts",
        "workers_booked",
        "pending_applications",
        "awaiting_review",
        "unpaid_invoices",
    }

    full = await app_client.get(
        f"{API}/business/shifts", params={"limit": 50}, headers=business.headers
    )
    assert full.status_code == 200, full.text
    statuses = {s["id"]: s["status"] for s in full.json()["items"]}
    assert statuses[done] == "completed"
    assert statuses[expired] == "expired"
    assert statuses[later] == "open"
    assert len(statuses) == 7
    groups = {s["id"]: s["group"] for s in full.json()["items"]}
    assert groups[done] == "completed"
    assert groups[cancelled] == "cancelled"
    assert groups[expired] == "expired"
    assert groups[filled] == "upcoming"
    assert groups[draft.json()["items"][0]["id"]] == "draft"
    assert [(g["key"], g["count"]) for g in full.json()["group_counts"]] == [
        ("upcoming", 3),
        ("in_progress", 0),
        ("draft", 1),
        ("completed", 1),
        ("expired", 1),
        ("cancelled", 1),
    ]

    upcoming = await app_client.get(
        f"{API}/business/shifts", params={"group": "upcoming"}, headers=business.headers
    )
    assert [s["id"] for s in upcoming.json()["items"]] == [filled, nxt, later]
