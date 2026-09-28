#!/usr/bin/env python3
"""Negative controls for CI fail-closed policies and fixture verification.

Validates that:
1. Absent truth script or tool fails CI preflight; missing binary fails gate runner.
2. Absent Python/NumPy dependency fails CMake configure when BUILD_TESTING=ON on MotionCorr CMakeLists.txt.
3. Zero collected tests or missing required tests (including CiFailClosedControls) fail CTest validation.
4. Missing fixture movie, missing truth file, or malformed manifest inventory fails fixture verification.
5. Asserted valid baseline fixture fails verification when corrupted by a single byte flip.
6. Default git-backed fixture verification fails closed on invalid git refs and rejects tampered disk manifests.
7. Generator protects canonical truth: rejects canonical disagreement and refuses conflicting stem overwrite.

All controls execute in isolated temporary sandboxes and never alter canonical files.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VERIFY_FIXTURES = REPO_ROOT / "tools" / "verify_fixtures.py"
VALIDATE_COLLECTION = REPO_ROOT / "tools" / "validate_test_collection.py"
PREFLIGHT = REPO_ROOT / "tools" / "ci_preflight.py"
RUNNER = REPO_ROOT / "tools" / "run_known_motion_gates.py"
GENERATOR = REPO_ROOT / "test-data" / "generate_known_motion_fixture.py"
CANONICAL_MANIFEST = REPO_ROOT / "test-data" / "known_motion" / "MANIFEST.json"


class TestCiFailClosedControls(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_1_absent_truth_script_and_missing_binary(self) -> None:
        """Control 1: Missing truth script fails CI preflight; missing binary fails gate runner."""
        # 1A: Isolated preflight test with missing required script
        fake_repo = self.sandbox / "fake_repo"
        fake_repo.mkdir()
        tools_dir = fake_repo / "tools"
        tools_dir.mkdir()
        test_data_dir = fake_repo / "test-data" / "known_motion"
        test_data_dir.mkdir(parents=True)

        from tools.ci_preflight import REQUIRED_TOOLS, REQUIRED_CANONICAL_FILES
        for rel in REQUIRED_TOOLS + REQUIRED_CANONICAL_FILES:
            if rel != "tools/run_known_motion_gates.py":
                p = fake_repo / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("dummy")

        res_preflight = subprocess.run(
            [sys.executable, str(PREFLIGHT), "--repo", str(fake_repo)],
            capture_output=True, text=True
        )
        self.assertEqual(res_preflight.returncode, 1, "Preflight must fail when a required script is missing")
        self.assertIn("MISSING: tools/run_known_motion_gates.py", res_preflight.stderr)

        # 1B: Runner with missing binary must fail with explicit reason, not argparse error
        res_runner = subprocess.run(
            [sys.executable, str(RUNNER),
             "--binary", str(self.sandbox / "nonexistent_binary"),
             "--outdir", str(self.sandbox / "outdir"),
             "--fixtures", str(REPO_ROOT / "test-data" / "known_motion")],
            capture_output=True, text=True
        )
        self.assertEqual(res_runner.returncode, 2, "Runner must exit 2 when binary is not found")
        self.assertIn("ERROR: binary not found:", res_runner.stderr)

        # 1C: Gate runner fails closed on malformed, truncated, or unreadable MANIFEST.json
        runner_fixtures = self.sandbox / "runner_fixtures"
        runner_fixtures.mkdir()
        shutil.copy(REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr_ground_truth.json",
                    runner_fixtures / "km_global_hisnr_ground_truth.json")

        # Write truncated/malformed MANIFEST.json
        truncated_manifest = runner_fixtures / "MANIFEST.json"
        truncated_manifest.write_text('{"cases": {"km_global_hisnr": ')  # unclosed JSON

        res_truncated = subprocess.run(
            [sys.executable, str(RUNNER),
             "--binary", str(sys.executable),
             "--outdir", str(self.sandbox / "outdir1"),
             "--fixtures", str(runner_fixtures),
             "--no-regenerate"],
            capture_output=True, text=True
        )
        self.assertEqual(res_truncated.returncode, 2, "Runner must fail closed on malformed manifest")
        self.assertIn("malformed or unreadable fixture manifest", res_truncated.stderr)

        # Empty cases in manifest must also fail closed
        truncated_manifest.write_text(json.dumps({"cases": {}}))
        res_empty = subprocess.run(
            [sys.executable, str(RUNNER),
             "--binary", str(sys.executable),
             "--outdir", str(self.sandbox / "outdir2"),
             "--fixtures", str(runner_fixtures),
             "--no-regenerate"],
            capture_output=True, text=True
        )
        self.assertEqual(res_empty.returncode, 2, "Runner must fail closed on empty cases manifest")
        self.assertIn("cases' inventory is empty or malformed", res_empty.stderr)

    def test_2_absent_dependency_fails_cmake(self) -> None:
        """Control 2: BUILD_TESTING=ON must fail if python or numpy is missing in MotionCorr CMakeLists.txt."""
        # Create a python stub wrapper with properly quoted sys.executable
        stub_python = self.sandbox / "stub_python.sh"
        stub_python.write_text(f"""#!/bin/sh
if echo "$*" | grep -q "numpy"; then
    exit 1
fi
exec "{sys.executable}" "$@"
""")
        stub_python.chmod(0o755)

        # Test MotionCorr's actual CMakeLists.txt with BUILD_TESTING=ON and stub python
        build_dir_on = self.sandbox / "build_test_on"
        res_on = subprocess.run([
            "cmake", "-S", str(REPO_ROOT), "-B", str(build_dir_on),
            "-DBUILD_TESTING=ON",
            f"-DPython3_EXECUTABLE={stub_python}",
            "-DCMAKE_BUILD_TYPE=Debug"
        ], capture_output=True, text=True)
        self.assertNotEqual(res_on.returncode, 0, "CMake configure must fail when NumPy is missing")
        self.assertIn("BUILD_TESTING=ON requires Python 3 with 'numpy' installed",
                      res_on.stderr + res_on.stdout)

        # Test MotionCorr's actual CMakeLists.txt with BUILD_TESTING=OFF
        build_dir_off = self.sandbox / "build_test_off"
        res_off = subprocess.run([
            "cmake", "-S", str(REPO_ROOT), "-B", str(build_dir_off),
            "-DBUILD_TESTING=OFF",
            f"-DPython3_EXECUTABLE={stub_python}",
            "-DCMAKE_BUILD_TYPE=Debug"
        ], capture_output=True, text=True)
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

        # Case B: CiFailClosedControls missing from collected list
        tests_without_control = [
            {"name": "SyntheticRegression"},
            {"name": "HotPixelRngDeterminism"},
            {"name": "RunnerExposure"},
            {"name": "Runner_failure"},
            {"name": "Runner_invalid"},
            {"name": "Runner_resume"},
            {"name": "Runner_tomography"},
            {"name": "RunnerLateBin"},
            {"name": "RunnerExportedUnits"},
            {"name": "GainCache"},
            {"name": "TiffRead"},
            {"name": "DamagedMovie"},
            {"name": "RunnerModelParser"},
        ]
        res_missing_new = subprocess.run(
            [sys.executable, str(VALIDATE_COLLECTION)],
            input=json.dumps({"kind": "ctestInfo", "version": {"major": 1, "minor": 0}, "tests": tests_without_control}),
            capture_output=True, text=True
        )
        self.assertEqual(res_missing_new.returncode, 1, "Missing CiFailClosedControls must fail validation")
        self.assertIn("CiFailClosedControls", res_missing_new.stdout)

    def test_4_missing_fixture_or_truth_fails(self) -> None:
        """Control 4: Missing fixture movie, missing truth file, or malformed manifest fails verify_fixtures."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # 4A: Missing movie
        res_missing_movie = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_missing_movie.returncode, 1)
        self.assertIn("MISSING", res_missing_movie.stdout)

        # 4B: Movie present but declared ground-truth JSON missing
        movie_path = fix_dir / "km_global_hisnr.mrcs"
        manifest_data = json.loads(CANONICAL_MANIFEST.read_text())
        expected_spec = manifest_data["cases"]["km_global_hisnr"]
        movie_path.write_bytes(b"\x00" * expected_spec["movie_bytes"])

        res_missing_truth = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_missing_truth.returncode, 1, "Missing ground-truth JSON must fail")
        self.assertIn("ground-truth JSON MISSING", res_missing_truth.stdout)

        # 4C: Malformed empty manifest inventory
        empty_manifest = self.sandbox / "empty_manifest.json"
        empty_manifest.write_text(json.dumps({"cases": {}}))
        res_empty_manifest = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(empty_manifest)],
            capture_output=True, text=True
        )
        self.assertEqual(res_empty_manifest.returncode, 2, "Empty manifest cases must fail schema validation")
        self.assertIn("Manifest 'cases' inventory is empty or malformed", res_empty_manifest.stderr)

    def test_5_byte_flipped_fixture_fails(self) -> None:
        """Control 5: Baseline fixture must pass first, then fail after corrupting one byte."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # Copy canonical truth to sandbox fixtures dir
        canon_truth = REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr_ground_truth.json"
        shutil.copy(canon_truth, fix_dir / "km_global_hisnr_ground_truth.json")

        # Generate canonical movie in the sandbox
        res_gen = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--canonical",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertEqual(res_gen.returncode, 0, f"Generator failed: {res_gen.stderr}")

        # Assert valid passing baseline before corruption
        res_baseline = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_baseline.returncode, 0,
                         f"Baseline verification must pass before corruption: {res_baseline.stdout}")

        # Corrupt exactly one byte in the movie file
        movie_path = fix_dir / "km_global_hisnr.mrcs"
        data = bytearray(movie_path.read_bytes())
        data[2048] ^= 0x01
        movie_path.write_bytes(data)

        res_corrupt = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--manifest", str(CANONICAL_MANIFEST),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_corrupt.returncode, 1, "Byte-flipped fixture must fail verification")
        self.assertIn("MISMATCH", res_corrupt.stdout)

    def test_6_trusted_git_lookup_and_tampered_disk_manifest(self) -> None:
        """Control 6: Git-backed verification rejects tampered disk manifest and fails closed on invalid ref."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # Copy canonical truth
        canon_truth = REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr_ground_truth.json"
        shutil.copy(canon_truth, fix_dir / "km_global_hisnr_ground_truth.json")

        # Generate clean case
        res_gen = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--canonical",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertEqual(res_gen.returncode, 0)

        # Tamper the movie bytes to make it noncanonical
        movie_path = fix_dir / "km_global_hisnr.mrcs"
        corrupt_bytes = bytearray(movie_path.read_bytes())
        corrupt_bytes[1024] ^= 0x02
        movie_path.write_bytes(corrupt_bytes)
        corrupt_sha = hashlib.sha256(corrupt_bytes).hexdigest()

        # Attacker writes a tampered adjacent disk manifest matching the corrupt bytes
        tampered_manifest = fix_dir / "MANIFEST.json"
        tampered_manifest.write_text(json.dumps({
            "cases": {
                "km_global_hisnr": {
                    "movie_sha256": corrupt_sha,
                    "movie_bytes": len(corrupt_bytes),
                    "ground_truth_sha256": hashlib.sha256(
                        (fix_dir / "km_global_hisnr_ground_truth.json").read_bytes()).hexdigest(),
                }
            }
        }))

        # If verified against the default git ref (HEAD), it MUST FAIL despite adjacent tampered manifest
        res_git = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--repo", str(REPO_ROOT),
             "--ref", "HEAD",
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_git.returncode, 1, "Default git-backed verification must reject tampered fixture")
        self.assertIn("MISMATCH", res_git.stdout)

        # 6B: An invalid git ref MUST fail closed, not silently degrade to disk manifest
        res_invalid_ref = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(fix_dir),
             "--repo", str(REPO_ROOT),
             "--ref", "nonexistent_ref_12345",
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_invalid_ref.returncode, 2, "Invalid git ref must fail closed")
        self.assertIn("Failed to load trusted manifest from git ref", res_invalid_ref.stderr)

        # 6C: In a source archive with proven absence of .git, fallback to trusted disk manifest is permitted
        archive_root = self.sandbox / "source_archive"
        archive_root.mkdir()
        archive_km = archive_root / "test-data" / "known_motion"
        archive_km.mkdir(parents=True)

        # Missing disk manifest in archive fails closed
        res_archive_missing = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(archive_km),
             "--repo", str(archive_root)],
            capture_output=True, text=True
        )
        self.assertEqual(res_archive_missing.returncode, 2, "Archive without manifest must fail closed")
        self.assertIn("Source archive contains no git metadata and trusted disk manifest is missing", res_archive_missing.stderr)

        # When disk manifest is present in archive, verification succeeds and reports archive provenance
        shutil.copy(CANONICAL_MANIFEST, archive_km / "MANIFEST.json")
        shutil.copy(REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr_ground_truth.json",
                    archive_km / "km_global_hisnr_ground_truth.json")
        res_archive_gen = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--canonical",
             "--outdir", str(archive_km)],
            capture_output=True, text=True
        )
        self.assertEqual(res_archive_gen.returncode, 0)

        res_archive_verify = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(archive_km),
             "--repo", str(archive_root),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_archive_verify.returncode, 0, f"Archive verification should pass: {res_archive_verify.stderr}")
        self.assertIn("archive:", res_archive_verify.stdout)

        # Corrupted fixture in archive fails closed
        archive_movie = archive_km / "km_global_hisnr.mrcs"
        corrupted = bytearray(archive_movie.read_bytes())
        corrupted[100] ^= 0x01
        archive_movie.write_bytes(corrupted)
        res_archive_corrupt = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES),
             "--fixtures-dir", str(archive_km),
             "--repo", str(archive_root),
             "--cases", "km_global_hisnr"],
            capture_output=True, text=True
        )
        self.assertEqual(res_archive_corrupt.returncode, 1, "Corrupted fixture in archive must fail verification")
        self.assertIn("MISMATCH", res_archive_corrupt.stdout)

    def test_7_reused_stem_and_canonical_generator_protection(self) -> None:
        """Control 7: Generator protects canonical truth and refuses conflicting stem overwrite."""
        fix_dir = self.sandbox / "fixtures"
        fix_dir.mkdir()

        # Step 1: Generate initial standard case
        res_init = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertEqual(res_init.returncode, 0)

        movie_path = fix_dir / "km_global_hisnr.mrcs"
        star_path = fix_dir / "km_global_hisnr.star"
        truth_path = fix_dir / "km_global_hisnr_ground_truth.json"
        init_movie_bytes = movie_path.read_bytes()
        init_star_bytes = star_path.read_bytes()
        init_truth_bytes = truth_path.read_bytes()

        # Step 2: Regenerating with --refuse-conflicting and conflicting noise-rel must refuse
        # and preserve every prior byte of movie, star, and truth files
        res_conflict = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--noise-rel", "0.5",
             "--refuse-conflicting",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertNotEqual(res_conflict.returncode, 0, "Generator must refuse conflicting parameters")
        self.assertIn("conflicting parameters with existing ground truth", res_conflict.stderr)

        self.assertEqual(movie_path.read_bytes(), init_movie_bytes, "Movie bytes must be preserved on refusal")
        self.assertEqual(star_path.read_bytes(), init_star_bytes, "STAR bytes must be preserved on refusal")
        self.assertEqual(truth_path.read_bytes(), init_truth_bytes, "Truth bytes must be preserved on refusal")

        # Step 3: Canonical mode on modified movie sha in truth must refuse disagreement and preserve files
        truth_data = json.loads(truth_path.read_text())
        truth_data["movie_sha256"] = "0" * 64
        truth_path.write_text(json.dumps(truth_data))
        tampered_truth_bytes = truth_path.read_bytes()

        res_canonical = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--canonical",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertNotEqual(res_canonical.returncode, 0, "Canonical mode must fail on disagreement")
        self.assertIn("Canonical mode disagreement", res_canonical.stderr)

        self.assertEqual(movie_path.read_bytes(), init_movie_bytes, "Movie bytes must be preserved on canonical disagreement")
        self.assertEqual(star_path.read_bytes(), init_star_bytes, "STAR bytes must be preserved on canonical disagreement")
        self.assertEqual(truth_path.read_bytes(), tampered_truth_bytes, "Truth bytes must be preserved on canonical disagreement")


if __name__ == "__main__":
    unittest.main()
