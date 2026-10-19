"""Profile photo storage. Local disk served under ``MEDIA_BASE_URL``.

Production object storage (S3 / GCS) is an OWNER DECISION; implement ``PhotoStorage``.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Protocol

from app.config.settings import load_settings
from app.paths import DEFAULT_MEDIA_DIR


class PhotoStorage(Protocol):
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        """Persist bytes and return a public URL."""
        ...


def media_root() -> Path:
    configured = load_settings().media_dir.strip()
    return Path(configured) if configured else DEFAULT_MEDIA_DIR


class LocalPhotoStorage:
    async def save(self, folder: str, data: bytes, extension: str) -> str:
        settings = load_settings()
        name = f"{uuid.uuid4().hex}{extension}"
        target_dir = media_root() / folder
        await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((target_dir / name).write_bytes, data)
        return f"{settings.media_base_url.rstrip('/')}/{folder}/{name}"


def get_photo_storage() -> PhotoStorage:
    return LocalPhotoStorage()
