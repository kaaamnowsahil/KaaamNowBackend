"""Liveness / readiness."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import load_settings
from app.constants.application.application_common import (
    OPENAPI_TAG_HEALTH,
    PATH_HEALTH,
    PATH_ROOT,
    SWAGGER_ROLE_PUBLIC,
    swagger_summary,
)
from app.constants.application.application_constants import APP_TITLE
from app.db.pool import get_pool

router = APIRouter(tags=[OPENAPI_TAG_HEALTH])


@router.get(PATH_ROOT, summary=swagger_summary("Service info", SWAGGER_ROLE_PUBLIC))
async def root() -> dict[str, str]:
    settings = load_settings()
    return {"service": APP_TITLE, "version": settings.app_version, "docs": "/docs"}


@router.get(PATH_HEALTH, summary=swagger_summary("Health check", SWAGGER_ROLE_PUBLIC))
async def health() -> JSONResponse:
    try:
        async with get_pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "database": "down"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
