from __future__ import annotations

import os

from app.config.environment_loader import activate_environment_profile

activate_environment_profile("test")
os.environ.setdefault("PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
