from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

from app.config.environment_loader import activate_environment_profile, resolve_env_file

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _test_database_url() -> str:
    """Tests drop and recreate their database, so derive a separate local one from .env.dev."""
    dev_url = os.getenv("DATABASE_URL") or dotenv_values(resolve_env_file()).get("DATABASE_URL")
    if not dev_url:
        raise RuntimeError("DATABASE_URL is not set in .env.dev")
    parts = urlsplit(dev_url)
    if parts.hostname not in _LOCAL_HOSTS:
        raise RuntimeError("Tests only run against a local Postgres (localhost).")
    db_name = parts.path.lstrip("/")
    if not db_name.endswith("_test"):
        db_name = f"{db_name}_test"
    return urlunsplit(parts._replace(path=f"/{db_name}"))


activate_environment_profile("dev")
os.environ["DATABASE_URL"] = _test_database_url()
os.environ["LOG_LEVEL"] = "warning"
os.environ["BACKGROUND_JOBS_ENABLED"] = "false"
os.environ["MEDIA_DIR"] = "/tmp/kaaamnow-test-media"
os.environ.setdefault("PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
