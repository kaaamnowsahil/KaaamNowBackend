"""Shared list pagination helpers for API routers."""

from __future__ import annotations

from app.config.settings import load_settings


def clamp_page_limit(limit: int | None) -> int:
    """Apply default and max page size from settings."""
    settings = load_settings()
    return min(limit or settings.pagination_default_limit, settings.pagination_max_limit)


__all__ = ["clamp_page_limit"]
