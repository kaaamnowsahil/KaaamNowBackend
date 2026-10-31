"""SQL for the realtime socket."""

from __future__ import annotations

WORKER_PROFILE_ID_BY_USER = "SELECT id FROM worker_profiles WHERE user_id = $1"
