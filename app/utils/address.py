"""Derive the short locality label shown on cards from a free-text address."""

from __future__ import annotations

LOCALITY_MAX_LENGTH = 160
_IGNORED_TAIL_PARTS = frozenset({"india"})


def derive_locality(address_text: str) -> str:
    """'12 MG Road, Indiranagar, Bengaluru 560038' -> 'Indiranagar'."""
    parts = [p.strip() for p in address_text.split(",") if p.strip()]
    while len(parts) > 1 and (parts[-1].isdigit() or parts[-1].lower() in _IGNORED_TAIL_PARTS):
        parts.pop()
    if not parts:
        return ""
    locality = parts[-2] if len(parts) >= 3 else parts[-1]
    return locality[:LOCALITY_MAX_LENGTH]


def resolve_locality(address_text: str | None, locality: str | None) -> str | None:
    if locality is not None or address_text is None:
        return locality
    return derive_locality(address_text)
