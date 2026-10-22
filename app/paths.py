"""Filesystem anchors for the service."""

from pathlib import Path

# app/
APP_DIR = Path(__file__).resolve().parent
# repo root (KaaamNowBackend checkout)
REPO_ROOT = APP_DIR.parent
SQL_DIR = REPO_ROOT / "sql"
SEED_SQL = SQL_DIR / "seed" / "seed.sql"
LOGS_DIR = REPO_ROOT / "logs"
DEFAULT_MEDIA_DIR = REPO_ROOT / "media"
STATIC_DIR = APP_DIR / "static"
