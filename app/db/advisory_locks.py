"""Postgres advisory lock keys shared across the API process."""

from __future__ import annotations

from typing import Final

# Serialises concurrent boots (several API replicas starting at once).
BOOTSTRAP_ADVISORY_LOCK_KEY: Final[int] = 7_420_001
# Held for a whole sweep; schema bootstrap also takes it so DDL never races a running sweep.
SWEEP_ADVISORY_LOCK_KEY: Final[int] = 7_420_002
