"""Domain / application exceptions mapped to one JSON shape.

Every error response body is ``{"code": str, "message": str, "details": object | null}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import status


class ApiError(Exception):
    """Base application error with an HTTP status and a stable machine code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class AuthenticationError(ApiError):
    def __init__(self, message: str, code: str = "not_authenticated") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, code, message)


class AuthorizationError(ApiError):
    def __init__(self, message: str, code: str = "forbidden") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, code, message)


def not_found(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, code, message)


def conflict(code: str, message: str, details: Any | None = None) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message, details)


def bad_request(code: str, message: str, details: Any | None = None) -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, code, message, details)


def forbidden(code: str, message: str) -> ApiError:
    return AuthorizationError(message, code)


def too_many_requests(code: str, message: str, details: Any | None = None) -> ApiError:
    return ApiError(status.HTTP_429_TOO_MANY_REQUESTS, code, message, details)
