"""CORS from ``CORS_ORIGIN`` (comma-separated; ``*`` refused in production)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import KaamNowSettings


def configure_cors(app: FastAPI, settings: KaamNowSettings) -> None:
    origins = [origin.strip() for origin in settings.cors_origin.split(",") if origin.strip()]
    wildcard = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
