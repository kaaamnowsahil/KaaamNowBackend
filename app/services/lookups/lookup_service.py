"""Slug-based lookup tables (work categories, business types): public reads, admin writes."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.lookups.lookup_route_strings import (
    ERR_LOOKUP_EMPTY_UPDATE,
    ERR_SUFFIX_NOT_FOUND,
    ERR_SUFFIX_SLUG_TAKEN,
    MSG_LOOKUP_EMPTY_UPDATE,
    MSG_LOOKUP_NOT_FOUND,
    MSG_LOOKUP_SLUG_TAKEN,
    LookupResource,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request, conflict, not_found
from app.repositories.lookups import lookup_repository
from app.schemas.lookups.lookup_schemas import LookupCreate, LookupItem, LookupUpdate


def _to_model(row: asyncpg.Record) -> LookupItem:
    return LookupItem.model_validate(dict(row))


def _not_found(resource: LookupResource) -> ApiError:
    return not_found(
        resource.error_prefix + ERR_SUFFIX_NOT_FOUND,
        MSG_LOOKUP_NOT_FOUND.format(label=resource.label),
    )


def _slug_taken(resource: LookupResource) -> ApiError:
    return conflict(
        resource.error_prefix + ERR_SUFFIX_SLUG_TAKEN,
        MSG_LOOKUP_SLUG_TAKEN.format(label=resource.label),
    )


def _clean(value: str | None) -> str | None:
    return value.strip() if value is not None else None


async def list_items(
    resource: LookupResource, *, include_inactive: bool, q: str | None
) -> list[LookupItem]:
    async with get_pool().acquire() as conn:
        rows = await lookup_repository.list_items(
            conn, resource.table, include_inactive=include_inactive, q=q or None
        )
    return [_to_model(r) for r in rows]


async def get_item(
    resource: LookupResource, item_id: UUID, *, include_inactive: bool
) -> LookupItem:
    async with get_pool().acquire() as conn:
        row = await lookup_repository.get_item(conn, resource.table, item_id)
    if row is None or not (include_inactive or row["is_active"]):
        raise _not_found(resource)
    return _to_model(row)


async def create_item(resource: LookupResource, body: LookupCreate) -> LookupItem:
    async with get_pool().acquire() as conn:
        try:
            row = await lookup_repository.insert_item(
                conn,
                resource.table,
                slug=body.slug,
                name=body.name.strip(),
                icon=body.icon.strip(),
                sort_order=body.sort_order,
                is_active=body.is_active,
            )
        except asyncpg.UniqueViolationError as exc:
            raise _slug_taken(resource) from exc
    return _to_model(row)


async def update_item(resource: LookupResource, item_id: UUID, body: LookupUpdate) -> LookupItem:
    if not body.model_fields_set:
        raise bad_request(ERR_LOOKUP_EMPTY_UPDATE, MSG_LOOKUP_EMPTY_UPDATE)
    async with get_pool().acquire() as conn:
        try:
            row = await lookup_repository.update_item(
                conn,
                resource.table,
                item_id,
                slug=body.slug,
                name=_clean(body.name),
                icon=_clean(body.icon),
                sort_order=body.sort_order,
                is_active=body.is_active,
            )
        except asyncpg.UniqueViolationError as exc:
            raise _slug_taken(resource) from exc
    if row is None:
        raise _not_found(resource)
    return _to_model(row)


async def delete_item(resource: LookupResource, item_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        found = await lookup_repository.deactivate_item(conn, resource.table, item_id)
    if not found:
        raise _not_found(resource)
