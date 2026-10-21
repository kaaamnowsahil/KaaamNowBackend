"""Admin dashboard: resource metadata, generic record pages, metrics overview."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

AdminRecord = dict[str, Any]


class AdminColumn(BaseModel):
    name: str
    data_type: str = Field(examples=["character varying"])
    udt_name: str = Field(examples=["varchar"])
    nullable: bool
    has_default: bool
    max_length: int | None = None
    primary_key: bool
    read_only: bool
    writable_on_create: bool
    writable_on_update: bool
    searchable: bool
    filterable: bool
    sortable: bool


class AdminResourceInfo(BaseModel):
    name: str = Field(examples=["work_categories"])
    table: str
    primary_key: list[str]
    operations: list[str] = Field(description="Allowed writes (read is always allowed).")
    delete_mode: str | None = Field(description="soft | hard | null when delete is disabled.")
    default_sort: str
    columns: list[AdminColumn]


class AdminResourceList(BaseModel):
    items: list[AdminResourceInfo]


class AdminRecordPage(BaseModel):
    items: list[AdminRecord]
    total: int
    limit: int
    offset: int


class AdminCount(BaseModel):
    key: str
    count: int


class AdminMetricsOverview(BaseModel):
    users_total: int
    users_active: int
    workers_total: int
    workers_by_verification: list[AdminCount]
    businesses_total: int
    businesses_by_verification: list[AdminCount]
    shifts_total: int
    shifts_by_status: list[AdminCount]
    open_support_tickets: int
    pending_withdrawals: int
    pending_withdrawals_minor: int
    total_paid_out_minor: int = Field(description="Sum of paid withdrawals (paise).")
    invoiced_paid_minor: int = Field(description="Sum of paid invoice totals (paise).")
    platform_fees_minor: int = Field(description="Platform fee revenue on paid invoices.")
    payments_succeeded_minor: int
    currency: str = "INR"
