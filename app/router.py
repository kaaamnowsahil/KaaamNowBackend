"""Register every HTTP router on the app."""

from __future__ import annotations

from fastapi import FastAPI

from app.routes.auth.auth_router import router as auth_router
from app.routes.health_router import router as health_router
from app.routes.users.me_router import router as me_router


def register_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
