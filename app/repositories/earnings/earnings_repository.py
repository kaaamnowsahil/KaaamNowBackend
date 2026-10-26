"""asyncpg persistence for the earnings ledger, payout accounts and withdrawals."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from app.repositories.earnings.earnings_queries import (
    BALANCE,
    CLEAR_DEFAULT_ACCOUNT,
    COUNT_ACTIVE_ACCOUNTS,
    DEACTIVATE_PAYOUT_ACCOUNT,
    EARNINGS_SUMMARY,
    FINISH_WITHDRAWAL,
    GET_PAYOUT_ACCOUNT,
    GET_WITHDRAWAL,
    GET_WITHDRAWAL_BY_KEY,
    IN_FLIGHT_WITHDRAWALS,
    INSERT_LEDGER_ENTRY,
    INSERT_PAYOUT_ACCOUNT,
    INSERT_SHIFT_EARNINGS_FOR_INVOICE,
    INSERT_WITHDRAWAL,
    INSERT_WORKER_COMMISSIONS_FOR_INVOICE,
    LIST_IN_FLIGHT_WITHDRAWALS,
    LIST_LEDGER,
    LIST_PAYOUT_ACCOUNTS,
    LIST_WITHDRAWALS,
    LOCK_WITHDRAWAL,
    LOCK_WORKER_LEDGER,
    PENDING_PAY,
    SET_DEFAULT_ACCOUNT,
    SET_WITHDRAWAL_PROCESSING,
    UPDATE_PAYOUT_ACCOUNT,
)


async def credit_invoice_earnings(
    conn: asyncpg.Connection, invoice_id: UUID
) -> list[asyncpg.Record]:
    """Idempotent: re-settling the same invoice inserts nothing."""
    return await conn.fetch(INSERT_SHIFT_EARNINGS_FOR_INVOICE, invoice_id)


async def debit_invoice_commissions(
    conn: asyncpg.Connection, invoice_id: UUID
) -> list[asyncpg.Record]:
    """Idempotent: one commission debit per assignment."""
    return await conn.fetch(INSERT_WORKER_COMMISSIONS_FOR_INVOICE, invoice_id)


async def insert_ledger_entry(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    entry_type: str,
    amount_minor: int,
    currency: str,
    withdrawal_id: UUID,
    description: str,
) -> None:
    await conn.execute(
        INSERT_LEDGER_ENTRY,
        worker_profile_id,
        entry_type,
        amount_minor,
        currency,
        withdrawal_id,
        description,
    )


async def balance(conn: asyncpg.Connection, worker_profile_id: UUID) -> int:
    return int(await conn.fetchval(BALANCE, worker_profile_id))


async def summary(
    conn: asyncpg.Connection, worker_profile_id: UUID, month_start: datetime
) -> asyncpg.Record:
    return await conn.fetchrow(EARNINGS_SUMMARY, worker_profile_id, month_start)


async def pending_pay(conn: asyncpg.Connection, worker_profile_id: UUID) -> int:
    return int(await conn.fetchval(PENDING_PAY, worker_profile_id))


async def in_flight_withdrawals(conn: asyncpg.Connection, worker_profile_id: UUID) -> int:
    return int(await conn.fetchval(IN_FLIGHT_WITHDRAWALS, worker_profile_id))


async def list_ledger(
    conn: asyncpg.Connection, worker_profile_id: UUID, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_LEDGER, worker_profile_id, limit, offset)


async def list_payout_accounts(
    conn: asyncpg.Connection, worker_profile_id: UUID
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_PAYOUT_ACCOUNTS, worker_profile_id)


async def get_payout_account(
    conn: asyncpg.Connection, account_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_PAYOUT_ACCOUNT, account_id, worker_profile_id)


async def update_payout_account(
    conn: asyncpg.Connection,
    account_id: UUID,
    worker_profile_id: UUID,
    *,
    upi_id: str | None,
    paytm_phone: str | None,
    bank_account_number: str | None,
    bank_ifsc: str | None,
    account_holder_name: str | None,
    details_changed: bool,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        UPDATE_PAYOUT_ACCOUNT,
        account_id,
        worker_profile_id,
        upi_id,
        paytm_phone,
        bank_account_number,
        bank_ifsc,
        account_holder_name,
        details_changed,
    )


async def count_active_accounts(conn: asyncpg.Connection, worker_profile_id: UUID) -> int:
    return int(await conn.fetchval(COUNT_ACTIVE_ACCOUNTS, worker_profile_id))


async def clear_default_account(conn: asyncpg.Connection, worker_profile_id: UUID) -> None:
    await conn.execute(CLEAR_DEFAULT_ACCOUNT, worker_profile_id)


async def insert_payout_account(
    conn: asyncpg.Connection,
    worker_profile_id: UUID,
    *,
    account_type: str,
    upi_id: str | None,
    paytm_phone: str | None,
    bank_account_number: str | None,
    bank_ifsc: str | None,
    account_holder_name: str,
    is_default: bool,
) -> asyncpg.Record:
    return await conn.fetchrow(
        INSERT_PAYOUT_ACCOUNT,
        worker_profile_id,
        account_type,
        upi_id,
        paytm_phone,
        bank_account_number,
        bank_ifsc,
        account_holder_name,
        is_default,
    )


async def set_default_account(
    conn: asyncpg.Connection, account_id: UUID, worker_profile_id: UUID
) -> bool:
    return (await conn.execute(SET_DEFAULT_ACCOUNT, account_id, worker_profile_id)).endswith(" 1")


async def deactivate_payout_account(
    conn: asyncpg.Connection, account_id: UUID, worker_profile_id: UUID
) -> bool:
    result = await conn.execute(DEACTIVATE_PAYOUT_ACCOUNT, account_id, worker_profile_id)
    return result.endswith(" 1")


async def lock_worker_ledger(conn: asyncpg.Connection, worker_profile_id: UUID) -> None:
    """Serialize balance-changing writes for one worker inside the current transaction."""
    await conn.execute(LOCK_WORKER_LEDGER, str(worker_profile_id))


async def get_withdrawal(
    conn: asyncpg.Connection, withdrawal_id: UUID, worker_profile_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WITHDRAWAL, withdrawal_id, worker_profile_id)


async def get_withdrawal_by_key(
    conn: asyncpg.Connection, worker_profile_id: UUID, idempotency_key: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(GET_WITHDRAWAL_BY_KEY, worker_profile_id, idempotency_key)


async def list_withdrawals(
    conn: asyncpg.Connection, worker_profile_id: UUID, limit: int, offset: int
) -> list[asyncpg.Record]:
    return await conn.fetch(LIST_WITHDRAWALS, worker_profile_id, limit, offset)


async def insert_withdrawal(
    conn: asyncpg.Connection,
    *,
    worker_profile_id: UUID,
    payout_account_id: UUID,
    amount_minor: int,
    currency: str,
    reference: str,
    idempotency_key: str,
    provider: str,
) -> UUID:
    return await conn.fetchval(
        INSERT_WITHDRAWAL,
        worker_profile_id,
        payout_account_id,
        amount_minor,
        currency,
        reference,
        idempotency_key,
        provider,
    )


async def set_withdrawal_processing(
    conn: asyncpg.Connection, withdrawal_id: UUID, provider_payout_id: str
) -> None:
    await conn.execute(SET_WITHDRAWAL_PROCESSING, withdrawal_id, provider_payout_id)


async def list_in_flight_withdrawal_ids(conn: asyncpg.Connection, limit: int) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(LIST_IN_FLIGHT_WITHDRAWALS, limit)]


async def lock_withdrawal(conn: asyncpg.Connection, withdrawal_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(LOCK_WITHDRAWAL, withdrawal_id)


async def finish_withdrawal(
    conn: asyncpg.Connection,
    withdrawal_id: UUID,
    *,
    status: str,
    failure_reason: str | None,
    now: datetime,
) -> None:
    await conn.execute(FINISH_WITHDRAWAL, withdrawal_id, status, failure_reason, now)
