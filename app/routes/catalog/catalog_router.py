"""Reference data for pickers: rating chips, payment methods, fee."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from app.constants.application.application_common import SWAGGER_ROLE_PUBLIC, swagger_summary
from app.constants.catalog.catalog_route_strings import (
    CATALOG_ROUTE_PREFIX,
    OPENAPI_TAG_CATALOG,
    PATH_CANCELLATION_POLICY,
    PATH_FEE_POLICY,
    PATH_PAYMENT_METHODS,
    PATH_RATING_TAGS,
)
from app.schemas.catalog.catalog_schemas import (
    CancellationPolicy,
    FeePolicy,
    PaymentMethod,
    RatingTags,
)
from app.services.catalog import catalog_service

router = APIRouter(prefix=CATALOG_ROUTE_PREFIX, tags=[OPENAPI_TAG_CATALOG])


@router.get(
    PATH_RATING_TAGS,
    response_model=list[RatingTags],
    summary=swagger_summary("Rating tag chips", SWAGGER_ROLE_PUBLIC),
)
async def rating_tags(
    direction: Literal["business_to_worker", "worker_to_business"] | None = None,
) -> list[RatingTags]:
    return catalog_service.list_rating_tags(direction)


@router.get(
    PATH_PAYMENT_METHODS,
    response_model=list[PaymentMethod],
    summary=swagger_summary("Payment methods", SWAGGER_ROLE_PUBLIC),
)
async def payment_methods() -> list[PaymentMethod]:
    return catalog_service.list_payment_methods()


@router.get(
    PATH_FEE_POLICY,
    response_model=FeePolicy,
    summary=swagger_summary("Active platform fee", SWAGGER_ROLE_PUBLIC),
)
async def fee_policy() -> FeePolicy:
    return await catalog_service.get_fee_policy()


@router.get(
    PATH_CANCELLATION_POLICY,
    response_model=CancellationPolicy,
    summary=swagger_summary("Active cancellation fee tiers", SWAGGER_ROLE_PUBLIC),
)
async def cancellation_policy() -> CancellationPolicy:
    return await catalog_service.get_cancellation_policy()
