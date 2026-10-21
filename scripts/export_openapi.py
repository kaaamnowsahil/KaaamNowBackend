"""Write the OpenAPI contract to ``openapi.yaml`` (no database needed)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from app.config.environment_loader import activate_environment_profile  # noqa: E402


def main() -> None:
    activate_environment_profile("dev")
    from app.kaaamnow_api_server import kaaamnow_api_application

    target = REPO_ROOT / "openapi.yaml"
    target.write_text(
        yaml.safe_dump(kaaamnow_api_application.openapi(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"wrote {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
