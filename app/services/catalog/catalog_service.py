"""Reference data + shared lookups used by other services."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.catalog.catalog_route_strings import (
    MSG_BUSINESS_TYPE_UNKNOWN,
    MSG_CATEGORY_UNKNOWN,
    MSG_NO_ACTIVE_CANCELLATION_POLICY,
    MSG_NO_ACTIVE_FEE_POLICY,
    PAYMENT_METHODS,
    RATING_TAGS,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request
from app.repositories.cancellations import cancellation_repository
from app.repositories.catalog import catalog_repository
from app.schemas.admin.admin_schemas import AdminSearchRadius
from app.schemas.catalog.catalog_schemas import (
    CancellationPolicy,
    CancellationTier,
    FeePolicy,
    PaymentMethod,
    RatingTags,
)
from app.utils.money import FeeRates


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
    return FeePolicy(
        version=row["version"],
        percentage=float(row["percentage"]),
        worker_percentage=float(row["worker_percentage"]),
        gateway_percentage=float(row["gateway_percentage"]),
    )


async def get_cancellation_policy() -> CancellationPolicy:
    async with get_pool().acquire() as conn:
        policy = await cancellation_repository.get_active_policy(conn)
        if policy is None:
            raise ApiError(500, "cancellation_policy_missing", MSG_NO_ACTIVE_CANCELLATION_POLICY)
        tiers = await cancellation_repository.list_policy_tiers(conn, policy["version"])
    return CancellationPolicy(
        version=policy["version"],
        strike_window_days=policy["strike_window_days"],
        strikes_to_limit=float(policy["strikes_to_limit"]),
        limit_days=policy["limit_days"],
        strikes_to_ban=float(policy["strikes_to_ban"]),
        voucher_valid_days=policy["voucher_valid_days"],
        unfilled_cutoff_hours=load_settings().apply_closes_hours_before,
        tiers=[
            CancellationTier(
                party=t["party"],
                event=t["event"],
                hours_from=float(t["hours_from"]),
                hours_to=None if t["hours_to"] is None else float(t["hours_to"]),
                flat_fee_minor=t["flat_fee_minor"],
                booking_pct=float(t["booking_pct"]),
                fee_cap_minor=t["fee_cap_minor"],
                worker_share_pct=float(t["worker_share_pct"]),
                strike_weight=float(t["strike_weight"]),
                business_voucher=t["business_voucher"],
            )
            for t in tiers
        ],
    )


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


async def resolve_business_type_ids(conn: asyncpg.Connection, slugs: list[str]) -> list[UUID]:
    """Resolve slugs in the caller's order (first one becomes the primary type)."""
    ordered = list(dict.fromkeys(slugs))
    rows = await catalog_repository.get_business_type_ids_by_slugs(conn, ordered)
    found = {r["slug"]: r["id"] for r in rows}
    missing = [s for s in ordered if s not in found]
    if missing:
        raise bad_request("business_type_unknown", MSG_BUSINESS_TYPE_UNKNOWN, {"slugs": missing})
    return [found[s] for s in ordered]


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


def policy_rates(policy: asyncpg.Record) -> FeeRates:
    return FeeRates(
        business_pct=Decimal(policy["percentage"]),
        worker_pct=Decimal(policy["worker_percentage"]),
        gateway_pct=Decimal(policy["gateway_percentage"]),
        tax_pct=Decimal(policy["tax_percentage"]),
        tax_base=policy["tax_base"],
        tax_label=policy["tax_label"],
    )


def shift_rates(shift: asyncpg.Record, fallback: FeeRates | None = None) -> FeeRates | None:
    """Rates snapshotted at publish; ``fallback`` (the active policy) for unpublished drafts."""
    if shift["fee_percentage"] is None:
        return fallback
    return FeeRates(
        business_pct=Decimal(shift["fee_percentage"]),
        worker_pct=Decimal(shift["worker_fee_percentage"] or 0),
        gateway_pct=Decimal(shift["gateway_fee_percentage"] or 0),
        tax_pct=Decimal(shift["tax_percentage"] or 0),
        tax_base=shift["tax_base"] or "subtotal",
        tax_label=shift["tax_label"] or "Tax",
    )


async def active_rates(conn: asyncpg.Connection) -> FeeRates:
    return policy_rates(await require_active_fee_policy(conn))


@dataclass(frozen=True, slots=True)
class SearchRadii:
    live_initial_km: float
    live_max_km: float
    scheduled_notify_km: float
    feed_km: float
    worker_max_shift_km: float


async def search_radii(conn: asyncpg.Connection) -> SearchRadii:
    """Admin-set search distances; the env values apply until an admin saves them."""
    return _radii_from_row(await catalog_repository.get_search_radius_settings(conn))


async def effective_search_radii() -> AdminSearchRadius:
    async with get_pool().acquire() as conn:
        row = await catalog_repository.get_search_radius_settings(conn)
    radii = _radii_from_row(row)
    return AdminSearchRadius(
        live_initial_radius_km=radii.live_initial_km,
        live_max_radius_km=radii.live_max_km,
        scheduled_notify_radius_km=radii.scheduled_notify_km,
        feed_radius_km=radii.feed_km,
        worker_max_shift_distance_km=radii.worker_max_shift_km,
        source="default" if row is None else "admin",
    )


def _radii_from_row(row: asyncpg.Record | None) -> SearchRadii:
    if row is None:
        settings = load_settings()
        return SearchRadii(
            live_initial_km=settings.live_initial_radius_km,
            live_max_km=settings.live_max_radius_km,
            scheduled_notify_km=settings.scheduled_notify_radius_km,
            feed_km=settings.feed_radius_km,
            worker_max_shift_km=settings.worker_max_shift_distance_km,
        )
    return SearchRadii(
        live_initial_km=float(row["live_initial_radius_km"]),
        live_max_km=float(row["live_max_radius_km"]),
        scheduled_notify_km=float(row["scheduled_notify_radius_km"]),
        feed_km=float(row["feed_radius_km"]),
        worker_max_shift_km=float(row["worker_max_shift_distance_km"]),
    )
