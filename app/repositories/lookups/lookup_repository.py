"""asyncpg access for lookup tables."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.lookups import lookup_queries


async def list_items(
    conn: asyncpg.Connection, table: str, *, include_inactive: bool, q: str | None
) -> list[asyncpg.Record]:
    return await conn.fetch(lookup_queries.list_items(table), include_inactive, q)


async def get_item(conn: asyncpg.Connection, table: str, item_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(lookup_queries.get_item(table), item_id)


async def insert_item(
    conn: asyncpg.Connection,
    table: str,
    *,
    slug: str,
    name: str,
    icon: str,
    sort_order: int,
    is_active: bool,
) -> asyncpg.Record:
    return await conn.fetchrow(
        lookup_queries.insert_item(table), slug, name, icon, sort_order, is_active
    )


async def update_item(
    conn: asyncpg.Connection,
    table: str,
    item_id: UUID,
    *,
    slug: str | None,
    name: str | None,
    icon: str | None,
    sort_order: int | None,
    is_active: bool | None,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        lookup_queries.update_item(table), item_id, slug, name, icon, sort_order, is_active
    )


async def deactivate_item(conn: asyncpg.Connection, table: str, item_id: UUID) -> bool:
    return await conn.fetchval(lookup_queries.deactivate_item(table), item_id) is not None
