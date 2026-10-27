"""Per-user coupons across Live Work and Shift: listing, validation reasons, reservation on
posting, application on payment, restoration on full refund, concurrency and admin audit.

Live Work booking: ₹500/h × 2h → base ₹1,000; commission 4% ₹40; tax 2% on base + commission.
A 50%-off-commission coupon takes ₹20 off; tax is then 2% of ₹1,020 = ₹20.40.
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest

from app.db.pool import get_pool
from app.services.background.background_sweep_loop import run_sweep_once
from tests.integration.conftest import Actor
from tests.integration.test_admin_crud import _admin
from tests.integration.test_live_work import BIZ, TOTAL, _create_body, _location, _pay
from tests.integration.test_promos_support import _shift_body

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
PROMO = f"{API}/business/promo-codes"
HALF_OFF_TOTAL = 100_000 + 2_000 + 2_040

_codes = itertools.count(1)


def _code(prefix: str) -> str:
    return f"{prefix}{next(_codes):04d}"


async def _coupon(db: asyncpg.Connection, code: str, **fields: object) -> UUID:
    values: dict = {
        "target_role": "business",
        "discount_type": "percent",
        "discount_value": 50,
        "applies_to": "commission",
        "booking_types": "all",
        "max_uses": None,
        "max_uses_per_user": 1,
        "owner_user_id": None,
        "is_listed": False,
        "is_active": True,
        "min_booking_minor": None,
        "valid_from": datetime.now(UTC) - timedelta(days=1),
        "valid_until": None,
        "title": "",
        **fields,
    }
    columns = ", ".join(["code", *values])
    params = ", ".join(f"${i}" for i in range(1, len(values) + 2))
    return await db.fetchval(
        f"INSERT INTO promo_codes ({columns}) VALUES ({params}) RETURNING id",
        code,
        *values.values(),
    )


async def _used(db: asyncpg.Connection, promo_id: UUID) -> int:
    return await db.fetchval("SELECT used_count FROM promo_codes WHERE id = $1", promo_id)


async def _redemption(db: asyncpg.Connection, booking_id: str) -> asyncpg.Record | None:
    return await db.fetchrow(
        "SELECT * FROM promo_redemptions WHERE shift_id = $1 ORDER BY created_at DESC LIMIT 1",
        UUID(booking_id),
    )


async def _post_live(
    client: httpx.AsyncClient, business: Actor, code: str | None, **overrides: object
) -> httpx.Response:
    lat, lng = _location()
    body = _create_body(lat, lng, **{"promo_code": code, "expected_total_minor": None, **overrides})
    return await client.post(BIZ, json=body, headers=business.headers)


# --- listing + validation ----------------------------------------------------------------


async def test_promotions_list_shows_assigned_and_listed_coupons_with_eligibility(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    other = await make_business()
    mine = _code("MINE")
    listed = _code("LIST")
    hidden = _code("HIDE")
    theirs = _code("THEIRS")
    shift_only = _code("SHIFT")
    big = _code("BIG")
    await _coupon(db, mine, owner_user_id=business.user_id, title="Welcome back")
    await _coupon(db, listed, is_listed=True)
    await _coupon(db, hidden)
    await _coupon(db, theirs, owner_user_id=other.user_id)
    await _coupon(db, shift_only, is_listed=True, booking_types="shift")
    await _coupon(db, big, is_listed=True, min_booking_minor=500_000)

    resp = await app_client.get(
        f"{PROMO}/available",
        params={"booking_type": "live", "amount_minor": 100_000},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text
    items = {i["code"]: i for i in resp.json()["items"]}
    assert mine in items and listed in items
    assert hidden not in items and theirs not in items
    assert items[mine]["eligible"] is True and items[mine]["title"] == "Welcome back"
    assert items[mine]["is_voucher"] is True
    assert items[shift_only]["eligible"] is False
    assert items[shift_only]["ineligible_reason"] == "wrong_booking_type"
    assert items[big]["ineligible_reason"] == "below_minimum"
    assert items[big]["min_booking_minor"] == 500_000
    assert items[mine]["message"] is None
    assert items[big]["message"]


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        (
            {
                "valid_until": datetime.now(UTC) - timedelta(minutes=1),
                "valid_from": datetime.now(UTC) - timedelta(days=2),
            },
            "expired",
        ),
        ({"is_active": False}, "not_found"),
        ({"valid_from": datetime.now(UTC) + timedelta(days=1)}, "not_started"),
        ({"booking_types": "shift"}, "wrong_booking_type"),
        ({"applies_to": "gateway"}, "not_applicable"),
        ({"min_booking_minor": 200_000}, "below_minimum"),
        ({"target_role": "worker"}, "wrong_role"),
        ({"max_uses": 1, "used_count": 1}, "used_up"),
    ],
)
async def test_validate_reports_each_reason(  # type: ignore[no-untyped-def]
    app_client, make_business, db, fields, reason
) -> None:
    business = await make_business()
    code = _code("BAD")
    await _coupon(db, code, **fields)
    resp = await app_client.post(
        f"{PROMO}/validate",
        json={"code": code, "booking_type": "live", "amount_minor": 100_000},
        headers=business.headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "promo_invalid"
    assert resp.json()["details"]["reason"] == reason
    assert resp.json()["request_id"]


async def test_someone_elses_coupon_looks_like_it_does_not_exist(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    owner = await make_business()
    intruder = await make_business()
    code = _code("OWNED")
    await _coupon(db, code, owner_user_id=owner.user_id)
    resp = await app_client.post(f"{PROMO}/validate", json={"code": code}, headers=intruder.headers)
    assert resp.json()["details"]["reason"] == "not_found"
    ok = await app_client.post(f"{PROMO}/validate", json={"code": code}, headers=owner.headers)
    assert ok.status_code == 200, ok.text


async def test_workers_and_anonymous_users_cannot_browse_business_coupons(  # type: ignore[no-untyped-def]
    app_client, make_worker
) -> None:
    worker = await make_worker("Coupon Peeker", online=False)
    assert (await app_client.get(f"{PROMO}/available", headers=worker.headers)).status_code == 403
    assert (await app_client.get(f"{PROMO}/available")).status_code == 401


async def test_booking_type_and_amount_are_validated(app_client, make_business) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    resp = await app_client.get(
        f"{PROMO}/available",
        params={"booking_type": "hourly", "amount_minor": -5},
        headers=business.headers,
    )
    assert resp.status_code == 422


# --- Live Work lifecycle -----------------------------------------------------------------


async def test_live_quote_shows_the_verified_discount(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    code = _code("QUOTE")
    await _coupon(db, code)
    quote = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": 50_000, "duration_minutes": 120, "promo_code": code},
        headers=business.headers,
    )
    assert quote.status_code == 200, quote.text
    q = quote.json()
    assert q["promo_code"] == code
    assert q["promo_discount_minor"] == 2_000
    assert q["commission_minor"] == 4_000
    assert q["taxable_minor"] == 102_000
    assert q["tax_minor"] == 2_040
    assert q["total_minor"] == HALF_OFF_TOTAL
    assert q["worker_net_minor"] == 96_000  # the Business coupon never touches worker pay

    bad = await app_client.post(
        f"{BIZ}/quote",
        json={"hourly_rate_minor": 50_000, "duration_minutes": 120, "promo_code": "NOPE-NOPE"},
        headers=business.headers,
    )
    assert bad.status_code == 400
    assert bad.json()["details"]["reason"] == "not_found"


async def test_live_coupon_is_reserved_on_post_and_applied_on_payment(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    code = _code("LIVE")
    promo_id = await _coupon(db, code)
    posted = await _post_live(app_client, business, code, expected_total_minor=HALF_OFF_TOTAL)
    assert posted.status_code == 201, posted.text
    booking = posted.json()
    assert booking["deposit_invoice"]["total_minor"] == HALF_OFF_TOTAL
    assert booking["pricing"]["promo_code"] == code
    assert booking["pricing"]["promo_discount_minor"] == 2_000
    assert (await _redemption(db, booking["booking_id"]))["status"] == "reserved"
    assert await _used(db, promo_id) == 1
    snapshot = await db.fetchrow(
        "SELECT promo_code_id, promo_code, promo_discount_minor, total_minor"
        " FROM live_booking_pricing WHERE shift_id = $1",
        UUID(booking["booking_id"]),
    )
    assert snapshot["promo_code_id"] == promo_id
    assert snapshot["promo_discount_minor"] == 2_000
    assert snapshot["total_minor"] == HALF_OFF_TOTAL

    invoice = await db.fetchrow(
        "SELECT promo_code, promo_discount_minor, platform_fee_minor FROM shift_invoices"
        " WHERE id = $1",
        UUID(booking["deposit_invoice"]["id"]),
    )
    assert (invoice["promo_code"], invoice["promo_discount_minor"]) == (code, 2_000)
    assert invoice["platform_fee_minor"] == 2_000

    await _pay(app_client, business, booking["deposit_invoice"]["id"])
    redemption = await _redemption(db, booking["booking_id"])
    assert redemption["status"] == "applied"
    assert redemption["discount_minor"] == 2_000

    again = await _post_live(app_client, business, code)
    assert again.status_code == 400
    assert again.json()["details"]["reason"] == "already_used"


async def test_stale_price_with_coupon_is_rejected(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    code = _code("STALE")
    promo_id = await _coupon(db, code)
    resp = await _post_live(app_client, business, code, expected_total_minor=TOTAL)
    assert resp.status_code == 409
    assert resp.json()["code"] == "price_changed"
    assert resp.json()["details"]["total_minor"] == HALF_OFF_TOTAL
    assert await _used(db, promo_id) == 0


async def test_coupon_is_restored_when_booking_is_cancelled_before_payment(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    code = _code("UNPAID")
    promo_id = await _coupon(db, code)
    booking = (await _post_live(app_client, business, code)).json()
    cancelled = await app_client.post(
        f"{BIZ}/{booking['booking_id']}/cancel",
        json={"reason": "changed_plans"},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert (await _redemption(db, booking["booking_id"]))["status"] == "released"
    assert await _used(db, promo_id) == 0
    reused = await _post_live(app_client, business, code)
    assert reused.status_code == 201, reused.text


async def test_coupon_is_restored_on_full_refund_before_acceptance(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    code = _code("REFUND")
    promo_id = await _coupon(db, code)
    booking = (await _post_live(app_client, business, code)).json()
    await _pay(app_client, business, booking["deposit_invoice"]["id"])
    preview = await app_client.get(
        f"{BIZ}/{booking['booking_id']}/cancel-preview", headers=business.headers
    )
    assert preview.json()["business_refund_minor"] == HALF_OFF_TOTAL
    await app_client.post(
        f"{BIZ}/{booking['booking_id']}/cancel",
        json={"reason": "changed_plans"},
        headers=business.headers,
    )
    assert (await _redemption(db, booking["booking_id"]))["status"] == "released"
    assert await _used(db, promo_id) == 0


async def test_coupon_is_restored_when_the_payment_window_lapses(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    code = _code("LAPSE")
    promo_id = await _coupon(db, code)
    booking = (await _post_live(app_client, business, code)).json()
    await db.execute(
        "UPDATE shifts SET published_at = now() - interval '2 hours' WHERE id = $1",
        UUID(booking["booking_id"]),
    )
    await run_sweep_once(get_pool())
    state = await app_client.get(f"{BIZ}/{booking['booking_id']}", headers=business.headers)
    assert state.json()["status"] == "cancelled"
    assert await _used(db, promo_id) == 0


async def test_concurrent_redemptions_never_exceed_the_limit(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    code = _code("RACE")
    promo_id = await _coupon(db, code, max_uses=1, max_uses_per_user=1)
    businesses = [await make_business() for _ in range(4)]
    results = await asyncio.gather(*[_post_live(app_client, b, code) for b in businesses])
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 400, 400, 400], [r.text for r in results]
    assert {r.json()["details"]["reason"] for r in results if r.status_code == 400} == {"used_up"}
    assert await _used(db, promo_id) == 1


async def test_shift_posting_rejects_a_live_only_coupon(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    code = _code("LIVEONLY")
    await _coupon(db, code, booking_types="live")
    resp = await app_client.post(
        f"{API}/business/shifts", json=_shift_body(code), headers=business.headers
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["details"]["reason"] == "wrong_booking_type"


# --- admin audit -------------------------------------------------------------------------


async def test_admin_coupon_and_fee_policy_changes_are_audited(app_client, db) -> None:  # type: ignore[no-untyped-def]
    admin = await _admin(app_client, db)
    code = _code("AUDIT")
    created = await app_client.post(
        f"{API}/admin/promo_codes",
        json={
            "code": code,
            "target_role": "business",
            "discount_type": "flat",
            "discount_value": 25,
            "applies_to": "commission",
            "max_uses_per_user": 1,
            "source": "admin",
        },
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    promo_id = created.json()["id"]
    updated = await app_client.patch(
        f"{API}/admin/promo_codes/{promo_id}", json={"is_active": False}, headers=admin.headers
    )
    assert updated.status_code == 200, updated.text
    rows = await db.fetch(
        "SELECT action, actor_user_id, old_values, new_values FROM admin_audit_log"
        " WHERE resource = 'promo_codes' AND record_id = $1 ORDER BY created_at",
        promo_id,
    )
    assert [r["action"] for r in rows] == ["create", "update"]
    assert all(r["actor_user_id"] == admin.user_id for r in rows)
    assert '"is_active": true' in rows[1]["old_values"]
    assert '"is_active": false' in rows[1]["new_values"]

    bad = await app_client.post(
        f"{API}/admin/platform_fee_policies",
        json={"version": 999, "percentage": 4, "tax_percentage": 120},
        headers=admin.headers,
    )
    assert bad.status_code in (400, 409, 422), bad.text


async def test_restoring_twice_gives_the_use_back_only_once(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    from app.repositories.promos import promo_repository
    from app.services.promos import promo_service

    business = await make_business()
    code = _code("TWICE")
    promo_id = await _coupon(db, code, max_uses=5)
    booking = (await _post_live(app_client, business, code)).json()
    await app_client.post(
        f"{BIZ}/{booking['booking_id']}/cancel",
        json={"reason": "changed_plans"},
        headers=business.headers,
    )
    assert await _used(db, promo_id) == 0
    async with get_pool().acquire() as conn:
        await promo_service.restore_for_booking(
            conn, UUID(booking["booking_id"]), datetime.now(UTC)
        )
        released = await _redemption(db, booking["booking_id"])
        await promo_repository.restore(conn, released, datetime.now(UTC))
    assert await _used(db, promo_id) == 0


async def test_used_up_general_coupons_are_hidden_but_assigned_ones_explain_why(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    business = await make_business()
    general = _code("GONE")
    mine = _code("MINEGONE")
    ids = [
        await _coupon(db, general, is_listed=True, max_uses=1),
        await _coupon(db, mine, owner_user_id=business.user_id, max_uses=1),
    ]
    await db.execute("UPDATE promo_codes SET used_count = 1 WHERE id = ANY($1::uuid[])", ids)
    listed = await app_client.get(f"{PROMO}/available", headers=business.headers)
    assert listed.status_code == 200, listed.text
    by_code = {i["code"].upper(): i for i in listed.json()["items"]}
    assert general not in by_code
    assert by_code[mine]["eligible"] is False
    assert by_code[mine]["ineligible_reason"] == "used_up"


async def test_business_sees_its_own_vouchers(app_client, make_business, db) -> None:  # type: ignore[no-untyped-def]
    business = await make_business()
    code = _code("VOUCH")
    await _coupon(db, code, owner_user_id=business.user_id)
    vouchers = await app_client.get(PROMO, headers=business.headers)
    assert vouchers.status_code == 200, vouchers.text
    assert code in {i["code"].upper() for i in vouchers.json()["items"]}


async def test_worker_sees_the_code_waiting_for_the_next_payout(
    app_client, make_worker, db
) -> None:  # type: ignore[no-untyped-def]
    worker = await make_worker(online=False)
    code = _code("WNEXT")
    await _coupon(db, code, target_role="worker")
    empty = await app_client.get(f"{API}/worker/promo-codes", headers=worker.headers)
    assert empty.status_code == 200 and empty.json()["pending"] is None
    redeemed = await app_client.post(
        f"{API}/worker/promo-codes/redeem", json={"code": code}, headers=worker.headers
    )
    assert redeemed.status_code == 200, redeemed.text
    status = await app_client.get(f"{API}/worker/promo-codes", headers=worker.headers)
    assert status.json()["pending"]["code"].upper() == code


async def test_shift_coupon_reservation_is_idempotent_and_gone_after_cancel(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    from app.services.promos import promo_service

    business = await make_business()
    code = _code("SHIFTONCE")
    promo_id = await _coupon(db, code, booking_types="shift", max_uses=5)
    posted = await app_client.post(
        f"{API}/business/shifts", json=_shift_body(code), headers=business.headers
    )
    assert posted.status_code == 201, posted.text
    shift_id = UUID(posted.json()["id"])
    async with get_pool().acquire() as conn:
        shift = await conn.fetchrow("SELECT * FROM shifts WHERE id = $1", shift_id)
        await promo_service.reserve_for_shift(conn, shift, business.user_id, datetime.now(UTC))
        assert (await promo_service.shift_promo(conn, shift)).code.upper() == code
    assert await _used(db, promo_id) == 1
    cancelled = await app_client.post(
        f"{API}/business/shifts/{shift_id}/cancel",
        json={"reason": "Plans changed"},
        headers=business.headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    async with get_pool().acquire() as conn:
        shift = await conn.fetchrow("SELECT * FROM shifts WHERE id = $1", shift_id)
        assert await promo_service.shift_promo(conn, shift) is None


async def test_final_bill_above_what_was_paid_stays_pending_without_paying_the_worker(  # type: ignore[no-untyped-def]
    app_client, make_business, db
) -> None:
    from app.repositories.live_work import live_work_repository
    from app.services.live_work import live_work_billing
    from app.services.live_work.live_pricing import LiveCharge

    business = await make_business()
    booking = (await _post_live(app_client, business, None)).json()
    shift_id = UUID(booking["booking_id"])
    async with get_pool().acquire() as conn:
        pricing = await live_work_repository.get_booking_pricing(conn, shift_id)
        invoice_id = await live_work_billing.create_final_invoice(
            conn,
            pricing,
            assignment_id=None,
            charge=LiveCharge(100_000, 4_000, 104_000, 2_080, 4_000),
            description="Reserved 2h",
            minutes=120,
            paid_minor=50_000,
            now=datetime.now(UTC),
        )
    invoice = await db.fetchrow("SELECT * FROM shift_invoices WHERE id = $1", invoice_id)
    assert invoice["status"] == "pending"
    assert invoice["refund_due_minor"] == 0
    assert invoice["total_minor"] == 106_080
    assert (
        await db.fetchval(
            "SELECT count(*) FROM earning_ledger_entries WHERE invoice_id = $1", invoice_id
        )
        == 0
    )
