"""Flow E: an admin changes Shift commission/tax the way the Admin panel does (new inactive
version → switch the current one off → activate the new one). Only shifts posted afterwards use
the new rates; earlier shifts and their invoices keep their snapshot."""

from __future__ import annotations

from uuid import UUID

import pytest

from tests.integration.test_admin_crud import _admin
from tests.integration.test_promos_support import _shift_body

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
ADMIN_FEES = f"{API}/admin/platform_fee_policies"


async def _post(client, business) -> dict:  # type: ignore[no-untyped-def]
    posted = await client.post(
        f"{API}/business/shifts", json=_shift_body(None), headers=business.headers
    )
    assert posted.status_code == 201, posted.text
    return posted.json()


async def _deposit(client, business, shift: dict) -> dict:  # type: ignore[no-untyped-def]
    resp = await client.get(
        f"{API}/business/invoices/{shift['deposit_invoice_id']}", headers=business.headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_new_fee_policy_applies_to_new_shifts_only(app_client, db, make_business) -> None:  # type: ignore[no-untyped-def]
    admin = await _admin(app_client, db)
    business = await make_business()
    current = await db.fetchrow("SELECT id, version FROM platform_fee_policies WHERE is_active")
    before = await _post(app_client, business)
    before_deposit = await _deposit(app_client, business, before)
    assert before["estimate"]["tax_percentage"] == 2.0

    created = await app_client.post(
        ADMIN_FEES,
        json={
            "version": current["version"] + 100,
            "percentage": 6,
            "worker_percentage": 4,
            "gateway_percentage": 2,
            "tax_percentage": 5,
            "tax_label": "Service tax",
            "is_active": False,
            "notes": "Flow E",
        },
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]
    try:
        off = await app_client.patch(
            f"{ADMIN_FEES}/{current['id']}", json={"is_active": False}, headers=admin.headers
        )
        assert off.status_code == 200, off.text
        on = await app_client.patch(
            f"{ADMIN_FEES}/{new_id}", json={"is_active": True}, headers=admin.headers
        )
        assert on.status_code == 200, on.text

        after = await _post(app_client, business)
        estimate = after["estimate"]
        assert estimate["tax_percentage"] == 5.0
        assert estimate["tax_label"] == "Service tax"
        # ₹120/h × 4h30m = ₹540; 6% commission ₹32.40; 5% tax on ₹572.40 = ₹28.62.
        assert estimate["fee_percentage"] == 6.0
        assert estimate["platform_fee_minor"] == 3_240
        assert estimate["taxable_minor"] == 57_240
        assert estimate["tax_minor"] == 2_862

        snapshot = await db.fetchrow(
            "SELECT fee_percentage, tax_percentage, tax_label FROM shifts WHERE id = $1",
            UUID(before["id"]),
        )
        assert float(snapshot["tax_percentage"]) == 2.0
        assert snapshot["tax_label"] == "Tax"
        assert await _deposit(app_client, business, before) == before_deposit

        actions = await db.fetch(
            "SELECT action, actor_user_id FROM admin_audit_log"
            " WHERE resource = 'platform_fee_policies' AND record_id = ANY($1::text[])"
            " ORDER BY created_at",
            [str(current["id"]), new_id],
        )
        assert [a["action"] for a in actions] == ["create", "update", "update"]
        assert {a["actor_user_id"] for a in actions} == {admin.user_id}
    finally:
        await db.execute("UPDATE platform_fee_policies SET is_active = false WHERE is_active")
        await db.execute(
            "UPDATE platform_fee_policies SET is_active = true WHERE id = $1", current["id"]
        )
        await db.execute("DELETE FROM platform_fee_policies WHERE id = $1", UUID(new_id))


@pytest.mark.parametrize(
    "tampered",
    [
        {"total_minor": 1},
        {"commission_minor": 0},
        {"tax_minor": 0},
        {"promo_discount_minor": 100_000},
        {"user_id": "00000000-0000-0000-0000-000000000000"},
        {"payment_status": "paid"},
    ],
)
async def test_live_work_rejects_client_supplied_price_fields(  # type: ignore[no-untyped-def]
    app_client, make_business, tampered
) -> None:
    from tests.integration.test_live_work import BIZ, _create_body, _location

    business = await make_business()
    lat, lng = _location()
    resp = await app_client.post(
        BIZ, json={**_create_body(lat, lng), **tampered}, headers=business.headers
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "validation_error"


async def test_coupon_quote_rejects_a_client_supplied_discount(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    resp = await app_client.post(
        f"{API}/business/live-work/quote",
        json={"hourly_rate_minor": 50_000, "duration_minutes": 120, "promo_discount_minor": 1},
        headers=business.headers,
    )
    assert resp.status_code == 422, resp.text
