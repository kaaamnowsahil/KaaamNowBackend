"""Money tables must not be writable through the generic admin CRUD."""

from __future__ import annotations

import pytest

from app.constants.admin.admin_route_strings import READ_ONLY_OPS
from app.services.admin.admin_resources import find_resource


@pytest.mark.parametrize(
    "name",
    ["payments", "withdrawals", "earning_ledger_entries", "payment_webhook_events"],
)
def test_money_resources_are_read_only(name: str) -> None:
    resource = find_resource(name)
    assert resource is not None
    assert resource.operations == READ_ONLY_OPS
