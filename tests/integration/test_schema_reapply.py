"""The schema is re-applied on every boot, so it must accept every row the app can write."""

from __future__ import annotations

import pytest

from app.db.bootstrap import bootstrap_database
from app.db.pool import get_pool

pytestmark = pytest.mark.asyncio(loop_scope="session")

LEDGER_ENTRIES = [
    ("shift_earning", 1000),
    ("withdrawal", -500),
    ("withdrawal_reversal", 500),
    ("commission", -40),
    ("cancellation_fee", -14900),
    ("cancellation_compensation", 800),
    ("adjustment", -200),
    ("promo_credit", 40),
    ("fee_waiver", 14900),
]


async def test_reboot_keeps_working_with_every_ledger_entry_type(
    app_client, make_worker, db
) -> None:  # type: ignore[no-untyped-def]
    worker = await make_worker("Ledger Reboot")
    await db.executemany(
        "INSERT INTO earning_ledger_entries (worker_profile_id, entry_type, amount_minor, "
        "currency) VALUES ($1, $2, $3, 'INR')",
        [(worker.profile_id, entry_type, amount) for entry_type, amount in LEDGER_ENTRIES],
    )
    try:
        await bootstrap_database(get_pool())
        await bootstrap_database(get_pool())
    finally:
        await db.execute(
            "DELETE FROM earning_ledger_entries WHERE worker_profile_id = $1", worker.profile_id
        )
