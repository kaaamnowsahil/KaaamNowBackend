"""Process-level constants: names, env profiles, roles, log messages."""

from __future__ import annotations

from typing import Final

APP_TITLE: Final[str] = "KaaamNow API"
SERVICE_NAME: Final[str] = "kaaamnow-api"
UVICORN_APP_IMPORT_PATH: Final[str] = "app.kaaamnow_api_server:kaaamnow_api_application"
DEFAULT_API_PORT: Final[int] = 8000
ENCODING_UTF8: Final[str] = "utf-8"

# --- Environment profiles ---
ENV_VAR_PROFILE: Final[str] = "ENV_PROFILE"
ENV_PROFILE_DEV: Final[str] = "dev"
ENV_PROFILE_PREPROD: Final[str] = "preprod"
ENV_PROFILE_PROD: Final[str] = "prod"
ENV_PROFILE_TEST: Final[str] = "test"
ENV_FILE_BY_PROFILE: Final[dict[str, str]] = {
    ENV_PROFILE_DEV: ".env.dev",
    ENV_PROFILE_PREPROD: ".env.preprod",
    ENV_PROFILE_PROD: ".env.prod",
    ENV_PROFILE_TEST: ".env.test",
}
VALID_ENV_PROFILES: Final[tuple[str, ...]] = tuple(ENV_FILE_BY_PROFILE)

# --- User roles (JWT ``roles`` claim + ``user_roles.role``) ---
ROLE_BUSINESS: Final[str] = "business"
ROLE_WORKER: Final[str] = "worker"
ROLE_ADMIN: Final[str] = "admin"
SELF_SERVICE_ROLES: Final[tuple[str, ...]] = (ROLE_BUSINESS, ROLE_WORKER)
ALL_ROLES: Final[tuple[str, ...]] = (ROLE_BUSINESS, ROLE_WORKER, ROLE_ADMIN)

# --- Logging ---
LOG_FILE_NAME: Final[str] = "kaaamnow-api.log"
LOG_FILE_MAX_BYTES: Final[int] = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT: Final[int] = 5
LOG_API_READY: Final[str] = "api ready"
LOG_API_SHUTDOWN_COMPLETE: Final[str] = "api shutdown complete"
LOG_DATABASE_CONNECTED: Final[str] = "database connected"
LOG_DATABASE_CREATED: Final[str] = "database created"
LOG_DATABASE_BOOTSTRAP_COMPLETE: Final[str] = "database bootstrap complete"

MSG_DATABASE_POOL_NOT_INITIALIZED: Final[str] = "database pool is not initialized"
MSG_DATABASE_URL_SCHEME: Final[str] = (
    "DATABASE_URL must start with postgres:// or postgresql:// (got {scheme!r})"
)
MSG_PROVIDER_NOT_ALLOWED_IN_PRODUCTION: Final[str] = (
    "{name}={value} is a development provider and is refused in production"
)
MSG_JWT_SECRET_TOO_SHORT: Final[str] = "JWT_SECRET_KEY must be at least 32 characters"
MSG_CORS_WILDCARD_NOT_ALLOWED_IN_PRODUCTION: Final[str] = "CORS_ORIGIN='*' is refused in production"
