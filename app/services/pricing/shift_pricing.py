"""Shift pricing on the shared engine: rates snapshotted from ``platform_fee_policies``."""

from __future__ import annotations

from decimal import Decimal

from app.services.pricing.pricing_engine import Charge, PricingRates, compute_charge
from app.services.promos.promo_rules import Promo, discounter
from app.utils.money import BusinessCharge, FeeRates


def pricing_rates(rates: FeeRates) -> PricingRates:
    return PricingRates(
        commission_pct=rates.business_pct,
        tax_pct=rates.tax_pct,
        tax_base=rates.tax_base,
        gateway_pct=rates.gateway_pct,
    )


def shift_charge(
    worker_subtotal_minor: int,
    rates: FeeRates,
    promo: Promo | None = None,
    *,
    scale: Decimal = Decimal(1),
) -> Charge:
    return compute_charge(
        worker_subtotal_minor, pricing_rates(rates), discounter(promo, scale=scale)
    )


def as_business_charge(charge: Charge) -> BusinessCharge:
    """Invoice amounts: fees net of the coupon (the discount is stored next to them)."""
    return BusinessCharge(
        worker_subtotal_minor=charge.base_amount_minor,
        commission_minor=charge.net_commission_minor,
        gateway_fee_minor=charge.net_gateway_minor,
        tax_minor=charge.tax_minor,
    )
