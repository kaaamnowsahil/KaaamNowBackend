"""Coerce JSON / query-string values to the Python type asyncpg expects for a column."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from app.services.admin.admin_schema_cache import ColumnInfo

_TRUE: Final[frozenset[str]] = frozenset({"true", "1", "yes", "on"})
_FALSE: Final[frozenset[str]] = frozenset({"false", "0", "no", "off"})


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
        return value.strip().lower() in _TRUE
    raise ValueError(value)


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(value)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        raise ValueError(value)
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(value) from exc


def _to_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(value)
    return float(value)


def _to_str(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError(value)
    return str(value)


def _to_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise ValueError(value)
    return UUID(value.strip())


def _to_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError(value)
    parsed = datetime.fromisoformat(value.strip())
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _to_naive_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError(value)
    return datetime.fromisoformat(value.strip())


def _to_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError(value)
    return date.fromisoformat(value.strip())


def _to_time(value: Any) -> time:
    if not isinstance(value, str):
        raise ValueError(value)
    return time.fromisoformat(value.strip())


def _to_json(value: Any) -> Any:
    return value


_SCALAR: Final[dict[str, Callable[[Any], Any]]] = {
    "uuid": _to_uuid,
    "smallint": _to_int,
    "integer": _to_int,
    "bigint": _to_int,
    "numeric": _to_decimal,
    "double precision": _to_float,
    "real": _to_float,
    "boolean": _to_bool,
    "timestamp with time zone": _to_datetime,
    "timestamp without time zone": _to_naive_datetime,
    "date": _to_date,
    "time without time zone": _to_time,
    "json": _to_json,
    "jsonb": _to_json,
}

_ARRAY_ELEMENT: Final[dict[str, Callable[[Any], Any]]] = {
    "_uuid": _to_uuid,
    "_int2": _to_int,
    "_int4": _to_int,
    "_int8": _to_int,
    "_numeric": _to_decimal,
    "_float8": _to_float,
    "_bool": _to_bool,
}


def coerce_value(column: ColumnInfo, value: Any) -> Any:
    """Return a value of the column's type, ``None`` for null, or raise ``ValueError``."""
    if value is None:
        if not column.nullable:
            raise ValueError(value)
        return None
    if column.data_type == "ARRAY":
        if not isinstance(value, list):
            raise ValueError(value)
        element = _ARRAY_ELEMENT.get(column.udt_name, _to_str)
        return [element(v) for v in value]
    coerced = _SCALAR.get(column.data_type, _to_str)(value)
    if isinstance(coerced, str) and column.max_length and len(coerced) > column.max_length:
        raise ValueError(value)
    return coerced
