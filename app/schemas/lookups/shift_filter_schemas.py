"""Worker shift filter options managed by admins."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.lookups.lookup_route_strings import SLUG_MAX_LENGTH, SLUG_PATTERN


class ShiftFilterType(StrEnum):
    DISTANCE = "distance"
    MINIMUM_PAY = "minimum_pay"
    SHIFT_LENGTH = "shift_length"


class ShiftFilterOptionValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter_type: ShiftFilterType
    slug: str = Field(max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    min_value: float | None = Field(default=None, ge=0)
    max_value: float | None = Field(default=None, gt=0)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_filter_values(self) -> ShiftFilterOptionValues:
        if self.filter_type == ShiftFilterType.DISTANCE:
            if self.max_value is None:
                raise ValueError("Distance options require max_value in kilometers.")
            if self.min_value is not None:
                raise ValueError("Distance options only use max_value.")
        elif self.filter_type == ShiftFilterType.MINIMUM_PAY:
            if self.min_value is None or self.min_value <= 0:
                raise ValueError("Minimum pay options require a positive min_value.")
            if self.max_value is not None:
                raise ValueError("Minimum pay options only use min_value.")
        elif self.min_value is None:
            raise ValueError("Shift length options require min_value in hours.")
        if (
            self.filter_type == ShiftFilterType.SHIFT_LENGTH
            and self.max_value is not None
            and self.min_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError("Shift length max_value must be at least min_value.")
        return self


class ShiftFilterOptionCreate(ShiftFilterOptionValues):
    pass


class ShiftFilterOptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter_type: ShiftFilterType | None = None
    slug: str | None = Field(default=None, max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    min_value: float | None = Field(default=None, ge=0)
    max_value: float | None = Field(default=None, gt=0)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ShiftFilterOption(ShiftFilterOptionValues):
    id: UUID
    created_at: datetime
    updated_at: datetime
