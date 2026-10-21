"""Generic, registry-driven admin CRUD over every business table."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from typing import Any

from app.constants.admin.admin_route_strings import (
    COLUMN_IS_ACTIVE,
    COMPOSITE_KEY_SEPARATOR,
    DELETE_MODE_SOFT,
    ERR_EMPTY_BODY,
    ERR_INVALID_FIELDS,
    ERR_INVALID_FILTER,
    ERR_INVALID_KEY,
    ERR_INVALID_SORT,
    ERR_INVALID_VALUE,
    ERR_OPERATION_NOT_ALLOWED,
    ERR_RECORD_NOT_FOUND,
    ERR_RESOURCE_NOT_FOUND,
    EXPORT_MAX_ROWS,
    FILTER_NULL_LITERAL,
    MSG_EMPTY_BODY,
    MSG_FIELD_READ_ONLY,
    MSG_FIELD_REQUIRED,
    MSG_FIELD_TYPE,
    MSG_FIELD_UNKNOWN,
    MSG_INVALID_FIELDS,
    MSG_INVALID_FILTER,
    MSG_INVALID_KEY,
    MSG_INVALID_SORT,
    MSG_INVALID_VALUE,
    MSG_OPERATION_NOT_ALLOWED,
    MSG_RECORD_NOT_FOUND,
    MSG_RESOURCE_NOT_FOUND,
    NOTIFICATION_DATA_COLUMN,
    NOTIFICATION_KIND_COLUMN,
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    RESOURCE_NOTIFICATIONS,
    SORT_DESC_PREFIX,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, forbidden, not_found
from app.pagination import clamp_page_limit
from app.repositories.admin import admin_repository
from app.schemas.admin.admin_schemas import (
    AdminColumn,
    AdminRecord,
    AdminRecordPage,
    AdminResourceInfo,
    AdminResourceList,
)
from app.services.admin import admin_schema_cache
from app.services.admin.admin_coercion import coerce_value
from app.services.admin.admin_db_errors import translate_db_errors
from app.services.admin.admin_schema_cache import ResolvedResource

# --- Resolution / validation helpers ---


async def _resolve(name: str) -> ResolvedResource:
    resolved = await admin_schema_cache.resolve(name)
    if resolved is None:
        raise not_found(ERR_RESOURCE_NOT_FOUND, MSG_RESOURCE_NOT_FOUND)
    return resolved


def _require_op(resolved: ResolvedResource, op: str) -> None:
    if op not in resolved.resource.operations:
        raise forbidden(ERR_OPERATION_NOT_ALLOWED, MSG_OPERATION_NOT_ALLOWED)


def _type_error(resolved: ResolvedResource, column: str, value: Any) -> str:
    if value is None:
        return MSG_FIELD_REQUIRED
    return MSG_FIELD_TYPE.format(data_type=resolved.columns[column].data_type)


def _parse_key(resolved: ResolvedResource, record_id: str) -> dict[str, Any]:
    parts = record_id.split(COMPOSITE_KEY_SEPARATOR)
    if len(parts) != len(resolved.primary_key):
        raise bad_request(ERR_INVALID_KEY, MSG_INVALID_KEY)
    key: dict[str, Any] = {}
    for column, raw in zip(resolved.primary_key, parts, strict=True):
        try:
            key[column] = coerce_value(resolved.columns[column], raw)
        except ValueError as exc:
            raise bad_request(ERR_INVALID_KEY, MSG_INVALID_KEY) from exc
    return key


def _coerce_body(
    resolved: ResolvedResource, body: Mapping[str, Any], writable: frozenset[str]
) -> dict[str, Any]:
    field_errors: dict[str, str] = {}
    for column in body:
        if column not in resolved.visible:
            field_errors[column] = MSG_FIELD_UNKNOWN
        elif column not in writable:
            field_errors[column] = MSG_FIELD_READ_ONLY
    if field_errors:
        raise bad_request(ERR_INVALID_FIELDS, MSG_INVALID_FIELDS, field_errors)
    values: dict[str, Any] = {}
    for column, raw in body.items():
        try:
            values[column] = coerce_value(resolved.columns[column], raw)
        except ValueError:
            field_errors[column] = _type_error(resolved, column, raw)
    if field_errors:
        raise bad_request(ERR_INVALID_VALUE, MSG_INVALID_VALUE, field_errors)
    return values


def _filters(resolved: ResolvedResource, raw_filters: Mapping[str, str]) -> list[tuple[str, Any]]:
    allowed = set(resolved.filterable)
    unknown = sorted(f for f in raw_filters if f not in allowed)
    if unknown:
        raise bad_request(ERR_INVALID_FILTER, MSG_INVALID_FILTER, {"fields": unknown})
    parsed: list[tuple[str, Any]] = []
    field_errors: dict[str, str] = {}
    for column, raw in raw_filters.items():
        if raw == FILTER_NULL_LITERAL:
            parsed.append((column, None))
            continue
        try:
            parsed.append((column, coerce_value(resolved.columns[column], raw)))
        except ValueError:
            field_errors[column] = _type_error(resolved, column, raw)
    if field_errors:
        raise bad_request(ERR_INVALID_FILTER, MSG_INVALID_FILTER, field_errors)
    return parsed


def _order(resolved: ResolvedResource, sort: str | None) -> list[tuple[str, bool]]:
    spec = (sort or "").strip() or resolved.default_sort
    desc = spec.startswith(SORT_DESC_PREFIX)
    column = spec.removeprefix(SORT_DESC_PREFIX)
    if column not in resolved.sortable:
        raise bad_request(ERR_INVALID_SORT, MSG_INVALID_SORT, {"sortable": resolved.sortable})
    order = [(column, desc)]
    order += [(pk, False) for pk in resolved.primary_key if pk != column]
    return order


def _search_term(q: str | None) -> str | None:
    return (q or "").strip() or None


def _record(row: Mapping[str, Any]) -> AdminRecord:
    return dict(row)


# --- Hooks ---


def _prepare_create(resolved: ResolvedResource, values: dict[str, Any]) -> dict[str, Any]:
    """Admin-sent notifications get the same ``data.kind`` envelope as service-sent ones;
    the pending ``push_status`` default makes the background loop deliver the push."""
    if resolved.name == RESOURCE_NOTIFICATIONS and NOTIFICATION_KIND_COLUMN in values:
        data = values.get(NOTIFICATION_DATA_COLUMN) or {}
        if isinstance(data, dict):
            values[NOTIFICATION_DATA_COLUMN] = {
                NOTIFICATION_KIND_COLUMN: values[NOTIFICATION_KIND_COLUMN],
                **data,
            }
    return values


# --- Public API ---


def _resource_info(resolved: ResolvedResource) -> AdminResourceInfo:
    on_create = resolved.writable_on_create
    on_update = resolved.writable_on_update
    searchable = set(resolved.searchable)
    filterable = set(resolved.filterable)
    sortable = set(resolved.sortable)
    ops = resolved.resource.operations
    columns = [
        AdminColumn(
            name=name,
            data_type=info.data_type,
            udt_name=info.udt_name,
            nullable=info.nullable,
            has_default=info.has_default,
            max_length=info.max_length,
            primary_key=name in resolved.primary_key,
            read_only=resolved.is_read_only(name),
            writable_on_create=OP_CREATE in ops and name in on_create,
            writable_on_update=OP_UPDATE in ops and name in on_update,
            searchable=name in searchable,
            filterable=name in filterable,
            sortable=name in sortable,
        )
        for name, info in resolved.columns.items()
        if name in resolved.visible
    ]
    return AdminResourceInfo(
        name=resolved.name,
        table=resolved.table,
        primary_key=list(resolved.primary_key),
        operations=sorted(ops),
        delete_mode=resolved.delete_mode,
        default_sort=resolved.default_sort,
        columns=columns,
    )


async def list_resources() -> AdminResourceList:
    return AdminResourceList(
        items=[_resource_info(r) for r in await admin_schema_cache.resolve_all()]
    )


async def list_records(
    name: str,
    *,
    limit: int | None,
    offset: int,
    q: str | None,
    sort: str | None,
    raw_filters: Mapping[str, str],
) -> AdminRecordPage:
    resolved = await _resolve(name)
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        with translate_db_errors():
            rows, total = await admin_repository.list_rows(
                conn,
                table=resolved.table,
                columns=resolved.visible,
                filters=_filters(resolved, raw_filters),
                search_columns=resolved.searchable,
                search_term=_search_term(q),
                order=_order(resolved, sort),
                limit=page_limit,
                offset=offset,
            )
    return AdminRecordPage(
        items=[_record(r) for r in rows], total=total, limit=page_limit, offset=offset
    )


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def export_csv(
    name: str, *, q: str | None, sort: str | None, raw_filters: Mapping[str, str]
) -> tuple[str, str]:
    """Return ``(resource_name, csv_text)`` for the filtered list (capped)."""
    resolved = await _resolve(name)
    columns = resolved.visible
    async with get_pool().acquire() as conn:
        with translate_db_errors():
            rows = await admin_repository.export_rows(
                conn,
                table=resolved.table,
                columns=columns,
                filters=_filters(resolved, raw_filters),
                search_columns=resolved.searchable,
                search_term=_search_term(q),
                order=_order(resolved, sort),
                limit=EXPORT_MAX_ROWS,
            )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_cell(row[c]) for c in columns])
    return resolved.name, buffer.getvalue()


async def get_record(name: str, record_id: str) -> AdminRecord:
    resolved = await _resolve(name)
    key = _parse_key(resolved, record_id)
    async with get_pool().acquire() as conn:
        row = await admin_repository.get_row(
            conn, table=resolved.table, columns=resolved.visible, key=key
        )
    if row is None:
        raise not_found(ERR_RECORD_NOT_FOUND, MSG_RECORD_NOT_FOUND)
    return _record(row)


async def create_record(name: str, body: Mapping[str, Any]) -> AdminRecord:
    resolved = await _resolve(name)
    _require_op(resolved, OP_CREATE)
    values = _prepare_create(resolved, _coerce_body(resolved, body, resolved.writable_on_create))
    async with get_pool().acquire() as conn:
        with translate_db_errors():
            row = await admin_repository.insert_row(
                conn, table=resolved.table, values=values, returning=resolved.visible
            )
    return _record(row)


async def update_record(name: str, record_id: str, body: Mapping[str, Any]) -> AdminRecord:
    resolved = await _resolve(name)
    _require_op(resolved, OP_UPDATE)
    key = _parse_key(resolved, record_id)
    values = _coerce_body(resolved, body, resolved.writable_on_update)
    if not values:
        raise bad_request(ERR_EMPTY_BODY, MSG_EMPTY_BODY)
    async with get_pool().acquire() as conn:
        with translate_db_errors():
            row = await admin_repository.update_row(
                conn,
                table=resolved.table,
                values=values,
                touch_columns=resolved.touch_columns,
                key=key,
                returning=resolved.visible,
            )
    if row is None:
        raise not_found(ERR_RECORD_NOT_FOUND, MSG_RECORD_NOT_FOUND)
    return _record(row)


async def delete_record(name: str, record_id: str) -> None:
    resolved = await _resolve(name)
    _require_op(resolved, OP_DELETE)
    key = _parse_key(resolved, record_id)
    async with get_pool().acquire() as conn:
        with translate_db_errors():
            if resolved.delete_mode == DELETE_MODE_SOFT:
                found = await admin_repository.soft_delete_row(
                    conn,
                    table=resolved.table,
                    flag_column=COLUMN_IS_ACTIVE,
                    touch_columns=resolved.touch_columns,
                    key=key,
                )
            else:
                found = await admin_repository.delete_row(conn, table=resolved.table, key=key)
    if not found:
        raise not_found(ERR_RECORD_NOT_FOUND, MSG_RECORD_NOT_FOUND)
