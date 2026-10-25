"""Figma "Terms & Conditions", "FAQ & Help", "Contact support"."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Audience = Literal["worker", "business"]
SupportTopic = Literal["general", "check_in", "payment", "payout", "shift", "account"]


class ContentSection(BaseModel):
    id: str
    title: str
    body: str


class ContentPage(BaseModel):
    slug: str
    audience: str
    title: str
    body_markdown: str
    sections: list[ContentSection] = Field(
        default_factory=list, description="body_markdown split on '## ' headings."
    )
    effective_date: date
    updated_at: datetime


class FaqItem(BaseModel):
    id: UUID
    slug: str | None = None
    question: str
    answer: str


class FaqList(BaseModel):
    items: list[FaqItem]
    support_email: str = Field(description="Comma-separated; prefer support_emails.")
    support_emails: list[str]


ContentAudience = Literal["worker", "business", "all"]


class AdminFaq(BaseModel):
    id: UUID
    audience: str
    slug: str | None
    question: str
    answer: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminFaqCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: ContentAudience = "all"
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    question: str = Field(min_length=3, max_length=300)
    answer: str = Field(min_length=1, max_length=8000)
    sort_order: int = 0
    is_active: bool = True


class AdminFaqUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: ContentAudience | None = None
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    question: str | None = Field(default=None, min_length=3, max_length=300)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    sort_order: int | None = None
    is_active: bool | None = None


class AdminTerms(BaseModel):
    id: UUID
    audience: str
    title: str
    body_markdown: str
    effective_date: date
    created_at: datetime
    updated_at: datetime


class AdminTermsUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    body_markdown: str = Field(min_length=1, max_length=100_000)
    effective_date: date


class SupportTicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: SupportTopic = "general"
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=5, max_length=4000)
    shift_id: UUID | None = None


class SupportTicketResponse(BaseModel):
    id: UUID
    topic: str
    subject: str
    status: str
    created_at: datetime
    support_email: str
    support_emails: list[str]
