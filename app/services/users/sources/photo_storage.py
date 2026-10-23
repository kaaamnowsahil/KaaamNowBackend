"""Profile photo / business logo storage, selected by ``MEDIA_STORAGE``.

* ``local``       — disk under ``MEDIA_DIR``, served under ``MEDIA_BASE_URL``.
* ``vercel_blob`` — public Vercel Blob store; credentials come from the linked project
  (``BLOB_READ_WRITE_TOKEN`` or OIDC + ``BLOB_STORE_ID``).

Every stored object gets a fresh random name, so a replaced image never reuses a URL and
deleting the previous object cannot affect the new one.
"""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from app.config.settings import load_settings
from app.constants.application.application_constants import (
    BLOB_ACCESS_PUBLIC,
    BLOB_HOST_SUFFIX,
    BLOB_ROOT_FOLDER,
    MEDIA_STORAGE_VERCEL_BLOB,
)
from app.constants.users.user_route_strings import (
    ALLOWED_PHOTO_CONTENT_TYPES,
    MSG_PHOTO_CONTENT,
    MSG_PHOTO_TOO_LARGE,
    MSG_PHOTO_TYPE,
)
from app.exceptions.api_errors import bad_request
from app.observability.logging import get_logger, log_extra
from app.paths import DEFAULT_MEDIA_DIR

log = get_logger(__name__)

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class PhotoStorage(Protocol):
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        """Persist bytes and return a public URL."""
        ...

    async def delete(self, url: str) -> None:
        """Remove an object previously returned by ``save``; ignore foreign URLs."""
        ...


def media_root() -> Path:
    configured = load_settings().media_dir.strip()
    return Path(configured) if configured else DEFAULT_MEDIA_DIR


def uses_local_media() -> bool:
    return load_settings().media_storage != MEDIA_STORAGE_VERCEL_BLOB


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(content_type: str, data: bytes) -> str:
    """Check declared type, size and magic bytes; return the file extension to store."""
    extension = ALLOWED_PHOTO_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise bad_request("photo_type", MSG_PHOTO_TYPE)
    if len(data) > load_settings().max_photo_bytes:
        raise bad_request("photo_too_large", MSG_PHOTO_TOO_LARGE)
    if sniff_image_type(data) != content_type:
        raise bad_request("photo_content", MSG_PHOTO_CONTENT)
    return extension


class LocalPhotoStorage:
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        name = f"{uuid.uuid4().hex}{extension}"
        target_dir = media_root() / folder
        await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((target_dir / name).write_bytes, data)
        return f"{self._base_url()}/{folder}/{name}"

    async def delete(self, url: str) -> None:
        prefix = f"{self._base_url()}/"
        if not url.startswith(prefix):
            return
        root = media_root().resolve()
        target = (root / url.removeprefix(prefix)).resolve()
        if root not in target.parents:
            return
        await asyncio.to_thread(target.unlink, missing_ok=True)

    @staticmethod
    def _base_url() -> str:
        return load_settings().media_base_url.rstrip("/")


class VercelBlobPhotoStorage:
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        from vercel import blob

        uploaded = await blob.put_blob(
            f"{BLOB_ROOT_FOLDER}/{folder}/{uuid.uuid4().hex}{extension}",
            data,
            access=BLOB_ACCESS_PUBLIC,
            content_type=mimetypes.guess_type(f"file{extension}")[0],
        )
        return uploaded.url

    async def delete(self, url: str) -> None:
        parts = urlsplit(url)
        if not (parts.hostname or "").endswith(BLOB_HOST_SUFFIX):
            return
        if not parts.path.startswith(f"/{BLOB_ROOT_FOLDER}/"):
            return
        from vercel import blob

        await blob.delete_blob(url)


def get_photo_storage() -> PhotoStorage:
    if uses_local_media():
        return LocalPhotoStorage()
    return VercelBlobPhotoStorage()


async def delete_images(urls: Iterable[str | None]) -> None:
    """Best-effort cleanup: a failed delete leaves an orphan object, never a broken profile."""
    storage = get_photo_storage()
    for url in urls:
        if not url:
            continue
        try:
            await storage.delete(url)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "image delete failed",
                extra=log_extra(url=url, error_type=type(exc).__name__),
            )
