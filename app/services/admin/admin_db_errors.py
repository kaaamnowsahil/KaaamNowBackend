"""Translate Postgres constraint / data errors into clean admin ``ApiError`` responses."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import asyncpg
from asyncpg.exceptions._base import DataError as ClientDataError

from app.constants.admin.admin_route_strings import (
    ERR_CHECK_VIOLATION,
    ERR_FOREIGN_KEY_VIOLATION,
    ERR_INVALID_DATA,
    ERR_NOT_NULL_VIOLATION,
    ERR_UNIQUE_VIOLATION,
    MSG_CHECK_VIOLATION,
    MSG_FOREIGN_KEY_VIOLATION,
    MSG_INVALID_DATA,
    MSG_NOT_NULL_VIOLATION,
    MSG_UNIQUE_VIOLATION,
)
from app.exceptions.api_errors import bad_request, conflict


def _details(exc: asyncpg.PostgresError) -> dict[str, Any]:
    return {
        "constraint": getattr(exc, "constraint_name", None),
        "column": getattr(exc, "column_name", None),
        "detail": getattr(exc, "detail", None),
    }


@contextmanager
def translate_db_errors() -> Iterator[None]:
    try:
        yield
    except asyncpg.UniqueViolationError as exc:
        raise conflict(ERR_UNIQUE_VIOLATION, MSG_UNIQUE_VIOLATION, _details(exc)) from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise conflict(ERR_FOREIGN_KEY_VIOLATION, MSG_FOREIGN_KEY_VIOLATION, _details(exc)) from exc
    except asyncpg.CheckViolationError as exc:
        raise bad_request(ERR_CHECK_VIOLATION, MSG_CHECK_VIOLATION, _details(exc)) from exc
    except asyncpg.NotNullViolationError as exc:
        raise bad_request(ERR_NOT_NULL_VIOLATION, MSG_NOT_NULL_VIOLATION, _details(exc)) from exc
    except (asyncpg.DataError, ClientDataError) as exc:
        raise bad_request(ERR_INVALID_DATA, MSG_INVALID_DATA, {"detail": str(exc)}) from exc
