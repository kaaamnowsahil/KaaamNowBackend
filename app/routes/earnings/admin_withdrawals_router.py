"""Admin: settle manual withdrawals (pay outside the app, then mark paid or reject)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from app.config.settings import load_settings
from app.constants.application.application_common import SWAGGER_ROLE_ADMIN, swagger_summary
from app.constants.earnings.earnings_route_strings import (
    PATH_ADMIN_WITHDRAWAL_PAID,
    PATH_ADMIN_WITHDRAWAL_REJECT,
)
from app.constants.support.support_route_strings import (
    ADMIN_SUPPORT_ROUTE_PREFIX,
    OPENAPI_TAG_ADMIN_SUPPORT,
)
from app.dependencies import RequireVerificationWrite
from app.schemas.earnings.earnings_schemas import ManualPayoutReject, ManualPayoutView
from app.services.earnings import manual_payout_service

router = APIRouter(prefix=ADMIN_SUPPORT_ROUTE_PREFIX, tags=[OPENAPI_TAG_ADMIN_SUPPORT])

UtrField = Annotated[str | None, Form(max_length=40, pattern=r"^\s*[A-Za-z0-9]*\s*$")]


@router.post(
    PATH_ADMIN_WITHDRAWAL_PAID,
    response_model=ManualPayoutView,
    summary=swagger_summary(
        "Mark a manual withdrawal paid with the payment screenshot", SWAGGER_ROLE_ADMIN
    ),
)
async def mark_withdrawal_paid(
    withdrawal_id: UUID,
    admin: RequireVerificationWrite,
    proof: UploadFile = File(...),
    utr: UtrField = None,
) -> ManualPayoutView:
    data = await proof.read(load_settings().max_photo_bytes + 1)
    return await manual_payout_service.mark_paid(
        admin,
        withdrawal_id,
        content_type=proof.content_type or "",
        proof=data,
        utr=(utr or "").strip() or None,
    )


@router.post(
    PATH_ADMIN_WITHDRAWAL_REJECT,
    response_model=ManualPayoutView,
    summary=swagger_summary(
        "Reject a manual withdrawal and return the money to the worker", SWAGGER_ROLE_ADMIN
    ),
)
async def reject_withdrawal(
    withdrawal_id: UUID, body: ManualPayoutReject, admin: RequireVerificationWrite
) -> ManualPayoutView:
    return await manual_payout_service.reject(admin, withdrawal_id, body.reason)
