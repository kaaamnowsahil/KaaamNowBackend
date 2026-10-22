"""Vercel entrypoint: exposes the FastAPI application as ``app``."""

from app.kaaamnow_api_server import kaaamnow_api_application as app

__all__ = ["app"]
