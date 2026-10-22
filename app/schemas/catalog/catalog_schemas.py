"""Reference data shown in pickers."""

from __future__ import annotations

from pydantic import BaseModel


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
