"""API process lifespan: config checks, DB bootstrap, background sweep loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.settings import load_settings
from app.constants.application.application_constants import (
    LOG_API_READY,
    LOG_API_SHUTDOWN_COMPLETE,
)
from app.db.bootstrap import bootstrap_database
from app.db.ensure_database import ensure_database_exists
from app.db.pool import close_pool, create_pool
from app.observability.logging import get_logger, log_extra
from app.services.background.background_sweep_loop import (
    start_background_sweep_loop,
    stop_background_sweep_loop,
)
from app.services.notifications.sources.push_sender_factory import push_delivery_status

log = get_logger(__name__)


@asynccontextmanager
async def api_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    settings.validate_production_config()
    push_provider = push_delivery_status()
    if push_provider != "fcm":
        log.warning(
            "push notifications are not delivered to devices",
            extra=log_extra(push_provider=push_provider),
        )
    if settings.db_auto_create:
        await ensure_database_exists(settings.database_url)
    pool = await create_pool()
    await bootstrap_database(pool)
    if settings.background_jobs_enabled:
        await start_background_sweep_loop(pool, settings.background_sweep_interval_seconds)
    log.info(
        LOG_API_READY,
        extra=log_extra(env=settings.env_profile, port=settings.port),
    )
    try:
        yield
    finally:
        await stop_background_sweep_loop()
        await close_pool()
        log.info(LOG_API_SHUTDOWN_COMPLETE)
