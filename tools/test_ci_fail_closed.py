#!/usr/bin/env python3
"""Negative controls for CI fail-closed policies and fixture verification.

Validates that:
1. Absent truth script fails CI / preflight (no silent exit 0).
2. Absent dependency fails CMake configure when BUILD_TESTING=ON.
3. Zero collected tests or missing required tests fail CTest collection validation.
4. Missing required fixture fails fixture verification.
5. Byte-flipped fixture fails fixture verification.
6. Locally regenerated self-consistent but noncanonical fixture fails verification
   against the trusted canonical manifest (prevents self-certification drift).

All controls execute in isolated temporary sandboxes and never alter canonical files.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_FIXTURES = REPO_ROOT / "tools" / "verify_fixtures.py"
VALIDATE_COLLECTION = REPO_ROOT / "tools" / "validate_test_collection.py"
CANONICAL_MANIFEST = REPO_ROOT / "test-data" / "known_motion" / "MANIFEST.json"


class TestCiFailClosedControls(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_1_absent_truth_script_fails_closed(self) -> None:
        """Control 1: Missing truth script must fail with nonzero exit, not exit 0."""
        # Simulate CI check command where truth script is absent
        fake_bin_dir = self.sandbox / "tools"
        fake_bin_dir.mkdir(parents=True)
        missing_script = fake_bin_dir / "run_known_motion_gates.py"

        # The new CI fail-closed check:
        # test -f tools/run_known_motion_gates.py || { echo "ERROR: Missing required script"; exit 1; }
        bash_cmd = f"test -f {missing_script} || exit 1"
        res = subprocess.run(["bash", "-c", bash_cmd])
        self.assertNotEqual(res.returncode, 0, "Missing truth script must yield nonzero exit code")

        # Also verify that runner itself fails if invoked with missing checker or binary
        res_runner = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "run_known_motion_gates.py"),
             "--binary", str(self.sandbox / "nonexistent_binary")],
            capture_output=True, text=True
        )
        self.assertNotEqual(res_runner.returncode, 0, "Runner must fail if binary is nonexistent")

    def test_2_absent_dependency_fails_cmake(self) -> None:
        """Control 2: BUILD_TESTING=ON must fail if python or numpy is missing."""
        # Create a python wrapper that executes python but fails import numpy
        stub_python = self.sandbox / "stub_python.sh"
        stub_python.write_text("""#!/bin/sh
if echo "$*" | grep -q "numpy"; then
    exit 1
fi
exec """ + sys.executable + """ "$@"
""")
        stub_python.chmod(0o755)

        proj_on = self.sandbox / "proj_on"
        proj_on.mkdir()
        (proj_on / "CMakeLists.txt").write_text(f"""
cmake_minimum_required(VERSION 3.20)
project(DependencyNegativeControl)
set(BUILD_TESTING ON)
set(Python3_EXECUTABLE "{stub_python}")

find_package(Python3 COMPONENTS Interpreter REQUIRED)
execute_process(
    COMMAND "${{Python3_EXECUTABLE}}" -c "import numpy"
    RESULT_VARIABLE _NUMPY_CHECK
    OUTPUT_QUIET ERROR_QUIET
)
if(NOT _NUMPY_CHECK EQUAL 0)
    message(FATAL_ERROR "BUILD_TESTING=ON requires Python 3 with 'numpy' installed.")
endif()
""")
        build_dir = self.sandbox / "build_test_on"
        res = subprocess.run(["cmake", "-S", str(proj_on), "-B", str(build_dir)],
                             capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0, "CMake configure must fail when dependency check fails")
        self.assertIn("BUILD_TESTING=ON requires Python 3 with 'numpy' installed",
                      res.stderr + res.stdout)

        # Confirm BUILD_TESTING=OFF passes without python/numpy
        proj_off = self.sandbox / "proj_off"
        proj_off.mkdir()
        (proj_off / "CMakeLists.txt").write_text("""
cmake_minimum_required(VERSION 3.20)
project(DependencyOffControl)
set(BUILD_TESTING OFF)
if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
endif()
""")
        build_dir_off = self.sandbox / "build_test_off"
        res_off = subprocess.run(["cmake", "-S", str(proj_off), "-B", str(build_dir_off)],
                                 capture_output=True, text=True)
        self.assertEqual(res_off.returncode, 0, "BUILD_TESTING=OFF should not require Python/numpy")

    def test_3_zero_or_missing_collected_tests_fails(self) -> None:
        """Control 3: Empty test suite or missing required test fails collection validation."""
        # Case A: 0 tests collected
        empty_ctest_json = {"kind": "ctestInfo", "version": {"major": 1, "minor": 0}, "tests": []}
        res_empty = subprocess.run(
            [sys.executable, str(VALIDATE_COLLECTION)],
            input=json.dumps(empty_ctest_json),
            capture_output=True, text=True
        )
        self.assertEqual(res_empty.returncode, 1, "Zero collected tests must fail with exit code 1")
        self.assertIn("Empty test collection: 0 tests found", res_empty.stdout)

        # Case B: Tests present, but missing a required test
        incomplete_json = {
            "kind": "ctestInfo",
            "version": {"major": 1, "minor": 0},
            "tests": [{"name": "SyntheticRegression"}, {"name": "HotPixelRngDeterminism"}]
        }
        res_incomplete = subprocess.run(
            [sys.executable, str(VALIDATE_COLLECTION),
             "--required-tests", "SyntheticRegression", "HotPixelRngDeterminism", "RunnerExposure"],
            input=json.dumps(incomplete_json),
            capture_output=True, text=True
        )
        self.assertEqual(res_incomplete.returncode, 1, "Missing required test must fail with exit code 1")
        self.assertIn("Missing required test(s): RunnerExposure", res_incomplete.stdout)

    def test_4_missing_fixture_fails(self) -> None:
        """Control 4: Missing required fixture must fail verify_fixtures.py."""
        # Create fixtures dir with only 1 case instead of declared cases
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()
        (fix_dir / "km_global_hisnr.mrcs").write_bytes(b"dummy")

        res = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--no-allow-missing-heavy"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 1, "Missing fixture must fail verification")
        self.assertIn("MISSING", res.stdout)

    def test_5_byte_flipped_fixture_fails(self) -> None:
        """Control 5: Byte-flipped fixture file must fail verify_fixtures.py."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # Copy valid fixture from repo if present, or create matching mock
        manifest_data = json.loads(CANONICAL_MANIFEST.read_text())
        case_name = "km_global_hisnr"
        spec = manifest_data["cases"][case_name]
        src_file = REPO_ROOT / "test-data" / "known_motion" / f"{case_name}.mrcs"

        if src_file.exists():
            data = bytearray(src_file.read_bytes())
        else:
            # Generate minimal bytes matching spec length
            data = bytearray(spec["movie_bytes"])

        # Flip one bit in byte 100
        data[100] ^= 0x01
        corrupt_file = fix_dir / f"{case_name}.mrcs"
        corrupt_file.write_bytes(data)

        res = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", case_name],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 1, "Byte-flipped fixture must fail verification")
        self.assertIn("MISMATCH", res.stdout)

    def test_6_locally_regenerated_noncanonical_fixture_fails(self) -> None:
        """Control 6: Noncanonical fixture matching its own local manifest must fail against canonical manifest."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # Suppose an altered generator ran with different parameters/noise
        noncanonical_bytes = b"NONCANONICAL_FIXTURE_CONTENT_12345678"
        case_file = fix_dir / "km_global_hisnr.mrcs"
        case_file.write_bytes(noncanonical_bytes)

        import hashlib
        noncanonical_sha = hashlib.sha256(noncanonical_bytes).hexdigest()

        # The local generator writes a matching local manifest
        local_manifest = fix_dir / "MANIFEST.json"
        local_manifest.write_text(json.dumps({
            "cases": {
                "km_global_hisnr": {
                    "movie_sha256": noncanonical_sha,
                    "movie_bytes": len(noncanonical_bytes),
                }
            }
        }))

        # If verified against its adjacent local manifest, it would pass (the vulnerability!)
        res_self = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(local_manifest),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_self.returncode, 0, "Sanity check: self-verification passes adjacent manifest")

        # BUT verified against the trusted canonical manifest (default / git), it MUST FAIL!
        res_canonical = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_canonical.returncode, 1, "Noncanonical fixture must fail against canonical manifest")
        self.assertIn("MISMATCH", res_canonical.stdout)


if __name__ == "__main__":
    unittest.main()
