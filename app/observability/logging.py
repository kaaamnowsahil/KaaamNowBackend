"""JSON structured logging with optional rotating file output.

* JSON is always emitted to stdout (container/log-aggregator friendly).
* ``LOG_TO_FILE=true`` (or production) also writes ``logs/kaamnow-api.log``.
* ``request_id`` from the request context is merged into every record.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from app.constants.application.application_constants import (
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    LOG_FILE_NAME,
)
from app.paths import LOGS_DIR
from app.utils.request_context import get_request_id

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, default=str)


def _settings_log_level() -> str:
    try:
        from app.config.settings import load_settings

        return load_settings().log_level.upper()
    except Exception:
        return "INFO"


def _should_log_to_file() -> bool:
    try:
        from app.config.settings import load_settings

        settings = load_settings()
        return settings.log_to_file or settings.is_production
    except Exception:
        return False


def configure_application_logging() -> None:
    """Configure the root logger once per process (idempotent)."""
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(getattr(logging, _settings_log_level(), logging.INFO))
    if _CONFIGURED:
        return
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JsonFormatter())
    root.addHandler(stdout_handler)
    if _should_log_to_file():
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOGS_DIR / LOG_FILE_NAME,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(**fields: object) -> dict[str, object]:
    """Build the ``extra=`` dict expected by :class:`JsonFormatter`."""
    return {"extra_fields": {k: v for k, v in fields.items() if v is not None}}
