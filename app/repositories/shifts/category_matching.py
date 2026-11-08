"""Worker <-> work category matching, shared by the feed, dispatch and availability SQL."""

from __future__ import annotations

from typing import Final

# Off for now: every Worker sees, receives and may take work in any category.
# A Worker with no categories set always matches every category.
MATCH_WORKER_CATEGORIES: Final[bool] = False


def worker_category_clause(worker_profile_id: str, category_id: str) -> str:
    if not MATCH_WORKER_CATEGORIES:
        # Still reference the parameter: Postgres can't type an unused $n placeholder.
        return f"({category_id}::uuid IS NULL OR TRUE)"
    return f"""(
      NOT EXISTS (SELECT 1 FROM worker_work_categories wwc
                  WHERE wwc.worker_profile_id = {worker_profile_id})
      OR EXISTS (SELECT 1 FROM worker_work_categories wwc
                 WHERE wwc.worker_profile_id = {worker_profile_id}
                   AND wwc.category_id = {category_id})
  )"""
