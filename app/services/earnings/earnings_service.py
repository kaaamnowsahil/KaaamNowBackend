"""Worker earnings ledger, payout accounts and withdrawals.

Balance = SUM(ledger). A withdrawal debits immediately (under a per-worker advisory lock);
a failed payout is credited back with a ``withdrawal_reversal`` entry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from app.config.settings import load_settings
from app.constants.earnings.earnings_route_strings import (
    ENTRY_WITHDRAWAL,
    MAX_PAYOUT_ACCOUNTS,
    MSG_IDEMPOTENCY_MISMATCH,
    MSG_INSUFFICIENT_BALANCE,
    MSG_PAYOUT_ACCOUNT_FIELDS,
    MSG_PAYOUT_ACCOUNT_LIMIT,
    MSG_PAYOUT_ACCOUNT_NOT_FOUND,
    MSG_WITHDRAWAL_MIN,
    MSG_WITHDRAWAL_NOT_FOUND,
    RECENT_ENTRIES_LIMIT,
)
from app.db.pool import get_pool
from app.exceptions.api_errors import bad_request, conflict, not_found
from app.pagination import clamp_page_limit
from app.repositories.earnings import earnings_repository
from app.schemas.earnings.earnings_schemas import (
    EarningsSummary,
    LedgerEntry,
    LedgerPage,
    PayoutAccountCreate,
    PayoutAccountResponse,
    WithdrawalCreate,
    WithdrawalPage,
    WithdrawalResponse,
)
from app.security.authenticated_user import AuthenticatedUser
from app.services.earnings.sources.payout_provider_factory import get_payout_provider
from app.services.profiles.profile_lookup import require_worker_profile
from app.utils.clock import utc_now
from app.utils.references import WITHDRAWAL_REFERENCE_PREFIX, new_reference

_REQUIRED_FIELDS = {
    "upi": ("upi_id",),
    "paytm": ("paytm_phone",),
    "bank": ("bank_account_number", "bank_ifsc"),
}


def payout_display(row: asyncpg.Record) -> str:
    kind = row["account_type"]
    if kind == "upi":
        return f"UPI · {row['upi_id']}"
    if kind == "paytm":
        return f"Paytm · {row['paytm_phone']}"
    return f"Bank · ••••{(row['bank_account_number'] or '')[-4:]}"


def _account_response(row: asyncpg.Record) -> PayoutAccountResponse:
    number = row["bank_account_number"]
    return PayoutAccountResponse(
        id=row["id"],
        account_type=row["account_type"],
        display=payout_display(row),
        upi_id=row["upi_id"],
        paytm_phone=row["paytm_phone"],
        bank_account_last4=number[-4:] if number else None,
        bank_ifsc=row["bank_ifsc"],
        account_holder_name=row["account_holder_name"],
        is_default=row["is_default"],
        created_at=row["created_at"],
    )


def _withdrawal_response(row: asyncpg.Record) -> WithdrawalResponse:
    return WithdrawalResponse(
        id=row["id"],
        amount_minor=row["amount_minor"],
        currency=row["currency"],
        status=row["status"],
        reference=row["reference"],
        payout_account_id=row["payout_account_id"],
        payout_display=payout_display(row),
        failure_reason=row["failure_reason"],
        initiated_at=row["initiated_at"],
        completed_at=row["completed_at"],
    )


def _month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def get_summary(user: AuthenticatedUser) -> EarningsSummary:
    settings = load_settings()
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        totals = await earnings_repository.summary(conn, worker["id"], _month_start(utc_now()))
        pending = await earnings_repository.pending_pay(conn, worker["id"])
        in_flight = await earnings_repository.in_flight_withdrawals(conn, worker["id"])
        recent = await earnings_repository.list_ledger(conn, worker["id"], RECENT_ENTRIES_LIMIT, 0)
    return EarningsSummary(
        currency=settings.default_currency,
        available_minor=totals["available_minor"],
        pending_minor=pending,
        in_flight_withdrawals_minor=in_flight,
        lifetime_minor=totals["lifetime_minor"],
        this_month_minor=totals["this_month_minor"],
        completed_shifts=worker["completed_shift_count"],
        min_withdrawal_minor=settings.min_withdrawal_minor,
        recent=[LedgerEntry.model_validate(dict(r)) for r in recent],
    )


async def list_entries(user: AuthenticatedUser, limit: int | None, offset: int) -> LedgerPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        rows = await earnings_repository.list_ledger(conn, worker["id"], page_limit, offset)
    return LedgerPage(
        items=[LedgerEntry.model_validate(dict(r)) for r in rows], limit=page_limit, offset=offset
    )


async def list_payout_accounts(user: AuthenticatedUser) -> list[PayoutAccountResponse]:
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        rows = await earnings_repository.list_payout_accounts(conn, worker["id"])
    return [_account_response(r) for r in rows]


async def add_payout_account(
    user: AuthenticatedUser, body: PayoutAccountCreate
) -> PayoutAccountResponse:
    data = body.model_dump()
    if any(not data.get(field) for field in _REQUIRED_FIELDS[body.account_type]):
        raise bad_request("payout_account_fields", MSG_PAYOUT_ACCOUNT_FIELDS)
    keep = set(_REQUIRED_FIELDS[body.account_type])
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            await earnings_repository.lock_worker_ledger(conn, worker["id"])
            count = await earnings_repository.count_active_accounts(conn, worker["id"])
            if count >= MAX_PAYOUT_ACCOUNTS:
                raise conflict("payout_account_limit", MSG_PAYOUT_ACCOUNT_LIMIT)
            make_default = body.make_default or count == 0
            if make_default:
                await earnings_repository.clear_default_account(conn, worker["id"])
            row = await earnings_repository.insert_payout_account(
                conn,
                worker["id"],
                account_type=body.account_type,
                upi_id=data["upi_id"] if "upi_id" in keep else None,
                paytm_phone=data["paytm_phone"] if "paytm_phone" in keep else None,
                bank_account_number=(
                    data["bank_account_number"] if "bank_account_number" in keep else None
                ),
                bank_ifsc=data["bank_ifsc"] if "bank_ifsc" in keep else None,
                account_holder_name=body.account_holder_name or worker["full_name"],
                is_default=make_default,
            )
    return _account_response(row)


async def set_default_account(user: AuthenticatedUser, account_id: UUID) -> PayoutAccountResponse:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            if await earnings_repository.get_payout_account(conn, account_id, worker["id"]) is None:
                raise not_found("payout_account_not_found", MSG_PAYOUT_ACCOUNT_NOT_FOUND)
            await earnings_repository.clear_default_account(conn, worker["id"])
            await earnings_repository.set_default_account(conn, account_id, worker["id"])
            row = await earnings_repository.get_payout_account(conn, account_id, worker["id"])
    return _account_response(row)


async def remove_payout_account(user: AuthenticatedUser, account_id: UUID) -> None:
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        if not await earnings_repository.deactivate_payout_account(conn, account_id, worker["id"]):
            raise not_found("payout_account_not_found", MSG_PAYOUT_ACCOUNT_NOT_FOUND)


async def create_withdrawal(user: AuthenticatedUser, body: WithdrawalCreate) -> WithdrawalResponse:
    """Idempotent on ``idempotency_key``: a retried request returns the original withdrawal."""
    settings = load_settings()
    provider = get_payout_provider()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            worker = await require_worker_profile(conn, user.user_id)
            await earnings_repository.lock_worker_ledger(conn, worker["id"])
            existing = await earnings_repository.get_withdrawal_by_key(
                conn, worker["id"], body.idempotency_key
            )
            if existing is not None:
                if (
                    existing["amount_minor"] != body.amount_minor
                    or existing["payout_account_id"] != body.payout_account_id
                ):
                    raise conflict("idempotency_mismatch", MSG_IDEMPOTENCY_MISMATCH)
                return _withdrawal_response(existing)
            if body.amount_minor < settings.min_withdrawal_minor:
                raise bad_request(
                    "withdrawal_below_min",
                    MSG_WITHDRAWAL_MIN,
                    {"min_withdrawal_minor": settings.min_withdrawal_minor},
                )
            account = await earnings_repository.get_payout_account(
                conn, body.payout_account_id, worker["id"]
            )
            if account is None:
                raise not_found("payout_account_not_found", MSG_PAYOUT_ACCOUNT_NOT_FOUND)
            balance = await earnings_repository.balance(conn, worker["id"])
            if body.amount_minor > balance:
                raise conflict(
                    "insufficient_balance", MSG_INSUFFICIENT_BALANCE, {"available_minor": balance}
                )
            reference = new_reference(WITHDRAWAL_REFERENCE_PREFIX)
            withdrawal_id = await earnings_repository.insert_withdrawal(
                conn,
                worker_profile_id=worker["id"],
                payout_account_id=account["id"],
                amount_minor=body.amount_minor,
                currency=settings.default_currency,
                reference=reference,
                idempotency_key=body.idempotency_key,
                provider=provider.name,
            )
            await earnings_repository.insert_ledger_entry(
                conn,
                worker_profile_id=worker["id"],
                entry_type=ENTRY_WITHDRAWAL,
                amount_minor=-body.amount_minor,
                currency=settings.default_currency,
                withdrawal_id=withdrawal_id,
                description=f"Withdrawal {reference} to {payout_display(account)}",
            )
            payout_id = await provider.create_payout(
                reference=reference,
                amount_minor=body.amount_minor,
                account={
                    k: account[k]
                    for k in (
                        "account_type",
                        "upi_id",
                        "paytm_phone",
                        "bank_account_number",
                        "bank_ifsc",
                    )
                },
            )
            await earnings_repository.set_withdrawal_processing(conn, withdrawal_id, payout_id)
            row = await earnings_repository.get_withdrawal(conn, withdrawal_id, worker["id"])
    return _withdrawal_response(row)


async def list_withdrawals(
    user: AuthenticatedUser, limit: int | None, offset: int
) -> WithdrawalPage:
    page_limit = clamp_page_limit(limit)
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        rows = await earnings_repository.list_withdrawals(conn, worker["id"], page_limit, offset)
    return WithdrawalPage(
        items=[_withdrawal_response(r) for r in rows], limit=page_limit, offset=offset
    )


async def get_withdrawal(user: AuthenticatedUser, withdrawal_id: UUID) -> WithdrawalResponse:
    async with get_pool().acquire() as conn:
        worker = await require_worker_profile(conn, user.user_id)
        row = await earnings_repository.get_withdrawal(conn, withdrawal_id, worker["id"])
    if row is None:
        raise not_found("withdrawal_not_found", MSG_WITHDRAWAL_NOT_FOUND)
    return _withdrawal_response(row)
