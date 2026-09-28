#!/usr/bin/env python3
"""Preflight verification for CI: ensure all required validation tools and canonical truth exist.

Fails closed if any required runner script, checker, generator, or canonical ground-truth
file is absent or empty.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOOLS = [
    "tools/run_known_motion_gates.py",
    "tools/verify_fixtures.py",
    "tools/test_ci_fail_closed.py",
    "tools/validate_test_collection.py",
    "tools/check_known_motion.py",
    "tools/motion_field.py",
    "test-data/generate_known_motion_fixture.py",
]

REQUIRED_CANONICAL_FILES = [
    "test-data/known_motion/MANIFEST.json",
    "test-data/known_motion/km_global_hisnr_ground_truth.json",
    "test-data/known_motion/km_local_hisnr_ground_truth.json",
    "test-data/known_motion/km_local_noisy_ground_truth.json",
    "test-data/known_motion/km_local_nonsquare_ground_truth.json",
    "test-data/known_motion/km_global_hisnr.star",
    "test-data/known_motion/km_local_hisnr.star",
    "test-data/known_motion/km_local_noisy.star",
    "test-data/known_motion/km_local_nonsquare.star",
]


def check_preflight(repo_dir: Path) -> Tuple[bool, List[str]]:
    missing_or_empty: List[str] = []
    for rel_path in REQUIRED_TOOLS + REQUIRED_CANONICAL_FILES:
        path = repo_dir / rel_path
        if not path.is_file():
            missing_or_empty.append(f"MISSING: {rel_path}")
        elif path.stat().st_size == 0:
            missing_or_empty.append(f"EMPTY: {rel_path}")
    return len(missing_or_empty) == 0, missing_or_empty


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT,
                        help="Repository root directory to inspect")
    args = parser.parse_args()

    ok, errors = check_preflight(args.repo.resolve())
    if not ok:
        print("=== CI PREFLIGHT FAILURE: Required validation files missing ===", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print(f"CI PREFLIGHT PASS: All {len(REQUIRED_TOOLS) + len(REQUIRED_CANONICAL_FILES)} required files verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
