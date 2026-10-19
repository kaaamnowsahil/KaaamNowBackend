"""Worker earnings, payout accounts and withdrawals."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.constants.application.application_common import SWAGGER_ROLE_WORKER, swagger_summary
from app.constants.earnings.earnings_route_strings import (
    OPENAPI_TAG_EARNINGS,
    PATH_EARNINGS,
    PATH_EARNINGS_ENTRIES,
    PATH_PAYOUT_ACCOUNT,
    PATH_PAYOUT_ACCOUNT_DEFAULT,
    PATH_PAYOUT_ACCOUNTS,
    PATH_WITHDRAWAL,
    PATH_WITHDRAWALS,
    WORKER_ROUTE_PREFIX,
)
from app.dependencies import RequireEarningsRead, RequireEarningsWrite
from app.schemas.earnings.earnings_schemas import (
    EarningsSummary,
    LedgerPage,
    PayoutAccountCreate,
    PayoutAccountResponse,
    WithdrawalCreate,
    WithdrawalPage,
    WithdrawalResponse,
)
from app.services.earnings import earnings_service

router = APIRouter(prefix=WORKER_ROUTE_PREFIX, tags=[OPENAPI_TAG_EARNINGS])


@router.get(
    PATH_EARNINGS,
    response_model=EarningsSummary,
    summary=swagger_summary("Earnings summary", SWAGGER_ROLE_WORKER),
)
async def summary(user: RequireEarningsRead) -> EarningsSummary:
    return await earnings_service.get_summary(user)


@router.get(
    PATH_EARNINGS_ENTRIES,
    response_model=LedgerPage,
    summary=swagger_summary("Earnings history", SWAGGER_ROLE_WORKER),
)
async def entries(
    user: RequireEarningsRead,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> LedgerPage:
    return await earnings_service.list_entries(user, limit, offset)


@router.get(
    PATH_PAYOUT_ACCOUNTS,
    response_model=list[PayoutAccountResponse],
    summary=swagger_summary("Payout accounts", SWAGGER_ROLE_WORKER),
)
async def list_accounts(user: RequireEarningsRead) -> list[PayoutAccountResponse]:
    return await earnings_service.list_payout_accounts(user)


@router.post(
    PATH_PAYOUT_ACCOUNTS,
    response_model=PayoutAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Add payout account", SWAGGER_ROLE_WORKER),
)
async def add_account(
    body: PayoutAccountCreate, user: RequireEarningsWrite
) -> PayoutAccountResponse:
    return await earnings_service.add_payout_account(user, body)


@router.put(
    PATH_PAYOUT_ACCOUNT_DEFAULT,
    response_model=PayoutAccountResponse,
    summary=swagger_summary("Make default payout account", SWAGGER_ROLE_WORKER),
)
async def set_default(account_id: UUID, user: RequireEarningsWrite) -> PayoutAccountResponse:
    return await earnings_service.set_default_account(user, account_id)


@router.delete(
    PATH_PAYOUT_ACCOUNT,
    status_code=status.HTTP_204_NO_CONTENT,
    summary=swagger_summary("Remove payout account", SWAGGER_ROLE_WORKER),
)
async def remove_account(account_id: UUID, user: RequireEarningsWrite) -> None:
    await earnings_service.remove_payout_account(user, account_id)


@router.post(
    PATH_WITHDRAWALS,
    response_model=WithdrawalResponse,
    status_code=status.HTTP_201_CREATED,
    summary=swagger_summary("Withdraw earnings", SWAGGER_ROLE_WORKER),
)
async def withdraw(body: WithdrawalCreate, user: RequireEarningsWrite) -> WithdrawalResponse:
    return await earnings_service.create_withdrawal(user, body)


@router.get(
    PATH_WITHDRAWALS,
    response_model=WithdrawalPage,
    summary=swagger_summary("Withdrawals", SWAGGER_ROLE_WORKER),
)
async def list_withdrawals(
    user: RequireEarningsRead,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> WithdrawalPage:
    return await earnings_service.list_withdrawals(user, limit, offset)


@router.get(
    PATH_WITHDRAWAL,
    response_model=WithdrawalResponse,
    summary=swagger_summary("Withdrawal detail", SWAGGER_ROLE_WORKER),
)
async def get_withdrawal(withdrawal_id: UUID, user: RequireEarningsRead) -> WithdrawalResponse:
    return await earnings_service.get_withdrawal(user, withdrawal_id)
