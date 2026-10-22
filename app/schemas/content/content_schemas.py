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
