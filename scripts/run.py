#!/usr/bin/env python3
"""Single entrypoint for the KaaamNow API.

Usage:
    make run-api ENV=dev
    .venv/bin/python scripts/run.py --env dev

The environment profile MUST be pinned before any ``app.config.settings`` import
(pydantic-settings resolves the dotenv file at class definition time), so this script
activates ``--env`` first and only imports the rest of the application afterwards.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _ensure_project_deps() -> None:
    try:
        import pydantic  # noqa: F401
    except ModuleNotFoundError:
        hint = (
            f"{_VENV_PYTHON} scripts/run.py --env dev"
            if _VENV_PYTHON.is_file()
            else "make install && make run-api ENV=dev"
        )
        print(f"Missing project dependencies. Use the project venv:\n  {hint}", file=sys.stderr)
        raise SystemExit(1) from None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the KaaamNow API.")
    parser.add_argument(
        "--env",
        choices=["dev", "prod"],
        default="dev",
        help="Environment profile (.env.dev / .env.prod).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _ensure_project_deps()
    args = parse_args(argv)

    from app.config.environment_loader import activate_environment_profile

    activate_environment_profile(args.env)

    from pydantic import ValidationError

    from app.config.settings import load_settings

    try:
        load_settings()
    except ValidationError as exc:
        missing = ", ".join(sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]}))
        print(
            f"Invalid or missing settings for profile '{args.env}': {missing.upper()}.\n"
            f"Copy .env.example to .env.{args.env} and fill it in.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    from app.kaaamnow_api_server import start_kaaamnow_api_server

    start_kaaamnow_api_server()


if __name__ == "__main__":
    main()
