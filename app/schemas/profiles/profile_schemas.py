"""Business / worker profile schemas (Figma "Business profile", "Worker profile", "Go online")."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.profiles.profile_route_strings import MSG_COORDINATES_PAIR
from app.schemas.users.user_schemas import MeResponse, ThemePreference

VerificationStatus = Literal["pending", "verified", "rejected"]
ProfileType = Literal["account", "business", "worker"]

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
WORKER_MIN_AGE = 18
WORKER_MAX_AGE = 70

Latitude = Field(ge=-90, le=90)
Longitude = Field(ge=-180, le=180)
OptionalLatitude = Field(default=None, ge=-90, le=90)
OptionalLongitude = Field(default=None, ge=-180, le=180)


class _CoordinatesPair(BaseModel):
    @model_validator(mode="after")
    def _both_or_neither(self):  # type: ignore[no-untyped-def]
        if (self.latitude is None) != (self.longitude is None):  # type: ignore[attr-defined]
            raise ValueError(MSG_COORDINATES_PAIR)
        return self


class _AccountPreferences(BaseModel):
    """Account settings any role may change through PATCH /me/profile."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    language_code: str | None = Field(default=None, min_length=2, max_length=8)
    theme_preference: ThemePreference | None = None


class BusinessProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    business_name: str
    category_slug: str | None = None
    category_name: str | None = None
    logo_url: str | None = None
    address_text: str
    locality: str
    latitude: float | None = None
    longitude: float | None = None
    verification_status: VerificationStatus
    verification_note: str | None = None
    verified_at: datetime | None = None
    rating_avg: float
    rating_count: int
    owner_name: str
    contact_name: str
    email: str | None = None
    business_type_slug: str | None = None
    business_type_name: str | None = None
    phone: str


class BusinessProfilePatch(_CoordinatesPair, _AccountPreferences):
    """``full_name`` is the owner's name; ``email`` is the business contact email."""

    model_config = ConfigDict(extra="forbid")

    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    business_type_slug: str | None = Field(default=None, max_length=64)
    category_slug: str | None = Field(default=None, max_length=64)
    address_text: str | None = Field(default=None, max_length=500)
    locality: str | None = Field(default=None, max_length=160)
    latitude: float | None = OptionalLatitude
    longitude: float | None = OptionalLongitude


class WorkerProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str | None = None
    age: int | None = None
    photo_url: str | None = None
    phone: str
    address_text: str
    locality: str
    latitude: float | None = None
    longitude: float | None = None
    category_slugs: list[str]
    verification_status: VerificationStatus
    verification_note: str | None = None
    verified_at: datetime | None = None
    is_available: bool
    availability_changed_at: datetime | None = None
    rating_avg: float
    rating_count: int
    completed_shift_count: int


class WorkerProfilePatch(_CoordinatesPair, _AccountPreferences):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    age: int | None = Field(default=None, ge=WORKER_MIN_AGE, le=WORKER_MAX_AGE)
    address_text: str | None = Field(default=None, max_length=500)
    locality: str | None = Field(default=None, max_length=160)
    latitude: float | None = OptionalLatitude
    longitude: float | None = OptionalLongitude
    category_slugs: list[str] | None = Field(default=None, max_length=20)


class AccountProfilePatch(_AccountPreferences):
    """Profile fields for an account without a Business or Worker profile."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)


# The role resolved from the access token decides which member is enforced; the union only
# documents the accepted shapes.
ProfilePatch = BusinessProfilePatch | WorkerProfilePatch | AccountProfilePatch


class MyProfileResponse(BaseModel):
    """Exactly one of ``business`` / ``worker`` is set, matching ``profile_type``."""

    profile_type: ProfileType
    account: MeResponse
    business: BusinessProfileResponse | None = None
    worker: WorkerProfileResponse | None = None


class WorkerPublicProfile(BaseModel):
    """What a business sees about an applicant or booked worker."""

    id: UUID
    full_name: str
    photo_url: str | None = None
    locality: str
    category_slugs: list[str]
    verification_status: VerificationStatus
    rating_avg: float
    rating_count: int
    completed_shift_count: int
    member_since: datetime
    recent_reviews: list[ReviewSnippet] = Field(default_factory=list)


class ReviewSnippet(BaseModel):
    stars: int
    tags: list[str]
    review: str
    rater_name: str
    created_at: datetime


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_available: bool
    latitude: float | None = OptionalLatitude
    longitude: float | None = OptionalLongitude
    accuracy_m: int | None = Field(default=None, ge=0, le=100_000)


class LocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Latitude
    longitude: float = Longitude
    accuracy_m: int | None = Field(default=None, ge=0, le=100_000)


class AvailabilityResponse(BaseModel):
    is_available: bool
    availability_changed_at: datetime | None = None
    location_recorded_at: datetime | None = None


class VerificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class VerificationQueue(BaseModel):
    workers: list[WorkerProfileResponse]
    businesses: list[BusinessProfileResponse]


WorkerPublicProfile.model_rebuild()
