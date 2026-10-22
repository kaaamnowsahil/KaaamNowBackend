"""Application settings — all runtime knobs from environment (12-factor).

Marketplace policy values (radii, timeouts, fee) are **owner decisions**: defaults
below mirror the Figma copy and must be confirmed before production.

Payments, payouts and push are out of scope for now, so their fake/console providers
are allowed in production; only the console OTP provider is refused.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.environment_loader import resolve_active_profile, resolve_env_file
from app.constants.application.application_constants import (
    DEFAULT_API_PORT,
    ENCODING_UTF8,
    ENV_PROFILE_PROD,
    MEDIA_STORAGE_CHOICES,
    MEDIA_STORAGE_LOCAL,
    MSG_CORS_WILDCARD_NOT_ALLOWED_IN_PRODUCTION,
    MSG_DATABASE_URL_SCHEME,
    MSG_JWT_SECRET_TOO_SHORT,
    MSG_MEDIA_STORAGE_UNKNOWN,
    MSG_PROVIDER_NOT_ALLOWED_IN_PRODUCTION,
)

_DEV_ONLY_PROVIDERS: dict[str, str] = {
    "otp_provider": "console",
}


class KaaamNowSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(),
        env_file_encoding=ENCODING_UTF8,
        extra="ignore",
        case_sensitive=False,
    )

    # --- Process ---
    app_version: str = "1.0.0"
    port: int = DEFAULT_API_PORT
    listen_host: str = "0.0.0.0"
    log_level: str = "info"
    log_to_file: bool = False
    cors_origin: str = "*"
    pagination_default_limit: int = Field(default=20, ge=1)
    pagination_max_limit: int = Field(default=100, ge=1)
    background_jobs_enabled: bool = True
    background_sweep_interval_seconds: int = Field(default=15, ge=1)
    # Serverless hosts (Vercel) freeze idle processes, so the sweep runs inline on
    # incoming requests at most once per interval instead of in a background loop.
    request_sweep_enabled: bool = False

    # --- Database ---
    database_url: str
    db_pool_min: int = 1
    db_pool_max: int = 10
    db_command_timeout_seconds: int = 60
    db_connect_timeout_seconds: int = 30
    db_auto_create: bool = True

    # --- Auth (self-issued JWT after phone OTP) ---
    jwt_secret_key: str
    jwt_issuer: str = "kaaamnow"
    jwt_access_minutes: int = Field(default=15, ge=1)
    jwt_refresh_days: int = Field(default=30, ge=1)

    # --- OTP ---
    otp_provider: str = "console"
    otp_length: int = Field(default=6, ge=4, le=8)
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 30
    otp_max_sends_per_hour: int = 5
    firebase_project_id: str = ""

    # --- Marketplace policy (OWNER DECISIONS) ---
    default_currency: str = "INR"
    require_verified_workers: bool = True
    location_freshness_seconds: int = 300
    live_initial_radius_km: float = 3.0
    live_max_radius_km: float = 5.0
    live_radius_expand_after_seconds: int = 600
    live_search_timeout_seconds: int = 1800
    live_offer_timeout_seconds: int = 300
    live_dispatch_batch_size: int = 50
    scheduled_notify_radius_km: float = 5.0
    feed_radius_km: float = 10.0
    selection_confirm_hours: int = 12
    default_cancellation_cutoff_hours: int = 12
    check_in_radius_m: int = 200
    check_in_opens_minutes_before: int = 30
    no_show_grace_minutes: int = 30
    tracking_average_speed_kmph: float = 20.0

    # --- Payments / payouts ---
    payment_provider: str = "fake"
    payment_expiry_seconds: int = 300
    payment_webhook_secret: str = ""
    upi_payee_vpa: str = "kaaamnow@upi"
    upi_payee_name: str = "KaaamNow"
    payout_provider: str = "fake"
    min_withdrawal_minor: int = 10000

    # --- Notifications / media / support ---
    push_provider: str = "console"
    media_storage: str = MEDIA_STORAGE_LOCAL
    media_dir: str = ""
    media_base_url: str = "/media"
    max_photo_bytes: int = 5 * 1024 * 1024
    support_email: str

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        url = (value or "").strip()
        lowered = url.lower()
        if not (lowered.startswith("postgres://") or lowered.startswith("postgresql://")):
            scheme = url.split(":", 1)[0] if ":" in url else ""
            raise ValueError(MSG_DATABASE_URL_SCHEME.format(scheme=scheme))
        return url

    @field_validator("media_storage")
    @classmethod
    def _validate_media_storage(cls, value: str) -> str:
        storage = (value or "").strip().lower()
        if storage not in MEDIA_STORAGE_CHOICES:
            raise ValueError(
                MSG_MEDIA_STORAGE_UNKNOWN.format(
                    allowed=", ".join(MEDIA_STORAGE_CHOICES), value=value
                )
            )
        return storage

    @property
    def env_profile(self) -> str:
        return resolve_active_profile()

    @property
    def is_production(self) -> bool:
        return self.env_profile == ENV_PROFILE_PROD

    def validate_production_config(self) -> None:
        """Refuse dev-only providers and weak secrets in production."""
        if len(self.jwt_secret_key) < 32 and self.is_production:
            raise ValueError(MSG_JWT_SECRET_TOO_SHORT)
        if not self.is_production:
            return
        if self.cors_origin.strip() == "*":
            raise ValueError(MSG_CORS_WILDCARD_NOT_ALLOWED_IN_PRODUCTION)
        for field_name, dev_value in _DEV_ONLY_PROVIDERS.items():
            if getattr(self, field_name) == dev_value:
                raise ValueError(
                    MSG_PROVIDER_NOT_ALLOWED_IN_PRODUCTION.format(
                        name=field_name.upper(), value=dev_value
                    )
                )


@lru_cache(maxsize=1)
def load_settings() -> KaaamNowSettings:
    return KaaamNowSettings()  # type: ignore[call-arg]


__all__ = ["KaaamNowSettings", "load_settings"]
