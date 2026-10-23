"""Common /me/profile API: role-resolved reads, patches and image uploads."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config.settings import load_settings
from app.services.users.sources.photo_storage import media_root
from tests.integration.conftest import login, signup

pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


def _stored_file(url: str) -> Path:
    prefix = f"{load_settings().media_base_url.rstrip('/')}/"
    assert url.startswith(prefix), url
    return media_root() / url.removeprefix(prefix)


async def _upload(
    client: httpx.AsyncClient, headers: dict[str, str], data: bytes, content_type: str
) -> httpx.Response:
    return await client.post(
        f"{API}/me/profile/image",
        files={"file": ("image", data, content_type)},
        headers=headers,
    )


async def test_account_profile_without_role(app_client: httpx.AsyncClient) -> None:
    actor = await login(app_client)
    profile = await app_client.get(f"{API}/me/profile", headers=actor.headers)
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["profile_type"] == "account"
    assert body["business"] is None and body["worker"] is None
    assert body["account"]["id"] == str(actor.user_id)
    assert body["account"]["language_code"] == "en"
    assert body["account"]["theme_preference"] == "dark"

    light = await app_client.patch(
        f"{API}/me/profile", json={"theme_preference": "light"}, headers=actor.headers
    )
    assert light.json()["account"]["theme_preference"] == "light"
    again = (await app_client.get(f"{API}/me/profile", headers=actor.headers)).json()
    assert again["account"]["theme_preference"] == "light"

    patched = await app_client.patch(
        f"{API}/me/profile",
        json={"full_name": "Asha", "email": "asha@example.com"},
        headers=actor.headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["account"]["full_name"] == "Asha"
    assert patched.json()["account"]["email"] == "asha@example.com"

    business_field = await app_client.patch(
        f"{API}/me/profile", json={"business_name": "Nope"}, headers=actor.headers
    )
    assert business_field.status_code == 422

    photo = await _upload(app_client, actor.headers, JPEG, "image/jpeg")
    assert photo.status_code == 200, photo.text
    assert _stored_file(photo.json()["account"]["photo_url"]).is_file()


async def test_protected_and_foreign_fields_rejected(
    app_client: httpx.AsyncClient,
    make_business,
    make_worker,  # type: ignore[no-untyped-def]
) -> None:
    worker = await make_worker(online=False)
    business = await make_business()
    for field, value in (
        ("verification_status", "verified"),
        ("id", "00000000-0000-0000-0000-000000000000"),
        ("user_id", "00000000-0000-0000-0000-000000000000"),
        ("role", "admin"),
        ("roles", ["admin"]),
        ("rating_avg", 5),
        ("is_available", True),
    ):
        for actor in (worker, business):
            resp = await app_client.patch(
                f"{API}/me/profile", json={field: value}, headers=actor.headers
            )
            assert resp.status_code == 422, (field, resp.text)

    worker_field = await app_client.patch(
        f"{API}/me/profile", json={"age": 30}, headers=business.headers
    )
    assert worker_field.status_code == 422
    assert worker_field.json()["details"][0]["loc"] == ["body", "age"]
    business_field = await app_client.patch(
        f"{API}/me/profile", json={"business_name": "X"}, headers=worker.headers
    )
    assert business_field.status_code == 422
    logo_url = await app_client.patch(
        f"{API}/me/profile",
        json={"logo_url": "https://evil.example/x.png"},
        headers=business.headers,
    )
    assert logo_url.status_code == 422

    profile = (await app_client.get(f"{API}/me/profile", headers=worker.headers)).json()
    assert profile["worker"]["verification_status"] == "verified"


async def test_image_validation(app_client: httpx.AsyncClient, make_worker) -> None:  # type: ignore[no-untyped-def]
    worker = await make_worker(online=False)
    wrong_type = await _upload(app_client, worker.headers, PNG, "image/gif")
    assert wrong_type.status_code == 400 and wrong_type.json()["code"] == "photo_type"

    disguised = await _upload(app_client, worker.headers, b"<svg onload=alert(1)>", "image/png")
    assert disguised.status_code == 400 and disguised.json()["code"] == "photo_content"
    mismatched = await _upload(app_client, worker.headers, JPEG, "image/png")
    assert mismatched.status_code == 400 and mismatched.json()["code"] == "photo_content"
    empty = await _upload(app_client, worker.headers, b"", "image/png")
    assert empty.status_code == 400 and empty.json()["code"] == "photo_content"

    too_big = PNG + b"0" * load_settings().max_photo_bytes
    large = await _upload(app_client, worker.headers, too_big, "image/png")
    assert large.status_code == 400 and large.json()["code"] == "photo_too_large"

    profile = (await app_client.get(f"{API}/me/profile", headers=worker.headers)).json()
    assert profile["account"]["photo_url"] is None


async def test_worker_photo_replacement_deletes_previous(
    app_client: httpx.AsyncClient,
    make_worker,  # type: ignore[no-untyped-def]
) -> None:
    worker = await make_worker(online=False)
    first = await _upload(app_client, worker.headers, PNG, "image/png")
    assert first.status_code == 200, first.text
    first_url = first.json()["worker"]["photo_url"]
    assert first_url == first.json()["account"]["photo_url"]
    assert _stored_file(first_url).is_file()

    second = await _upload(app_client, worker.headers, JPEG, "image/jpeg")
    assert second.status_code == 200, second.text
    second_url = second.json()["worker"]["photo_url"]
    assert second_url != first_url and second_url.endswith(".jpg")
    assert _stored_file(second_url).is_file()
    assert not _stored_file(first_url).exists()


async def test_business_logo_is_separate_from_personal_photo(
    app_client: httpx.AsyncClient,
    make_business,
    db,  # type: ignore[no-untyped-def]
) -> None:
    business = await make_business()
    personal = "https://cdn.example/personal.png"
    await db.execute("UPDATE users SET photo_url = $2 WHERE id = $1", business.user_id, personal)

    first = await _upload(app_client, business.headers, PNG, "image/png")
    assert first.status_code == 200, first.text
    first_logo = first.json()["business"]["logo_url"]
    assert "/logos/" in first_logo
    assert first.json()["account"]["photo_url"] == personal

    second = await _upload(app_client, business.headers, PNG, "image/png")
    second_logo = second.json()["business"]["logo_url"]
    assert second_logo != first_logo
    assert not _stored_file(first_logo).exists() and _stored_file(second_logo).is_file()
    assert second.json()["account"]["photo_url"] == personal


async def test_preferences_patch_for_every_role(
    app_client: httpx.AsyncClient,
    make_business,
    make_worker,  # type: ignore[no-untyped-def]
) -> None:
    account = await login(app_client)
    for actor in (account, await make_worker(online=False), await make_business()):
        resp = await app_client.patch(
            f"{API}/me/profile",
            json={"language_code": "hi", "theme_preference": "dark"},
            headers=actor.headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["account"]["language_code"] == "hi"
        assert resp.json()["account"]["theme_preference"] == "dark"
        unknown = await app_client.patch(
            f"{API}/me/profile", json={"language_code": "zz"}, headers=actor.headers
        )
        assert unknown.status_code == 400 and unknown.json()["code"] == "language_unknown"


async def test_business_owner_name_and_business_email(
    app_client: httpx.AsyncClient,
    make_business,  # type: ignore[no-untyped-def]
) -> None:
    business = await make_business()
    resp = await app_client.patch(
        f"{API}/me/profile",
        json={"full_name": "Neha Owner", "email": "hello@cafe.example"},
        headers=business.headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account"]["full_name"] == "Neha Owner"
    assert body["business"]["owner_name"] == "Neha Owner"
    assert body["business"]["email"] == "hello@cafe.example"
    assert body["account"]["email"] is None


async def test_role_less_account_picks_role_through_signup(
    app_client: httpx.AsyncClient,
    db,  # type: ignore[no-untyped-def]
) -> None:
    actor = await login(app_client)
    await db.execute(
        "UPDATE otp_challenges SET created_at = now() - interval '1 hour' WHERE phone = $1",
        actor.phone,
    )
    worker = await signup(
        app_client,
        "worker",
        {
            "full_name": "Kiran",
            "age": 30,
            "address_text": "Sector 5, HSR Layout, Bengaluru",
            "work_type_slugs": ["hospitality"],
        },
        phone=actor.phone,
    )
    assert worker.user_id == actor.user_id
    body = (await app_client.get(f"{API}/me/profile", headers=worker.headers)).json()
    assert body["profile_type"] == "worker" and body["worker"]["user_id"] == str(actor.user_id)


async def test_worker_presence_and_business_lookup_under_me(
    app_client: httpx.AsyncClient,
    make_business,
    make_worker,  # type: ignore[no-untyped-def]
) -> None:
    business = await make_business()
    worker = await make_worker()
    moved = await app_client.put(
        f"{API}/me/location",
        json={"latitude": 28.6331, "longitude": 77.2181},
        headers=worker.headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["is_available"] is True

    card = await app_client.get(f"{API}/me/workers/{worker.profile_id}", headers=business.headers)
    assert card.status_code == 200, card.text
    assert card.json()["id"] == str(worker.profile_id)
    forbidden = await app_client.get(
        f"{API}/me/workers/{worker.profile_id}", headers=worker.headers
    )
    assert forbidden.status_code == 403
    business_online = await app_client.put(
        f"{API}/me/availability", json={"is_available": False}, headers=business.headers
    )
    assert business_online.status_code == 403

    offline = await app_client.put(
        f"{API}/me/availability", json={"is_available": False}, headers=worker.headers
    )
    assert offline.status_code == 200 and offline.json()["is_available"] is False


async def test_removed_profile_routes(app_client: httpx.AsyncClient) -> None:
    actor = await login(app_client)
    for method, path in (
        ("GET", "/me"),
        ("PATCH", "/me"),
        ("PUT", "/me/active-role"),
        ("POST", "/me/roles"),
        ("POST", "/me/photo"),
        ("GET", "/business/profile"),
        ("PATCH", "/business/profile"),
        ("POST", "/business/profile/logo"),
        ("GET", "/worker/profile"),
        ("PATCH", "/worker/profile"),
        ("PUT", "/worker/availability"),
        ("PUT", "/worker/location"),
        ("GET", "/workers/00000000-0000-0000-0000-000000000000"),
    ):
        resp = await app_client.request(method, f"{API}{path}", headers=actor.headers)
        assert resp.status_code in (404, 405), (method, path, resp.status_code)
