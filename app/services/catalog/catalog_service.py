"""Reference data + shared lookups used by other services."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.constants.catalog.catalog_route_strings import (
    MSG_BUSINESS_TYPE_UNKNOWN,
    MSG_CATEGORY_UNKNOWN,
    MSG_NO_ACTIVE_FEE_POLICY,
    PAYMENT_METHODS,
    RATING_TAGS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request
from app.repositories.catalog import catalog_repository
from app.schemas.catalog.catalog_schemas import (
    BusinessType,
    FeePolicy,
    Language,
    PaymentMethod,
    RatingTags,
    WorkCategory,
)


async def list_work_categories() -> list[WorkCategory]:
    async with get_pool().acquire() as conn:
        rows = await catalog_repository.list_work_categories(conn)
    return [WorkCategory.model_validate(dict(r)) for r in rows]


async def list_business_types() -> list[BusinessType]:
    async with get_pool().acquire() as conn:
        rows = await catalog_repository.list_business_types(conn)
    return [BusinessType.model_validate(dict(r)) for r in rows]


async def list_languages() -> list[Language]:
    async with get_pool().acquire() as conn:
        rows = await catalog_repository.list_languages(conn)
    return [Language.model_validate(dict(r)) for r in rows]


def list_rating_tags(direction: str | None) -> list[RatingTags]:
    return [
        RatingTags(direction=d, tags=list(tags))
        for d, tags in RATING_TAGS.items()
        if direction is None or d == direction
    ]


def list_payment_methods() -> list[PaymentMethod]:
    return [PaymentMethod(code=code, label=label) for code, label in PAYMENT_METHODS]


async def get_fee_policy() -> FeePolicy:
    async with get_pool().acquire() as conn:
        row = await require_active_fee_policy(conn)
    return FeePolicy(version=row["version"], percentage=float(row["percentage"]))


async def resolve_category_id(conn: asyncpg.Connection, slug: str) -> UUID:
    row = await catalog_repository.get_category_by_slug(conn, slug)
    if row is None:
        raise bad_request("category_unknown", MSG_CATEGORY_UNKNOWN, {"slug": slug})
    return row["id"]


async def resolve_business_type_id(conn: asyncpg.Connection, slug: str) -> UUID:
    row = await catalog_repository.get_business_type_by_slug(conn, slug)
    if row is None:
        raise bad_request("business_type_unknown", MSG_BUSINESS_TYPE_UNKNOWN, {"slug": slug})
    return row["id"]


async def resolve_category_ids(conn: asyncpg.Connection, slugs: list[str]) -> list[UUID]:
    unique = sorted(set(slugs))
    rows = await catalog_repository.get_category_ids_by_slugs(conn, unique)
    found = {r["slug"]: r["id"] for r in rows}
    missing = [s for s in unique if s not in found]
    if missing:
        raise bad_request("category_unknown", MSG_CATEGORY_UNKNOWN, {"slugs": missing})
    return [found[s] for s in unique]


async def require_active_fee_policy(conn: asyncpg.Connection) -> asyncpg.Record:
    row = await catalog_repository.get_active_fee_policy(conn)
    if row is None:
        raise ApiError(500, "fee_policy_missing", MSG_NO_ACTIVE_FEE_POLICY)
    return row
