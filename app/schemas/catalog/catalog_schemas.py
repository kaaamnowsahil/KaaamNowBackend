"""Reference data shown in pickers."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class WorkCategory(BaseModel):
    id: UUID
    slug: str
    name: str
    icon: str


class BusinessType(BaseModel):
    id: UUID
    slug: str
    name: str
    icon: str


class Language(BaseModel):
    code: str
    english_name: str
    native_name: str


class RatingTags(BaseModel):
    direction: str
    tags: list[str]


class PaymentMethod(BaseModel):
    code: str
    label: str


class FeePolicy(BaseModel):
    version: int
    percentage: float
