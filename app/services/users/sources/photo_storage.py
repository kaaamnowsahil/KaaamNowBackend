"""Profile photo storage, selected by ``MEDIA_STORAGE``.

* ``local``       — disk under ``MEDIA_DIR``, served under ``MEDIA_BASE_URL``.
* ``vercel_blob`` — public Vercel Blob store; credentials come from the linked project
  (``BLOB_READ_WRITE_TOKEN`` or OIDC + ``BLOB_STORE_ID``).
"""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from typing import Protocol

from app.config.settings import load_settings
from app.constants.application.application_constants import (
    BLOB_ACCESS_PUBLIC,
    BLOB_ROOT_FOLDER,
    MEDIA_STORAGE_VERCEL_BLOB,
)
from app.paths import DEFAULT_MEDIA_DIR


class PhotoStorage(Protocol):
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        """Persist bytes and return a public URL."""
        ...


def media_root() -> Path:
    configured = load_settings().media_dir.strip()
    return Path(configured) if configured else DEFAULT_MEDIA_DIR


def uses_local_media() -> bool:
    return load_settings().media_storage != MEDIA_STORAGE_VERCEL_BLOB


class LocalPhotoStorage:
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        settings = load_settings()
        name = f"{uuid.uuid4().hex}{extension}"
        target_dir = media_root() / folder
        await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((target_dir / name).write_bytes, data)
        return f"{settings.media_base_url.rstrip('/')}/{folder}/{name}"


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


def get_photo_storage() -> PhotoStorage:
    if uses_local_media():
        return LocalPhotoStorage()
    return VercelBlobPhotoStorage()
