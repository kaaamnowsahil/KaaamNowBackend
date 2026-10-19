"""KaamNow API process: app factory + uvicorn entrypoint."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.settings import load_settings
from app.constants.application.application_common import PATH_MEDIA
from app.constants.application.application_constants import APP_TITLE, UVICORN_APP_IMPORT_PATH
from app.exceptions.exception_handlers import register_exception_handlers
from app.lifespan import api_lifespan
from app.middleware.cors_setup import configure_cors
from app.middleware.request_context import RequestContextMiddleware
from app.observability.logging import configure_application_logging
from app.router import register_routes
from app.services.users.sources.photo_storage import media_root


def create_kaamnow_api_application() -> FastAPI:
    configure_application_logging()
    settings = load_settings()
    app = FastAPI(
        title=APP_TITLE,
        version=settings.app_version,
        lifespan=api_lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.add_middleware(RequestContextMiddleware)
    configure_cors(app, settings)
    register_exception_handlers(app)
    media_dir = media_root()
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount(PATH_MEDIA, StaticFiles(directory=str(media_dir)), name="media")
    register_routes(app)
    return app


kaamnow_api_application = create_kaamnow_api_application()


def start_kaamnow_api_server() -> None:
    settings = load_settings()
    uvicorn.run(
        UVICORN_APP_IMPORT_PATH,
        host=settings.listen_host,
        port=settings.port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    start_kaamnow_api_server()
