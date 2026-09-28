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
CANONICAL_STAR = REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr.star"


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

        # The integrated suite registers 17 tests: the 13 pre-existing ones, the
        # #72 CiFailClosedControls, the #99 WriteFaults / ImageWriteFaults, and
        # the #98 DefectParser.
        INTEGRATED_SUITE = [
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
            "WriteFaults",
            "ImageWriteFaults",
            "DefectParser",
        ]

        def drop_one(name: str):
            """Collection with exactly one required test removed, and a filler
            added so the count gate cannot be what rejects it.

            Without the filler the short list fails on --min-count first and the
            missing-name branch is never reached, while the required-test list
            echoed in the report still contains the name being asserted on. That
            control would stay green even if the missing-name check were deleted.
            """
            kept = [t for t in INTEGRATED_SUITE if t != name]
            kept.append("AdditiveFillerTest")
            return kept

        # Case B: a required test is absent, the count gate is satisfied, so the
        # only thing that can reject the collection is the missing-name check.
        for dropped in ("CiFailClosedControls", "WriteFaults", "ImageWriteFaults", "DefectParser"):
            with self.subTest(dropped=dropped):
                names = drop_one(dropped)
                self.assertEqual(len(names), len(INTEGRATED_SUITE),
                                 "filler must keep the collection at the required count")
                res_missing = subprocess.run(
                    [sys.executable, str(VALIDATE_COLLECTION)],
                    input=json.dumps({"kind": "ctestInfo", "version": {"major": 1, "minor": 0},
                                      "tests": [{"name": n} for n in names]}),
                    capture_output=True, text=True
                )
                self.assertEqual(res_missing.returncode, 1,
                                 f"Missing {dropped} must fail validation")
                self.assertIn(f"Missing required test(s): {dropped}", res_missing.stdout,
                              "must be rejected for the missing name, not for the test count")

        # Case C: the complete integrated collection is accepted. Without this the
        # cases above could pass against a validator that rejects everything.
        res_full = subprocess.run(
            [sys.executable, str(VALIDATE_COLLECTION)],
            input=json.dumps({"kind": "ctestInfo", "version": {"major": 1, "minor": 0},
                              "tests": [{"name": n} for n in INTEGRATED_SUITE]}),
            capture_output=True, text=True
        )
        self.assertEqual(res_full.returncode, 0,
                         f"Complete integrated collection must pass:\n{res_full.stdout}")

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
        # Canonical mode treats the .star as a trusted input and refuses to write it, so it
        # must be staged like the truth JSON.
        shutil.copy(CANONICAL_STAR, fix_dir / "km_global_hisnr.star")

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
        # Canonical mode treats the .star as a trusted input and refuses to write it, so it
        # must be staged like the truth JSON.
        shutil.copy(CANONICAL_STAR, fix_dir / "km_global_hisnr.star")

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

        # Step 2: Regenerating with --refuse-conflicting and conflicting noise-rel must refuse
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

        # Step 3: Canonical mode on modified movie bytes must refuse disagreement
        movie_path = fix_dir / "km_global_hisnr.mrcs"
        corrupt_bytes = bytearray(movie_path.read_bytes())
        corrupt_bytes[500] ^= 0x01
        truth_path = fix_dir / "km_global_hisnr_ground_truth.json"
        truth_data = json.loads(truth_path.read_text())
        truth_data["movie_sha256"] = "0" * 64
        truth_path.write_text(json.dumps(truth_data))

        res_canonical = subprocess.run(
            [sys.executable, str(GENERATOR),
             "--case", "km_global_hisnr",
             "--canonical",
             "--outdir", str(fix_dir)],
            capture_output=True, text=True
        )
        self.assertNotEqual(res_canonical.returncode, 0, "Canonical mode must fail on disagreement")
        self.assertIn("Canonical mode disagreement", res_canonical.stderr)


    def test_8_canonical_star_input_is_immutable(self) -> None:
        """Control 8: STAR metadata drift that leaves the pixels untouched must fail closed.

        A change to the optics template -- pixel size, voltage, or the movie reference --
        does not move a single pixel, so the movie digest cannot see it. Before this control
        the canonical run rewrote the committed .star in place and the manifest carried no
        STAR digest, so the known-motion gates could consume freshly generated metadata under
        a green verification. Both halves are covered here: the generator must refuse and
        leave the committed file alone, and the verifier must reject a STAR tampered on disk.
        """
        def staged_fixture_dir(name: str) -> Path:
            d = self.sandbox / name
            d.mkdir()
            shutil.copy(REPO_ROOT / "test-data" / "known_motion" / "km_global_hisnr_ground_truth.json",
                        d / "km_global_hisnr_ground_truth.json")
            shutil.copy(CANONICAL_STAR, d / "km_global_hisnr.star")
            return d

        def run_generator(generator: Path, outdir: Path):
            return subprocess.run(
                [sys.executable, str(generator), "--case", "km_global_hisnr",
                 "--canonical", "--outdir", str(outdir)],
                capture_output=True, text=True)

        committed_star_bytes = CANONICAL_STAR.read_bytes()

        # 8A baseline: the unmutated maintained generator accepts the committed STAR, and
        # leaves it byte-identical. Without this, the mutation cases below could pass against
        # a generator that refuses everything.
        base_dir = staged_fixture_dir("star_base")
        res_base = run_generator(GENERATOR, base_dir)
        self.assertEqual(res_base.returncode, 0,
                         f"Unmutated canonical run must succeed: {res_base.stderr}")
        self.assertEqual((base_dir / "km_global_hisnr.star").read_bytes(), committed_star_bytes,
                         "Canonical mode must leave the committed STAR byte-identical")

        # 8B: each optics mutation is applied to a copy of the maintained generator, not to a
        # stub, so reverting the production policy makes these cases fail.
        mutations = {
            "pixel_size": ("PIXEL_SIZE = 0.885", "PIXEL_SIZE = 1.000"),
            "voltage": ("VOLTAGE = 300.0", "VOLTAGE = 200.0"),
            "movie_reference": ("{movie} 1", "unrelated_movie.mrcs 1"),
        }
        for label, (needle, replacement) in mutations.items():
            with self.subTest(mutation=label):
                src = GENERATOR.read_text()
                self.assertIn(needle, src, f"mutation anchor {needle!r} no longer present")
                mutated = self.sandbox / f"generator_{label}.py"
                mutated.write_text(src.replace(needle, replacement, 1))

                out_dir = staged_fixture_dir(f"star_{label}")
                res = run_generator(mutated, out_dir)

                self.assertNotEqual(res.returncode, 0,
                                    f"{label} mutation must fail canonical generation")
                self.assertIn("STAR disagreement", res.stderr + res.stdout,
                              f"{label} must be rejected for the STAR, not incidentally")
                # The pixels are unaffected, so the movie digest cannot be what caught it.
                self.assertNotIn("generated movie sha256", res.stderr + res.stdout,
                                 f"{label} changes no pixel; the movie check must not be the detector")
                self.assertEqual((out_dir / "km_global_hisnr.star").read_bytes(),
                                 committed_star_bytes,
                                 f"{label} must leave the committed STAR unmodified on disk")

        # 8C: the generator can be bypassed entirely (CI runs the gates with --no-regenerate),
        # so the verifier must independently reject a STAR altered on disk.
        res_clean = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES), "--fixtures-dir", str(base_dir),
             "--manifest", str(CANONICAL_MANIFEST), "--cases", "km_global_hisnr"],
            capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0,
                         f"Baseline must verify before tampering: {res_clean.stdout}")

        tampered = base_dir / "km_global_hisnr.star"
        tampered.write_text(tampered.read_text().replace("0.885000", "1.000000"))
        res_tampered = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES), "--fixtures-dir", str(base_dir),
             "--manifest", str(CANONICAL_MANIFEST), "--cases", "km_global_hisnr"],
            capture_output=True, text=True)
        self.assertEqual(res_tampered.returncode, 1, "Tampered STAR must fail verification")
        self.assertIn("STAR input hash MISMATCH", res_tampered.stdout,
                      "must be rejected for the STAR digest specifically")

        # 8D: a manifest with no star_sha256 must be rejected as malformed rather than
        # silently skipping the STAR check.
        legacy = json.loads(CANONICAL_MANIFEST.read_text())
        for spec in legacy["cases"].values():
            spec.pop("star_sha256", None)
        legacy_path = self.sandbox / "legacy_manifest.json"
        legacy_path.write_text(json.dumps(legacy))
        res_legacy = subprocess.run(
            [sys.executable, str(VERIFY_FIXTURES), "--fixtures-dir", str(base_dir),
             "--manifest", str(legacy_path), "--cases", "km_global_hisnr"],
            capture_output=True, text=True)
        self.assertEqual(res_legacy.returncode, 2,
                         "A manifest without star_sha256 must fail schema validation")
        self.assertIn("star_sha256", res_legacy.stderr)


if __name__ == "__main__":
    unittest.main()
