#!/usr/bin/env python3
"""Validate CTest test suite collection via ctest --show-only=json-v1.

Ensures that CTest collection is fail-closed:
- Fails if 0 tests are collected.
- Fails if the suite contains fewer than the expected minimum number of tests.
- Fails if any declared required test is missing from the collected test list.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_REQUIRED_TESTS = [
    "SyntheticRegression",
    "HotPixelRngDeterminism",
    "RunnerExposure",
    "Runner_failure",
    "Runner_invalid",
    "Runner_resume",
    "Runner_tomography",
    "RunnerLateBin",
    "RunnerExportedUnits",
    "GainCache",
    "TiffRead",
    "DamagedMovie",
    "RunnerModelParser",
    "CiFailClosedControls",
    # Added by the #99 fail-closed write group (PR105). WriteFaults is the
    # end-to-end runner control; ImageWriteFaults is the unit-level
    # RLIMIT_FSIZE injection and is registered under if(UNIX).
    "WriteFaults",
    "ImageWriteFaults",
    # Added by the #98 malformed-defect-parser group (PR101).
    "DefectParser",
    # Added by the #26 global inverse-FFT elision (PR111). This is the only
    # test in the suite that can observe a wrong elision predicate: both parity
    # comparators skip _EVN/_ODD, so without this entry the guard could be
    # dropped from CMakeLists.txt with the collected count still at the
    # minimum and CI still green.
    "GlobalIfftElision",
    # Added by the #69 CUDA reliability port. Device-free, so it is always
    # collected; the CUDA-only CudaErrorClass is not listed here, matching
    # the existing exclusion of CudaWrapperUploadFailure.
    "PatchRetryState",
    # Issue #85 lane C: each arm's MRC/STAR inventory and structure is checked
    # independently before pairwise image equality is considered.
    "OutputTreeComparator",
]


def load_ctest_json(
    test_dir: Optional[Path] = None,
    json_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Retrieve CTest JSON report either by executing ctest or reading file/stdin."""
    if test_dir is not None:
        cmd = ["ctest", "--test-dir", str(test_dir), "--show-only=json-v1"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ctest --show-only=json-v1 failed (exit {proc.returncode}):\n{proc.stderr}"
            )
        return json.loads(proc.stdout)
    if json_path is not None:
        return json.loads(json_path.read_text())
    if not sys.stdin.isatty():
        return json.load(sys.stdin)
    raise ValueError("Must provide --test-dir, --json, or pipe JSON to stdin")


def validate_tests(
    ctest_data: Dict[str, Any],
    min_count: int = 1,
    required_tests: Optional[Sequence[str]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    tests = ctest_data.get("tests", [])
    collected_names = [t.get("name", "") for t in tests if isinstance(t, dict)]

    req = list(required_tests) if required_tests is not None else list(DEFAULT_REQUIRED_TESTS)
    missing = [name for name in req if name not in collected_names]

    report: Dict[str, Any] = {
        "collected_count": len(collected_names),
        "collected_tests": collected_names,
        "min_count": min_count,
        "required_tests": req,
        "missing_tests": missing,
        "status": "PASS",
    }

    if len(collected_names) == 0:
        report["status"] = "FAIL"
        report["reason"] = "Empty test collection: 0 tests found"
        return False, report

    if len(collected_names) < min_count:
        report["status"] = "FAIL"
        report["reason"] = f"Test count {len(collected_names)} is less than minimum {min_count}"
        return False, report

    if missing:
        report["status"] = "FAIL"
        report["reason"] = f"Missing required test(s): {', '.join(missing)}"
        return False, report

    return True, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--test-dir", type=Path, default=None,
                        help="Build directory to inspect via ctest")
    parser.add_argument("--json", type=Path, default=None,
                        help="Path to pre-dumped ctest json-v1 output")
    parser.add_argument("--min-count", type=int, default=20,
                        help="Minimum number of tests that must be collected (default: 20)")
    parser.add_argument("--required-tests", nargs="*", default=None,
                        help="Explicit list of required test names (default: standard MotionCorr suite)")
    parser.add_argument("--quiet", action="store_true",
                        help="Quiet output")
    parser.add_argument("--dump-json", type=Path, default=None,
                        help="Write validation result to JSON file")
    opts = parser.parse_args()

    try:
        data = load_ctest_json(opts.test_dir, opts.json)
    except Exception as exc:
        print(f"ERROR: Failed to obtain CTest JSON data: {exc}", file=sys.stderr)
        return 2

    success, report = validate_tests(
        ctest_data=data,
        min_count=opts.min_count,
        required_tests=opts.required_tests,
    )

    if opts.dump_json:
        opts.dump_json.parent.mkdir(parents=True, exist_ok=True)
        opts.dump_json.write_text(json.dumps(report, indent=2) + "\n")

    if not opts.quiet:
        print(f"=== CTest Collection Validation: {report['status']} === ")
        print(f"  Collected tests: {report['collected_count']}")
        for t in report["collected_tests"]:
            mark = "REQUIRED" if t in report["required_tests"] else "ADDITIVE"
            print(f"    - {t:<30} [{mark}]")
        if report["missing_tests"]:
            print(f"  MISSING REQUIRED TESTS:\n    " + "\n    ".join(report["missing_tests"]))
        if not success:
            print(f"  FAILURE REASON: {report.get('reason')}")

    if not success:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
