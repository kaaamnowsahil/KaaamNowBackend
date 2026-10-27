"""Available Workers for a Business: location freshness, the anonymised map dots, and the
admin-editable search radius (audited, falls back to the env defaults)."""

from __future__ import annotations

import pytest

from tests.integration.test_admin_crud import _admin
from tests.integration.test_live_work import API, BIZ, _location, _place_worker

pytestmark = pytest.mark.asyncio(loop_scope="session")

ADMIN = f"{API}/admin"
EFFECTIVE = f"{ADMIN}/settings/search-radius"
# ~4 km north of the Work Location: inside the default 5 km, outside a 3 km admin radius.
WORKER_OFFSET_DEG = 0.036


async def _available(client, business, lat: float, lng: float) -> dict:  # type: ignore[no-untyped-def]
    resp = await client.get(
        f"{BIZ}/available-workers",
        params={"lat": lat, "lng": lng, "category": "house-help"},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_stale_location_hides_worker_until_heartbeat(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    business = await make_business()
    worker = await make_worker("Heartbeat Worker")
    lat, lng = _location()
    worker_lat = lat + WORKER_OFFSET_DEG + 0.000123
    await _place_worker(app_client, worker, worker_lat, lng)

    fresh = await _available(app_client, business, lat, lng)
    assert fresh["count"] == 1
    assert fresh["workers"] == [{"latitude": round(worker_lat, 3), "longitude": round(lng, 3)}]
    assert "worker_id" not in str(fresh) and "Heartbeat" not in str(fresh)

    await db.execute(
        "UPDATE worker_locations SET recorded_at = now() - interval '10 minutes' "
        "WHERE worker_profile_id = (SELECT id FROM worker_profiles WHERE user_id = $1)",
        worker.user_id,
    )
    stale = await _available(app_client, business, lat, lng)
    assert stale["count"] == 0 and stale["workers"] == []

    beat = await app_client.put(
        f"{API}/me/location",
        json={"latitude": worker_lat, "longitude": lng, "accuracy_m": 15},
        headers=worker.headers,
    )
    assert beat.status_code == 200, beat.text
    assert (await _available(app_client, business, lat, lng))["count"] == 1


async def test_admin_search_radius_applies_and_is_audited(  # type: ignore[no-untyped-def]
    app_client, make_business, make_worker, db
) -> None:
    admin = await _admin(app_client, db)
    business = await make_business()
    worker = await make_worker("Radius Worker")
    lat, lng = _location()
    await _place_worker(app_client, worker, lat + WORKER_OFFSET_DEG, lng)

    try:
        effective = await app_client.get(EFFECTIVE, headers=admin.headers)
        assert effective.status_code == 200, effective.text
        assert effective.json()["source"] == "default"
        assert (await _available(app_client, business, lat, lng))["count"] == 1

        created = await app_client.post(
            f"{ADMIN}/search_radius_settings",
            json={
                "live_initial_radius_km": 2,
                "live_max_radius_km": 3,
                "scheduled_notify_radius_km": 25,
                "feed_radius_km": 10,
                "worker_max_shift_distance_km": 20,
                "notes": "Tighter Live Work search",
            },
            headers=admin.headers,
        )
        assert created.status_code == 201, created.text
        row_id = created.json()["id"]

        now = (await app_client.get(EFFECTIVE, headers=admin.headers)).json()
        assert now["source"] == "admin"
        assert (now["live_max_radius_km"], now["worker_max_shift_distance_km"]) == (3.0, 20.0)
        narrowed = await _available(app_client, business, lat, lng)
        assert narrowed["radius_km"] == 3.0 and narrowed["count"] == 0

        backwards = await app_client.patch(
            f"{ADMIN}/search_radius_settings/{row_id}",
            json={"live_initial_radius_km": 5},
            headers=admin.headers,
        )
        assert backwards.status_code == 400, backwards.text

        second = await app_client.post(
            f"{ADMIN}/search_radius_settings",
            json={
                "live_initial_radius_km": 1,
                "live_max_radius_km": 2,
                "scheduled_notify_radius_km": 2,
                "feed_radius_km": 2,
                "worker_max_shift_distance_km": 2,
            },
            headers=admin.headers,
        )
        assert second.status_code == 409, second.text

        audited = await db.fetchval(
            "SELECT count(*) FROM admin_audit_log WHERE resource = 'search_radius_settings' "
            "AND actor_user_id = $1",
            admin.user_id,
        )
        assert audited == 1

        not_admin = await app_client.get(EFFECTIVE, headers=business.headers)
        assert not_admin.status_code == 403
    finally:
        await db.execute("DELETE FROM search_radius_settings")
