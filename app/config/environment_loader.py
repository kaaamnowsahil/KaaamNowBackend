"""Resolves which dotenv file backs the running process.

  * ``--env dev``     -> ``.env.dev`` (also the default when omitted)
  * ``--env preprod`` -> ``.env.preprod``
  * ``--env prod``    -> ``.env.prod``
  * ``--env test``    -> ``.env.test`` (pytest)

``ENV_PROFILE`` is honored the same way when ``--env`` is omitted.

Call :func:`activate_environment_profile` before importing ``app.config.settings``,
since pydantic-settings reads the dotenv file at class-definition time.
"""

from __future__ import annotations

import os

from app.constants.application.application_constants import (
    ENV_FILE_BY_PROFILE,
    ENV_PROFILE_DEV,
    ENV_VAR_PROFILE,
)
from app.paths import REPO_ROOT


def normalize_profile(profile: str | None) -> str | None:
    if profile is None:
        return None
    profile = profile.strip().lower()
    return profile or None


def resolve_active_profile(explicit_profile: str | None = None) -> str:
    """Order of precedence: explicit arg > ENV_PROFILE > ``dev``."""
    return (
        normalize_profile(explicit_profile)
        or normalize_profile(os.getenv(ENV_VAR_PROFILE))
        or ENV_PROFILE_DEV
    )


def resolve_env_file(explicit_profile: str | None = None) -> str:
    """Absolute path (as str) to the dotenv file for the active profile."""
    profile = resolve_active_profile(explicit_profile)
    filename = ENV_FILE_BY_PROFILE.get(profile, ENV_FILE_BY_PROFILE[ENV_PROFILE_DEV])
    return str(REPO_ROOT / filename)


def activate_environment_profile(explicit_profile: str | None = None) -> str:
    """Pin ``ENV_PROFILE`` for this process. Call before importing settings."""
    profile = resolve_active_profile(explicit_profile)
    os.environ[ENV_VAR_PROFILE] = profile
    return profile
