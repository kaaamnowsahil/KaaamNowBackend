"""asyncpg reads for reference data."""

from __future__ import annotations

import asyncpg

from app.repositories.catalog.catalog_queries import (
    GET_ACTIVE_FEE_POLICY,
    GET_BUSINESS_TYPE_BY_SLUG,
    GET_BUSINESS_TYPE_IDS_BY_SLUGS,
    GET_CATEGORY_BY_SLUG,
    GET_CATEGORY_IDS_BY_SLUGS,
)


async def get_business_type_by_slug(conn: asyncpg.Connection, slug: str) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_BUSINESS_TYPE_BY_SLUG, slug)


async def get_business_type_ids_by_slugs(
    conn: asyncpg.Connection, slugs: list[str]
) -> list[asyncpg.Record]:
    return await conn.fetch(GET_BUSINESS_TYPE_IDS_BY_SLUGS, slugs)


async def get_category_by_slug(conn: asyncpg.Connection, slug: str) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_CATEGORY_BY_SLUG, slug)


async def get_category_ids_by_slugs(
    conn: asyncpg.Connection, slugs: list[str]
) -> list[asyncpg.Record]:
    return await conn.fetch(GET_CATEGORY_IDS_BY_SLUGS, slugs)


async def get_active_fee_policy(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_ACTIVE_FEE_POLICY)
