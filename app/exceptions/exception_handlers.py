"""Map exceptions to the single documented JSON error body."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError
from app.observability.logging import get_logger, log_extra

log = get_logger(__name__)


def error_response(
    status_code: int, code: str, message: str, details: Any | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "details": details},
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Request validation failed.",
            _validation_details(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, "http_error", str(exc.detail))

    async def _database_unavailable(request: Request, exc: Exception) -> JSONResponse:
        log.warning(
            "database connection lost",
            extra=log_extra(path=request.url.path, error_type=type(exc).__name__),
        )
        # One network drop kills every pooled socket; drop them all now instead of
        # failing the next N requests one by one.
        try:
            await get_pool().expire_connections()
        except RuntimeError:
            pass
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "database_unavailable",
            "We couldn't reach the server. Please try again.",
        )

    for exc_type in (
        asyncpg.exceptions.ConnectionDoesNotExistError,
        asyncpg.exceptions.ConnectionFailureError,
        ConnectionError,
        TimeoutError,
    ):
        app.add_exception_handler(exc_type, _database_unavailable)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled error",
            extra=log_extra(path=request.url.path, error_type=type(exc).__name__),
        )
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Something went wrong. Please try again.",
        )
