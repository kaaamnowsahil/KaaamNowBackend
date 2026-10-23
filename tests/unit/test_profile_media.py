"""Profile-type resolution and image validation / storage ownership rules."""

from __future__ import annotations

import pytest

from app.exceptions.api_errors import ApiError
from app.services.profiles.profile_service import resolve_profile_type
from app.services.users.sources import photo_storage
from app.services.users.sources.photo_storage import (
    LocalPhotoStorage,
    VercelBlobPhotoStorage,
    sniff_image_type,
    validate_image,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 8
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "


@pytest.mark.parametrize(
    ("active_role", "roles", "expected"),
    [
        ("business", ["business"], "business"),
        ("worker", ["worker"], "worker"),
        (None, ["worker"], "worker"),
        (None, [], "account"),
        ("admin", ["admin"], "account"),
        ("admin", ["admin", "business"], "account"),
    ],
)
def test_resolve_profile_type(active_role: str | None, roles: list[str], expected: str) -> None:
    assert resolve_profile_type(active_role, roles) == expected


def test_sniff_image_type() -> None:
    assert sniff_image_type(PNG) == "image/png"
    assert sniff_image_type(JPEG) == "image/jpeg"
    assert sniff_image_type(WEBP) == "image/webp"
    assert sniff_image_type(b"GIF89a....") is None
    assert sniff_image_type(b"") is None


@pytest.mark.parametrize(
    ("content_type", "data", "code"),
    [
        ("image/gif", PNG, "photo_type"),
        ("", PNG, "photo_type"),
        ("image/png", JPEG, "photo_content"),
        ("image/webp", b"RIFF\x00\x00\x00\x00AVI ", "photo_content"),
        ("image/jpeg", b"", "photo_content"),
    ],
)
def test_validate_image_rejects(content_type: str, data: bytes, code: str) -> None:
    with pytest.raises(ApiError) as caught:
        validate_image(content_type, data)
    assert caught.value.code == code


def test_validate_image_accepts() -> None:
    assert validate_image("image/png", PNG) == ".png"
    assert validate_image("image/jpeg", JPEG) == ".jpg"
    assert validate_image("image/webp", WEBP) == ".webp"


async def test_local_delete_only_touches_managed_files(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(photo_storage, "media_root", lambda: tmp_path / "media")
    storage = LocalPhotoStorage()
    url = await storage.save("avatars", PNG, ".png")
    outside = tmp_path / "secret.txt"
    outside.write_text("keep")

    await storage.delete("https://elsewhere.example/avatars/x.png")
    await storage.delete(url.rsplit("/avatars/", 1)[0] + "/../secret.txt")
    assert outside.exists()

    stored = tmp_path / "media" / "avatars" / url.rsplit("/", 1)[1]
    assert stored.is_file()
    await storage.delete(url)
    assert not stored.exists()
    await storage.delete(url)


async def test_blob_delete_ignores_foreign_urls(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    deleted: list[str] = []

    async def fake_delete(url: str) -> None:
        deleted.append(url)

    from vercel import blob

    monkeypatch.setattr(blob, "delete_blob", fake_delete)
    storage = VercelBlobPhotoStorage()
    await storage.delete("https://cdn.example/media/avatars/a.png")
    await storage.delete("https://abc.public.blob.vercel-storage.com/other/a.png")
    own = "https://abc.public.blob.vercel-storage.com/media/logos/a.png"
    await storage.delete(own)
    assert deleted == [own]
