"""Admin "Live Work Pricing & Charges": active rates, versioned saves, per-field audit."""

from __future__ import annotations

from decimal import Decimal

import asyncpg

from app.config.settings import load_settings
from app.db.pool import get_pool
from app.exceptions.api_errors import ApiError, bad_request
from app.pagination import clamp_page_limit
from app.repositories.live_work import live_work_repository
from app.repositories.users import user_repository
from app.schemas.live_work.live_work_schemas import (
    LivePriceBreakdown,
    LivePricingAuditItem,
    LivePricingAuditPage,
    LivePricingSettingsUpdate,
    LivePricingSettingsView,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.live_work.live_pricing import (
    TAX_BASE_BASE_AMOUNT,
    TAX_BASE_COMMISSION,
    InvalidPercentage,
    LiveCharge,
    LiveRates,
    booking_charge,
    extension_rate,
    parse_percentage,
)
from app.utils.clock import utc_now
from app.utils.request_context import get_request_id

EXAMPLE_RATE_MINOR = 50_000
EXAMPLE_MINUTES = 120

_AUDITED_FIELDS = (
    "commission_pct",
    "tax_pct",
    "tax_label",
    "tax_base",
    "extension_surcharge_pct",
    "search_timeout_minutes",
    "max_search_rounds",
    "retry_choice_minutes",
    "boost_options_minor",
)
# Search + retry rules: (min, max) of each admin value.
SEARCH_LIMITS = {
    "search_timeout_minutes": (5, 120),
    "max_search_rounds": (1, 5),
    "retry_choice_minutes": (2, 60),
}
BOOST_LIMITS_MINOR = (100, 100_000)
MAX_BOOST_OPTIONS = 5
# Only used if no version exists yet (the seed creates v1 with the same column defaults).
_FIRST_SAVE_DEFAULTS = {
    "search_timeout_minutes": 30,
    "max_search_rounds": 3,
    "retry_choice_minutes": 10,
    "boost_options_minor": [1000, 2000, 3000],
}


def tax_base_description(tax_base: str, tax_label: str) -> str:
    if tax_base == TAX_BASE_BASE_AMOUNT:
        return f"{tax_label} is charged on the base amount only (rate × duration)."
    if tax_base == TAX_BASE_COMMISSION:
        return f"{tax_label} is charged on the platform charge only."
    return f"{tax_label} is charged on the base amount plus the platform charge."


def rates_from_row(row: asyncpg.Record) -> LiveRates:
    return LiveRates(
        version=row["version"] if "version" in row else row["settings_version"],
        commission_pct=Decimal(row["commission_pct"]),
        tax_pct=Decimal(row["tax_pct"]),
        tax_label=row["tax_label"],
        tax_base=row["tax_base"],
        extension_surcharge_pct=Decimal(row["extension_surcharge_pct"]),
    )


async def active_rates(conn: asyncpg.Connection) -> LiveRates:
    row = await live_work_repository.get_active_settings(conn)
    if row is None:
        raise ApiError(
            503,
            "live_pricing_not_configured",
            "Live Work pricing is not configured. Please contact support.",
        )
    return rates_from_row(row)


def breakdown(
    *,
    currency: str,
    hourly_rate_minor: int,
    reserved_minutes: int,
    rates: LiveRates,
    charge: LiveCharge,
    promo_code: str | None = None,
    pricing_mode: str = "hourly",
    task_price_minor: int | None = None,
    workers_required: int = 1,
) -> LivePriceBreakdown:
    return LivePriceBreakdown(
        currency=currency,
        settings_version=rates.version,
        pricing_mode=pricing_mode,  # type: ignore[arg-type]
        hourly_rate_minor=hourly_rate_minor,
        reserved_minutes=reserved_minutes,
        task_price_minor=task_price_minor,
        base_amount_minor=charge.base_amount_minor,
        commission_pct=float(rates.commission_pct),
        commission_minor=charge.commission_minor,
        promo_code=promo_code if charge.discount_minor else None,
        promo_discount_minor=charge.discount_minor,
        tax_label=rates.tax_label,
        tax_pct=float(rates.tax_pct),
        tax_base=rates.tax_base,  # type: ignore[arg-type]
        tax_base_description=tax_base_description(rates.tax_base, rates.tax_label),
        taxable_minor=charge.taxable_minor,
        tax_minor=charge.tax_minor,
        total_minor=charge.total_minor,
        worker_commission_minor=charge.worker_commission_minor,
        worker_net_minor=charge.worker_net_minor,
        extension_surcharge_pct=float(rates.extension_surcharge_pct),
        extension_rate_minor=extension_rate(hourly_rate_minor, rates.extension_surcharge_pct),
        workers_required=workers_required,
        max_workers=load_settings().live_max_workers,
        booking_total_minor=charge.total_minor * workers_required,
    )


def _settings_view(row: asyncpg.Record, currency: str) -> LivePricingSettingsView:
    rates = rates_from_row(row)
    return LivePricingSettingsView(
        version=row["version"],
        commission_pct=float(rates.commission_pct),
        tax_pct=float(rates.tax_pct),
        tax_label=rates.tax_label,
        tax_base=rates.tax_base,  # type: ignore[arg-type]
        tax_base_description=tax_base_description(rates.tax_base, rates.tax_label),
        extension_surcharge_pct=float(rates.extension_surcharge_pct),
        search_timeout_minutes=row["search_timeout_minutes"],
        max_search_rounds=row["max_search_rounds"],
        retry_choice_minutes=row["retry_choice_minutes"],
        boost_options_minor=list(row["boost_options_minor"]),
        effective_from=row["effective_from"],
        changed_by_label=row["changed_by_label"],
        notes=row["notes"],
        example=breakdown(
            currency=currency,
            hourly_rate_minor=EXAMPLE_RATE_MINOR,
            reserved_minutes=EXAMPLE_MINUTES,
            rates=rates,
            charge=booking_charge(EXAMPLE_RATE_MINOR, EXAMPLE_MINUTES, rates),
        ),
    )


async def get_settings() -> LivePricingSettingsView:
    async with get_pool().acquire() as conn:
        row = await live_work_repository.get_active_settings(conn)
        if row is None:
            await active_rates(conn)
    return _settings_view(row, load_settings().default_currency)


def _parse_search_rules(
    body: LivePricingSettingsUpdate, current: asyncpg.Record | None, errors: dict[str, str]
) -> dict[str, int | list[int]]:
    """Omitted values keep the current version's (or the column default on first save)."""
    values: dict[str, int | list[int]] = {}
    for field, (low, high) in SEARCH_LIMITS.items():
        value = getattr(body, field)
        if value is None:
            value = current[field] if current is not None else None
        elif not low <= value <= high:
            errors[field] = f"Enter a number from {low} to {high}."
        if value is not None:
            values[field] = value
    options = body.boost_options_minor
    if options is None:
        if current is not None:
            values["boost_options_minor"] = list(current["boost_options_minor"])
    else:
        low, high = BOOST_LIMITS_MINOR
        if not 1 <= len(options) <= MAX_BOOST_OPTIONS:
            errors["boost_options_minor"] = f"Give 1 to {MAX_BOOST_OPTIONS} amounts."
        elif len(set(options)) != len(options):
            errors["boost_options_minor"] = "Each amount can appear only once."
        elif any(o % 100 or not low <= o <= high for o in options):
            errors["boost_options_minor"] = (
                f"Each amount must be whole rupees from ₹{low // 100} to ₹{high // 100:,}."
            )
        values["boost_options_minor"] = sorted(options)
    return values


def _parse(
    body: LivePricingSettingsUpdate, current: asyncpg.Record | None
) -> dict[str, Decimal | str | int | list[int]]:
    values: dict[str, Decimal | str | int | list[int]] = {}
    errors: dict[str, str] = {}
    values.update(_parse_search_rules(body, current, errors))
    for field in ("commission_pct", "tax_pct", "extension_surcharge_pct"):
        try:
            values[field] = parse_percentage(getattr(body, field))
        except InvalidPercentage as exc:
            errors[field] = str(exc)
    if not body.tax_label:
        errors["tax_label"] = "Enter a label, e.g. Tax."
    if errors:
        raise bad_request(
            "validation_error", "Please correct the highlighted fields.", {"fields": errors}
        )
    values["tax_label"] = body.tax_label
    values["tax_base"] = body.tax_base
    return values


def _display(value: Decimal | str | int | list[int]) -> str:
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


async def update_settings(
    admin: AuthenticatedUser, body: LivePricingSettingsUpdate
) -> LivePricingSettingsView:
    now = utc_now()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await live_work_repository.lock_settings(conn)
            current = await live_work_repository.get_active_settings(conn)
            values = _parse(body, current)
            values = {**_FIRST_SAVE_DEFAULTS, **values}
            changed = [
                field
                for field in _AUDITED_FIELDS
                if current is None or _display(current[field]) != _display(values[field])
            ]
            if not changed:
                return _settings_view(current, load_settings().default_currency)
            admin_row = await user_repository.get_user(conn, admin.user_id)
            label = (
                (admin_row["full_name"] or admin_row["email"] or admin_row["phone"] or "")
                if admin_row
                else ""
            )
            row = await live_work_repository.insert_settings(
                conn,
                commission_pct=values["commission_pct"],  # type: ignore[arg-type]
                tax_pct=values["tax_pct"],  # type: ignore[arg-type]
                tax_label=values["tax_label"],  # type: ignore[arg-type]
                tax_base=values["tax_base"],  # type: ignore[arg-type]
                extension_surcharge_pct=values["extension_surcharge_pct"],  # type: ignore[arg-type]
                now=now,
                changed_by_user_id=admin.user_id,
                changed_by_label=label,
                notes=body.notes,
                search_timeout_minutes=values["search_timeout_minutes"],  # type: ignore[arg-type]
                max_search_rounds=values["max_search_rounds"],  # type: ignore[arg-type]
                retry_choice_minutes=values["retry_choice_minutes"],  # type: ignore[arg-type]
                boost_options_minor=values["boost_options_minor"],  # type: ignore[arg-type]
            )
            for field in changed:
                await live_work_repository.insert_audit(
                    conn,
                    settings_version=row["version"],
                    field=field,
                    old_value=_display(current[field]) if current is not None else None,
                    new_value=_display(values[field]),
                    changed_by_user_id=admin.user_id,
                    changed_by_label=label,
                    request_id=get_request_id(),
                    now=now,
                )
            return _settings_view(row, load_settings().default_currency)


async def list_audit(limit: int | None, offset: int) -> LivePricingAuditPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        rows = await live_work_repository.list_audit(conn, page_limit, offset)
        total = await live_work_repository.count_audit(conn)
    return LivePricingAuditPage(
        items=[LivePricingAuditItem.model_validate(dict(r)) for r in rows],
        total=total,
        limit=page_limit,
        offset=offset,
    )
