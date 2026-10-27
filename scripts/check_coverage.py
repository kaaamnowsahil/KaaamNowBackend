"""Per-file coverage gate for money and coupon logic.

coverage's own ``fail_under`` only checks the combined total, which lets one weak module hide
behind strong ones. This reads ``coverage.json`` (written by ``make coverage``) and fails when
any file in ``[tool.coverage.report].include`` is below the threshold for statements or for
branches, each checked on its own.

    python scripts/check_coverage.py [coverage.json] [--min 95]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _patterns() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return config["tool"]["coverage"]["report"]["include"]


def _pct(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default=str(ROOT / "coverage.json"))
    parser.add_argument("--min", type=float, default=95.0)
    args = parser.parse_args()

    files = json.loads(Path(args.report).read_text())["files"]
    patterns = _patterns()
    failures: list[str] = []
    print(f"{'file':58} {'stmts':>7} {'branch':>7} {'funcs':>7} {'lines':>7}")
    for name in sorted(files):
        if not any(fnmatch.fnmatch(name, p) for p in patterns):
            continue
        s = files[name]["summary"]
        statements = _pct(s["covered_lines"], s["num_statements"])
        branches = _pct(s.get("covered_branches", 0), s.get("num_branches", 0))
        functions = files[name].get("functions", {})
        fn_total = sum(1 for f, v in functions.items() if f and v["summary"]["num_statements"])
        fn_hit = sum(
            1
            for f, v in functions.items()
            if f and v["summary"]["num_statements"] and v["summary"]["covered_lines"]
        )
        funcs = _pct(fn_hit, fn_total)
        print(f"{name:58} {statements:6.1f}% {branches:6.1f}% {funcs:6.1f}% {statements:6.1f}%")
        for label, value in (("statements", statements), ("branches", branches)):
            if value < args.min:
                failures.append(f"{name}: {label} {value:.1f}% < {args.min}%")
    if failures:
        print("\nCoverage below threshold:\n  " + "\n  ".join(failures))
        return 1
    print(f"\nAll critical modules at or above {args.min}% statements and branches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
