"""Application settings — all runtime knobs from environment (12-factor).

Marketplace policy values (radii, timeouts, fee) are **owner decisions**: defaults
below mirror the Figma copy and must be confirmed before production.

The console OTP provider is refused in production. The fake payment and payout providers
still start there, but never report money as moved (see their factories), so no booking,
refund or withdrawal is marked done without a real provider. The console push provider
likewise reports pushes as failed (not sent) in production.
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
    MSG_PROVIDER_SETTING_MISSING,
)

_DEV_ONLY_PROVIDERS: dict[str, str] = {
    "otp_provider": "console",
}

_PRODUCTION_PROVIDER_SETTINGS: dict[tuple[str, str], tuple[str, ...]] = {
    ("payment_provider", "razorpay"): (
        "razorpay_key_id",
        "razorpay_key_secret",
        "payment_webhook_secret",
    ),
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
    # Recycle idle connections before the network/Neon silently drops them (dead sockets hang).
    db_max_idle_seconds: float = 60.0
    db_auto_create: bool = True

    # --- Auth (self-issued JWT after phone OTP) ---
    jwt_secret_key: str
    jwt_issuer: str = "kaaamnow"
    jwt_access_minutes: int = Field(default=15, ge=1)
    jwt_refresh_days: int = Field(default=30, ge=1)
    # A just-rotated refresh token may be presented again by a racing/retried client request.
    jwt_refresh_reuse_grace_seconds: int = Field(default=30, ge=0)

    # --- Admin panel login (env-backed admin accounts) ---
    # Comma-separated; every listed email signs in with the shared ADMIN_PASSWORD.
    admin_email: str = ""
    admin_password: str = ""

    # --- OTP ---
    otp_provider: str = "console"
    otp_length: int = Field(default=6, ge=4, le=8)
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 30
    otp_max_sends_per_hour: int = 5
    firebase_project_id: str = ""
    apitxt_auth_key: str = ""
    apitxt_send_otp_url: str = "https://apitxt.com/api/sendOTP"
    # sms | whatsapp | voice
    apitxt_channel: str = "sms"
    # DLT-approved SMS template id; empty uses the apitxt account default.
    apitxt_template_id: str = ""
    # Sender name users see on the OTP message (SMS header / WhatsApp name); empty hides it.
    otp_sender_name: str = ""

    # --- Marketplace policy (OWNER DECISIONS) ---
    default_currency: str = "INR"
    require_verified_workers: bool = True
    location_freshness_seconds: int = 300
    live_initial_radius_km: float = 3.0
    live_max_radius_km: float = 30.0
    live_radius_expand_after_seconds: int = 600
    live_search_timeout_seconds: int = 1800
    live_offer_timeout_seconds: int = 300
    live_dispatch_batch_size: int = 50
    # Live Work (paid, single-worker live bookings)
    live_work_payment_window_seconds: int = 1800
    live_arrival_code_ttl_seconds: int = 4 * 3600
    live_arrival_max_attempts: int = 5
    live_arrival_max_reissues: int = 10
    live_extension_response_seconds: int = 600
    live_extension_payment_seconds: int = 1800
    live_auto_complete_grace_seconds: int = 900
    live_refund_max_attempts: int = 5
    scheduled_notify_radius_km: float = 30.0
    feed_radius_km: float = 15.0
    # Hard cap: workers never see or apply to shifts farther than this from their own location.
    worker_max_shift_distance_km: float = 30.0
    # A live location this recent beats the saved profile address (worker moved city).
    worker_location_valid_hours: int = Field(default=24, ge=1)
    selection_confirm_hours: int = 12
    # Scheduled shifts must be posted at least this long before they start.
    scheduled_min_lead_hours: int = 24
    # Applying (= instant booking) closes this long before the shift starts.
    apply_closes_hours_before: int = 2
    max_upcoming_bookings_per_worker: int = 5
    # Workers with too many strikes see at most this many shifts in the feed.
    limited_feed_size: int = 5
    default_cancellation_cutoff_hours: int = 12
    check_in_radius_m: int = 200
    check_in_opens_minutes_before: int = 30
    no_show_grace_minutes: int = 30
    # Either side may end without a PIN from this many minutes before the booked end.
    end_shift_grace_minutes: int = 10
    early_end_pin_valid_minutes: int = 10
    extension_prompt_minutes_before: int = 15
    overtime_rate_pct: int = 130
    # Business stops work without a reason: worker keeps this share of the full booking.
    business_stop_worker_share_pct: int = 80
    tracking_average_speed_kmph: float = 20.0

    # --- Payments / payouts ---
    payment_provider: str = "fake"
    payment_expiry_seconds: int = 300
    payment_webhook_secret: str = ""
    # Razorpay Standard Checkout (PAYMENT_PROVIDER=razorpay). Key id is public (sent to apps).
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_api_base: str = "https://api.razorpay.com/v1"
    upi_payee_vpa: str = "kaaamnow@upi"
    upi_payee_name: str = "KaaamNow"
    payout_provider: str = "fake"
    min_withdrawal_minor: int = 10000

    # --- Notifications / media / support ---
    push_provider: str = "console"
    # push_provider=fcm: path to the Firebase service-account JSON (Project settings →
    # Service accounts → Generate new private key). Never commit the file.
    firebase_service_account_file: str = ""
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
    def admin_emails(self) -> list[str]:
        return [email.strip().lower() for email in self.admin_email.split(",") if email.strip()]

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
        for (field_name, provider), required in _PRODUCTION_PROVIDER_SETTINGS.items():
            missing = [name for name in required if not str(getattr(self, name)).strip()]
            if getattr(self, field_name) == provider and missing:
                raise ValueError(
                    MSG_PROVIDER_SETTING_MISSING.format(
                        provider=f"{field_name.upper()}={provider}",
                        names=", ".join(name.upper() for name in missing),
                    )
                )


@lru_cache(maxsize=1)
def load_settings() -> KaaamNowSettings:
    return KaaamNowSettings()  # type: ignore[call-arg]


__all__ = ["KaaamNowSettings", "load_settings"]
