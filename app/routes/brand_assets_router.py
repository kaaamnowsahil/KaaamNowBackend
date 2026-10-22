"""Brand icons (favicon, apple-touch-icon) so browsers and Vercel show the KaaamNow mark."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.constants.application.application_common import (
    APPLE_TOUCH_ICON_FILE,
    BRAND_ASSET_CACHE_CONTROL,
    FAVICON_SVG_FILE,
    MEDIA_TYPE_PNG,
    MEDIA_TYPE_SVG,
    PATH_APPLE_TOUCH_ICON,
    PATH_FAVICON_ICO,
    PATH_FAVICON_SVG,
)
from app.paths import STATIC_DIR

router = APIRouter(include_in_schema=False)

_CACHE_HEADERS = {"Cache-Control": BRAND_ASSET_CACHE_CONTROL}


@router.get(PATH_FAVICON_SVG)
async def favicon_svg() -> FileResponse:
    return FileResponse(
        STATIC_DIR / FAVICON_SVG_FILE, media_type=MEDIA_TYPE_SVG, headers=_CACHE_HEADERS
    )


@router.get(PATH_FAVICON_ICO)
@router.get(PATH_APPLE_TOUCH_ICON)
async def favicon_png() -> FileResponse:
    return FileResponse(
        STATIC_DIR / APPLE_TOUCH_ICON_FILE, media_type=MEDIA_TYPE_PNG, headers=_CACHE_HEADERS
    )
