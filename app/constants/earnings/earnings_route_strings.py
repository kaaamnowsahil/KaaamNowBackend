"""Worker earnings, payout accounts and withdrawals route constants."""

from __future__ import annotations

from typing import Final

from app.constants.application.application_common import API_V1, SEGMENT_WORKER

WORKER_ROUTE_PREFIX: Final[str] = f"{API_V1}{SEGMENT_WORKER}"
OPENAPI_TAG_EARNINGS: Final[str] = "earnings"

PATH_EARNINGS: Final[str] = "/earnings"
PATH_EARNINGS_ENTRIES: Final[str] = "/earnings/entries"
PATH_PAYOUT_ACCOUNTS: Final[str] = "/payout-accounts"
PATH_PAYOUT_ACCOUNT: Final[str] = "/payout-accounts/{account_id}"
PATH_PAYOUT_ACCOUNT_DEFAULT: Final[str] = "/payout-accounts/{account_id}/default"
PATH_WITHDRAWALS: Final[str] = "/withdrawals"
PATH_WITHDRAWAL: Final[str] = "/withdrawals/{withdrawal_id}"

UPI_ID_PATTERN: Final[str] = r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9.\-]{1,63}$"
IFSC_PATTERN: Final[str] = r"^[A-Z]{4}0[A-Z0-9]{6}$"
BANK_ACCOUNT_PATTERN: Final[str] = r"^\d{9,18}$"
MAX_PAYOUT_ACCOUNTS: Final[int] = 5
RECENT_ENTRIES_LIMIT: Final[int] = 5
WITHDRAWAL_SWEEP_BATCH: Final[int] = 100

ENTRY_SHIFT_EARNING: Final[str] = "shift_earning"
ENTRY_WITHDRAWAL: Final[str] = "withdrawal"
ENTRY_WITHDRAWAL_REVERSAL: Final[str] = "withdrawal_reversal"

WD_PROCESSING: Final[str] = "processing"
WD_PAID: Final[str] = "paid"
WD_FAILED: Final[str] = "failed"

MSG_PAYOUT_ACCOUNT_NOT_FOUND: Final[str] = "Payout account not found."
MSG_PAYOUT_ACCOUNT_FIELDS: Final[str] = "Fill in the details for the selected payout method."
MSG_PAYOUT_ACCOUNT_LIMIT: Final[str] = "You can save up to 5 payout accounts."
MSG_WITHDRAWAL_NOT_FOUND: Final[str] = "Withdrawal not found."
MSG_WITHDRAWAL_MIN: Final[str] = "Amount is below the minimum withdrawal."
MSG_INSUFFICIENT_BALANCE: Final[str] = "Amount is more than your available balance."
MSG_IDEMPOTENCY_MISMATCH: Final[str] = "This idempotency key was used for a different withdrawal."
