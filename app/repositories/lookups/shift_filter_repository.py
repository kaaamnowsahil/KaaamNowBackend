"""asyncpg access for shift filter options."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.repositories.lookups import shift_filter_queries


async def list_options(
    conn: asyncpg.Connection, *, include_inactive: bool
) -> list[asyncpg.Record]:
    return await conn.fetch(shift_filter_queries.LIST_OPTIONS, include_inactive)


async def get_option(conn: asyncpg.Connection, option_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(shift_filter_queries.GET_OPTION, option_id)


async def insert_option(
    conn: asyncpg.Connection,
    *,
    filter_type: str,
    slug: str,
    label: str,
    min_value: float | None,
    max_value: float | None,
    sort_order: int,
    is_active: bool,
) -> asyncpg.Record:
    return await conn.fetchrow(
        shift_filter_queries.INSERT_OPTION,
        filter_type,
        slug,
        label,
        min_value,
        max_value,
        sort_order,
        is_active,
    )


async def update_option(
    conn: asyncpg.Connection, option_id: UUID, values: dict[str, object]
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        shift_filter_queries.UPDATE_OPTION,
        option_id,
        values["filter_type"],
        values["slug"],
        values["label"],
        values["min_value"],
        values["max_value"],
        values["sort_order"],
        values["is_active"],
    )


async def deactivate_option(conn: asyncpg.Connection, option_id: UUID) -> bool:
    return await conn.fetchval(shift_filter_queries.DEACTIVATE_OPTION, option_id) is not None
