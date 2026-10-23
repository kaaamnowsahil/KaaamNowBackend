"""Several Business / Work entities per account: households, shops, ownership and isolation."""

from __future__ import annotations

from uuid import UUID

import asyncpg
import httpx
import pytest

from tests.integration.conftest import BUSINESS_LAT, BUSINESS_LNG, signup
from tests.integration.test_flows import _work_and_pay

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"

HOUSEHOLD = {
    "business_name": "Sharma Residence",
    "contact_name": "Neha Sharma",
    "business_type_slug": "household",
    "address_text": "House 12, Connaught Place",
    "latitude": BUSINESS_LAT,
    "longitude": BUSINESS_LNG,
}
SHOP = {
    "business_name": "Sharma Kirana",
    "business_type_slug": "grocery",
    "address_text": "Shop 4, Connaught Place",
    "latitude": BUSINESS_LAT,
    "longitude": BUSINESS_LNG,
}


def _shift_body(**extra: object) -> dict:
    return {
        "shift_type": "live",
        "category_slug": "house-help",
        "job_title": "House help",
        "workers_required": 1,
        "hourly_rate_minor": 15000,
        "duration_minutes": 240,
        **extra,
    }


async def test_household_signs_up_and_posts_without_documents(app_client) -> None:  # type: ignore[no-untyped-def]
    owner = await signup(app_client, "business", HOUSEHOLD)
    profile = (await app_client.get(f"{API}/me/profile", headers=owner.headers)).json()
    entity = profile["business"]
    assert profile["profile_type"] == "business"
    assert entity["business_type_slug"] == "household"
    assert entity["business_type_name"] == "Household"
    assert entity["is_primary"] is True
    assert entity["verification_status"] == "pending"

    shift = await app_client.post(
        f"{API}/business/shifts", json=_shift_body(), headers=owner.headers
    )
    assert shift.status_code == 201, shift.text
    assert shift.json()["business_profile_id"] == entity["id"]


async def test_one_account_manages_several_entities(app_client) -> None:  # type: ignore[no-untyped-def]
    owner = await signup(app_client, "business", HOUSEHOLD)
    primary_id = str(owner.profile_id)

    created = await app_client.post(f"{API}/me/businesses", json=SHOP, headers=owner.headers)
    assert created.status_code == 201, created.text
    shop = created.json()
    assert shop["is_primary"] is False
    assert shop["business_type_slug"] == "grocery"
    assert shop["contact_name"] == "Neha Sharma"
    assert shop["user_id"] == str(owner.user_id)

    office = await app_client.post(
        f"{API}/me/businesses",
        json={**SHOP, "business_name": "Sharma Consulting", "business_type_slug": "office"},
        headers=owner.headers,
    )
    assert office.status_code == 201, office.text

    listed = (await app_client.get(f"{API}/me/businesses", headers=owner.headers)).json()
    assert [b["id"] for b in listed][0] == primary_id
    assert {b["business_name"] for b in listed} == {
        "Sharma Residence",
        "Sharma Kirana",
        "Sharma Consulting",
    }

    profile = (await app_client.get(f"{API}/me/profile", headers=owner.headers)).json()
    assert profile["business"]["id"] == primary_id
    assert profile["account"]["business_profile"]["id"] == primary_id

    patched = await app_client.patch(
        f"{API}/me/businesses/{shop['id']}",
        json={"business_name": "Sharma General Store", "business_type_slug": "small-business"},
        headers=owner.headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["business_type_name"] == "Shop / Small Business"
    unchanged = (await app_client.get(f"{API}/me/profile", headers=owner.headers)).json()
    assert unchanged["business"]["business_name"] == "Sharma Residence"

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    logo = await app_client.post(
        f"{API}/me/businesses/{shop['id']}/logo",
        files={"file": ("logo.png", png, "image/png")},
        headers=owner.headers,
    )
    assert logo.status_code == 200, logo.text
    assert logo.json()["logo_url"]
    assert unchanged["business"]["logo_url"] is None

    for_shop = await app_client.post(
        f"{API}/business/shifts",
        json=_shift_body(business_profile_id=shop["id"], job_title="Shop helper", publish=True),
        headers=owner.headers,
    )
    assert for_shop.status_code == 201, for_shop.text
    assert for_shop.json()["business_profile_id"] == shop["id"]
    assert for_shop.json()["workplace_name"] == "Sharma General Store"
    for_home = await app_client.post(
        f"{API}/business/shifts", json=_shift_body(publish=True), headers=owner.headers
    )
    assert for_home.json()["business_profile_id"] == primary_id

    everything = (await app_client.get(f"{API}/business/shifts", headers=owner.headers)).json()
    assert {s["id"] for s in everything["items"]} == {for_shop.json()["id"], for_home.json()["id"]}
    only_shop = (
        await app_client.get(
            f"{API}/business/shifts",
            params={"business_profile_id": shop["id"]},
            headers=owner.headers,
        )
    ).json()
    assert [s["id"] for s in only_shop["items"]] == [for_shop.json()["id"]]
    dashboard = (
        await app_client.get(
            f"{API}/business/dashboard",
            params={"tab": "live", "business_profile_id": primary_id},
            headers=owner.headers,
        )
    ).json()
    assert [s["id"] for s in dashboard["shifts"]] == [for_home.json()["id"]]


async def test_entity_has_several_business_work_types(app_client) -> None:  # type: ignore[no-untyped-def]
    household = {k: v for k, v in HOUSEHOLD.items() if k != "business_type_slug"}
    owner = await signup(
        app_client,
        "business",
        {**household, "business_type_slugs": ["household", "rental-property", "household"]},
    )
    entity = (await app_client.get(f"{API}/me/profile", headers=owner.headers)).json()["business"]
    assert entity["business_type_slugs"] == ["household", "rental-property"]
    assert entity["business_type_names"] == ["Household", "Rental Property"]
    assert entity["business_type_slug"] == "household"

    patched = await app_client.patch(
        f"{API}/me/profile",
        json={"business_type_slugs": ["retail", "grocery"]},
        headers=owner.headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["business"]["business_type_slugs"] == ["retail", "grocery"]
    assert patched.json()["business"]["business_type_slug"] == "retail"

    legacy = await app_client.patch(
        f"{API}/me/profile", json={"business_type_slug": "office"}, headers=owner.headers
    )
    assert legacy.json()["business"]["business_type_slugs"] == ["office"]

    shop = {k: v for k, v in SHOP.items() if k != "business_type_slug"}
    created = await app_client.post(
        f"{API}/me/businesses",
        json={**shop, "business_type_slugs": ["grocery", "bakery"]},
        headers=owner.headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["business_type_slugs"] == ["grocery", "bakery"]
    edited = await app_client.patch(
        f"{API}/me/businesses/{created.json()['id']}",
        json={"business_type_slugs": ["bakery"]},
        headers=owner.headers,
    )
    assert edited.json()["business_type_slugs"] == ["bakery"]
    listed = (await app_client.get(f"{API}/me/businesses", headers=owner.headers)).json()
    assert [b["business_type_slugs"] for b in listed] == [["office"], ["bakery"]]

    missing = await app_client.post(f"{API}/me/businesses", json=shop, headers=owner.headers)
    assert missing.status_code == 422
    empty = await app_client.post(
        f"{API}/me/businesses", json={**shop, "business_type_slugs": []}, headers=owner.headers
    )
    assert empty.status_code == 422
    unknown = await app_client.patch(
        f"{API}/me/profile",
        json={"business_type_slugs": ["retail", "spaceport"]},
        headers=owner.headers,
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "business_type_unknown"


async def test_entity_validation(app_client, make_worker) -> None:  # type: ignore[no-untyped-def]
    owner = await signup(app_client, "business", HOUSEHOLD)
    unknown = await app_client.post(
        f"{API}/me/businesses",
        json={**SHOP, "business_type_slug": "spaceport"},
        headers=owner.headers,
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "business_type_unknown"

    for forbidden_field in ("user_id", "is_primary", "verification_status", "rating_avg"):
        resp = await app_client.post(
            f"{API}/me/businesses", json={**SHOP, forbidden_field: "x"}, headers=owner.headers
        )
        assert resp.status_code == 422, forbidden_field
    patch = await app_client.patch(
        f"{API}/me/businesses/{owner.profile_id}",
        json={"verification_status": "verified"},
        headers=owner.headers,
    )
    assert patch.status_code == 422

    worker = await make_worker(online=False)
    denied = await app_client.post(f"{API}/me/businesses", json=SHOP, headers=worker.headers)
    assert denied.status_code == 403
    anonymous = await app_client.get(f"{API}/me/businesses")
    assert anonymous.status_code == 401


async def test_entities_are_isolated_between_accounts(app_client) -> None:  # type: ignore[no-untyped-def]
    owner = await signup(app_client, "business", HOUSEHOLD)
    shop = (await app_client.post(f"{API}/me/businesses", json=SHOP, headers=owner.headers)).json()
    shift = (
        await app_client.post(
            f"{API}/business/shifts",
            json=_shift_body(business_profile_id=shop["id"]),
            headers=owner.headers,
        )
    ).json()
    intruder = await signup(app_client, "business", {**HOUSEHOLD, "business_name": "Other"})

    for method, path, kwargs in (
        ("GET", f"/me/businesses/{shop['id']}", {}),
        ("PATCH", f"/me/businesses/{shop['id']}", {"json": {"business_name": "Mine now"}}),
        ("GET", f"/business/shifts/{shift['id']}", {}),
        ("POST", f"/business/shifts/{shift['id']}/cancel", {"json": {}}),
        ("GET", "/business/shifts", {"params": {"business_profile_id": shop["id"]}}),
        ("GET", "/business/dashboard", {"params": {"business_profile_id": shop["id"]}}),
        ("GET", "/business/payments", {"params": {"business_profile_id": shop["id"]}}),
        (
            "POST",
            "/business/shifts",
            {"json": _shift_body(business_profile_id=shop["id"])},
        ),
    ):
        resp = await app_client.request(method, f"{API}{path}", headers=intruder.headers, **kwargs)
        assert resp.status_code == 404, (method, path, resp.text)

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    logo = await app_client.post(
        f"{API}/me/businesses/{shop['id']}/logo",
        files={"file": ("logo.png", png, "image/png")},
        headers=intruder.headers,
    )
    assert logo.status_code == 404
    mine = (await app_client.get(f"{API}/me/businesses", headers=intruder.headers)).json()
    assert [b["id"] for b in mine] == [str(intruder.profile_id)]
    theirs = (await app_client.get(f"{API}/business/shifts", headers=intruder.headers)).json()
    assert theirs["items"] == []
    still = (
        await app_client.get(f"{API}/me/businesses/{shop['id']}", headers=owner.headers)
    ).json()
    assert still["business_name"] == "Sharma Kirana"


async def test_invoice_payment_and_rating_follow_the_entity(  # type: ignore[no-untyped-def]
    app_client: httpx.AsyncClient, db: asyncpg.Connection, make_worker
) -> None:
    owner = await signup(app_client, "business", HOUSEHOLD)
    shop = (await app_client.post(f"{API}/me/businesses", json=SHOP, headers=owner.headers)).json()
    worker = await make_worker("Kiran")
    shift = (
        await app_client.post(
            f"{API}/business/shifts",
            json=_shift_body(business_profile_id=shop["id"], publish=True),
            headers=owner.headers,
        )
    ).json()
    accepted = await app_client.post(
        f"{API}/worker/live-shifts/{shift['id']}/accept", headers=worker.headers
    )
    assert accepted.status_code == 200, accepted.text
    assignment_id = accepted.json()["id"]
    detail = (
        await app_client.get(f"{API}/business/shifts/{shift['id']}", headers=owner.headers)
    ).json()

    receipt = await _work_and_pay(app_client, db, owner, worker, detail, assignment_id)
    assert receipt["business_name"] == "Sharma Kirana"
    invoice_entity = await db.fetchval(
        "SELECT business_profile_id FROM shift_invoices WHERE shift_id = $1", UUID(shift["id"])
    )
    payment_entity = await db.fetchval(
        "SELECT p.business_profile_id FROM payments p JOIN shift_invoices i ON i.id = p.invoice_id "
        "WHERE i.shift_id = $1 AND p.status = 'succeeded'",
        UUID(shift["id"]),
    )
    assert str(invoice_entity) == str(payment_entity) == shop["id"]

    history = (
        await app_client.get(
            f"{API}/business/payments",
            params={"business_profile_id": shop["id"]},
            headers=owner.headers,
        )
    ).json()
    assert [i["shift_id"] for i in history["items"]] == [shift["id"]]
    home_history = (
        await app_client.get(
            f"{API}/business/payments",
            params={"business_profile_id": str(owner.profile_id)},
            headers=owner.headers,
        )
    ).json()
    assert home_history["items"] == []

    rated = await app_client.post(
        f"{API}/assignments/{assignment_id}/ratings", json={"stars": 4}, headers=worker.headers
    )
    assert rated.status_code == 201, rated.text
    shop_now = (
        await app_client.get(f"{API}/me/businesses/{shop['id']}", headers=owner.headers)
    ).json()
    home_now = (await app_client.get(f"{API}/me/profile", headers=owner.headers)).json()
    assert shop_now["rating_count"] == 1 and float(shop_now["rating_avg"]) == 4.0
    assert home_now["business"]["rating_count"] == 0
