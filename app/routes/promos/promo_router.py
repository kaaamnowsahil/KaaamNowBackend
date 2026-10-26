"""Promo codes: business validates at posting and lists its vouchers; worker redeems one from
the wallet for the next payout."""

from __future__ import annotations

from fastapi import APIRouter

from app.constants.application.application_common import (
    SWAGGER_ROLE_BUSINESS,
    SWAGGER_ROLE_WORKER,
    swagger_summary,
)
from app.constants.application.application_constants import ROLE_BUSINESS
from app.constants.promos.promo_route_strings import (
    BUSINESS_ROUTE_PREFIX,
    OPENAPI_TAG_PROMOS,
    PATH_PROMO_CODES,
    PATH_PROMO_REDEEM,
    PATH_PROMO_VALIDATE,
    WORKER_ROUTE_PREFIX,
)
from app.dependencies import RequireEarningsRead, RequireEarningsWrite, RequireShiftsRead
from app.schemas.promos.promo_schemas import (
    PromoCodeRequest,
    PromoList,
    PromoView,
    WorkerPromoStatus,
)
from app.services.promos import promo_service

business_router = APIRouter(prefix=BUSINESS_ROUTE_PREFIX, tags=[OPENAPI_TAG_PROMOS])
worker_router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_PROMOS])


@business_router.post(
    PATH_PROMO_VALIDATE,
    response_model=PromoView,
    summary=swagger_summary("Check a promo code", SWAGGER_ROLE_BUSINESS),
)
async def validate_business_code(body: PromoCodeRequest, user: RequireShiftsRead) -> PromoView:
    return await promo_service.validate(user, body.code, ROLE_BUSINESS)


@business_router.get(
    PATH_PROMO_CODES,
    response_model=PromoList,
    summary=swagger_summary("My free-fees vouchers", SWAGGER_ROLE_BUSINESS),
)
async def list_vouchers(user: RequireShiftsRead) -> PromoList:
    return await promo_service.list_business_vouchers(user)


@worker_router.get(
    PATH_PROMO_CODES,
    response_model=WorkerPromoStatus,
    summary=swagger_summary("Promo waiting for next payout", SWAGGER_ROLE_WORKER),
)
async def worker_status(user: RequireEarningsRead) -> WorkerPromoStatus:
    return await promo_service.worker_status(user)


@worker_router.post(
    PATH_PROMO_REDEEM,
    response_model=WorkerPromoStatus,
    summary=swagger_summary("Apply promo to next payout", SWAGGER_ROLE_WORKER),
)
async def redeem(body: PromoCodeRequest, user: RequireEarningsWrite) -> WorkerPromoStatus:
    return await promo_service.redeem_worker(user, body.code)
