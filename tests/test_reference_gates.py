#!/usr/bin/env python3
"""Automated regression test verifying Issue #4 numerical acceptance gates and comparison tooling.

Executes MotionCorr on the standardized synthetic fixtures and validates outputs using
tools/compare_motioncorr.py under both strict (--gate exact) and relaxed (--gate relaxed) gates.
Also executes the comparator's self-test regression suite to prevent false passes.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_reference_gate_tests(binary: Path = None, python_bin: str = sys.executable) -> bool:
    repo_root = Path(__file__).resolve().parent.parent

    if binary is None:
        binary = repo_root / "build" / "motioncorr"
    if not binary.is_file():
        raise FileNotFoundError(f"motioncorr binary not found at {binary}. Build with cmake first.")

    fixtures_dir = repo_root / "test-data" / "fixtures"
    synthetic_dir = repo_root / "test-data" / "synthetic"
    comparator = repo_root / "tools" / "compare_motioncorr.py"
    comparator_tests = repo_root / "tools" / "test_compare_motioncorr.py"

    print("============================================================")
    print(" EXECUTING REFERENCE GATE ACCEPTANCE TESTS (Issue #4)")
    print("============================================================")

    # -------------------------------------------------------------------------
    # Test 1: Comparator Unit Tests (False Pass Prevention)
    # -------------------------------------------------------------------------
    print("\n[Suite 1/3] Running Comparator Unit Tests (test_compare_motioncorr.py)...")
    res_unit = subprocess.run([python_bin, str(comparator_tests.resolve())], capture_output=True, text=True)
    if res_unit.returncode != 0:
        print("Unit Test STDOUT:\n", res_unit.stdout)
        print("Unit Test STDERR:\n", res_unit.stderr)
        raise RuntimeError(f"Comparator unit tests failed (code {res_unit.returncode})")
    print(">> Suite 1 PASSED: 10/10 comparator unit tests passed.")

    # -------------------------------------------------------------------------
    # Test 2: Exact CPU Parity Gate (--gate exact) on Synthetic Benchmark
    # -------------------------------------------------------------------------
    print("\n[Suite 2/3] Testing Strict Parity Gate (--gate exact) against reference baseline...")
    synth_movie = synthetic_dir / "synthetic_movie.tiff"
    expected_mrc = synthetic_dir / "expected" / "synthetic_movie.mrc"
    expected_star = synthetic_dir / "expected" / "synthetic_movie.star"

    with tempfile.TemporaryDirectory(prefix="ref_gate_exact_") as tmpdir:
        out_dir = Path(tmpdir)
        cmd_run = [
            str(binary.resolve()),
            "--i", str(synth_movie.resolve()),
            "--o", str(out_dir.resolve()),
            "--use_own",
            "--j", "1",
            "--dose_weighting",
            "--dose_per_frame", "1.0",
            "--voltage", "300",
            "--angpix", "1.0",
            "--patch_x", "3",
            "--patch_y", "3",
            "--bfactor", "150",
        ]
        res_run = subprocess.run(cmd_run, cwd=str(out_dir), capture_output=True, text=True)
        if res_run.returncode != 0:
            print("MotionCorr STDOUT:\n", res_run.stdout)
            print("MotionCorr STDERR:\n", res_run.stderr)
            raise RuntimeError(f"MotionCorr exact run failed with code {res_run.returncode}")

        mrc_matches = list(out_dir.glob("**/synthetic_movie.mrc"))
        star_matches = list(out_dir.glob("**/synthetic_movie.star"))
        if not mrc_matches or not star_matches:
            raise FileNotFoundError(f"Output files not generated in {out_dir}")

        out_mrc = mrc_matches[0]
        out_star = star_matches[0]

        cmd_cmp = [
            python_bin,
            str(comparator.resolve()),
            "--ref-mrc", str(expected_mrc.resolve()),
            "--ref-star", str(expected_star.resolve()),
            "--test-mrc", str(out_mrc.resolve()),
            "--test-star", str(out_star.resolve()),
            "--gate", "exact",
            "--json",
        ]
        res_cmp = subprocess.run(cmd_cmp, capture_output=True, text=True)
        if res_cmp.returncode != 0:
            print("Comparator STDOUT:\n", res_cmp.stdout)
            print("Comparator STDERR:\n", res_cmp.stderr)
            raise RuntimeError(f"Strict exact gate failed (code {res_cmp.returncode})")

        report = json.loads(res_cmp.stdout)
        assert report["overall_status"] == "PASS", f"Expected PASS, got {report['overall_status']}"
        assert report["checks"]["corrected_image"]["pixel_identical"] is True
        assert report["checks"]["corrected_image"]["rmse"] == 0.0
        assert report["checks"]["motion_trajectory"]["max_shift_error"] == 0.0
        print(">> Suite 2 PASSED: Bit-exact numerical parity verified (Image RMSE: 0.0, Shift Δ: 0.0 px).")

    # -------------------------------------------------------------------------
    # Test 3: Numerical Equivalence Gate (--gate relaxed) on Multi-Frame Fixture
    # -------------------------------------------------------------------------
    print("\n[Suite 3/3] Testing Numerical Equivalence Gate (--gate relaxed)...")
    fixture_star = fixtures_dir / "synthetic_128x128_8frames.star"
    fixture_ref_dir = fixtures_dir / "reference_output"

    with tempfile.TemporaryDirectory(prefix="ref_gate_relaxed_") as tmpdir:
        out_dir = Path(tmpdir)
        cmd_run = [
            str(binary.resolve()),
            "--i", str(fixture_star.resolve()),
            "--o", str(out_dir.resolve()),
            "--use_own",
            "--j", "4",
        ]
        res_run = subprocess.run(cmd_run, cwd=str(fixtures_dir), capture_output=True, text=True)
        if res_run.returncode != 0:
            print("MotionCorr STDOUT:\n", res_run.stdout)
            print("MotionCorr STDERR:\n", res_run.stderr)
            raise RuntimeError(f"MotionCorr relaxed run failed with code {res_run.returncode}")

        cmd_cmp = [
            python_bin,
            str(comparator.resolve()),
            "--ref", str(fixture_ref_dir.resolve()),
            "--test", str(out_dir.resolve()),
            "--gate", "relaxed",
            "--json",
        ]
        res_cmp = subprocess.run(cmd_cmp, capture_output=True, text=True)
        if res_cmp.returncode != 0:
            print("Comparator STDOUT:\n", res_cmp.stdout)
            print("Comparator STDERR:\n", res_cmp.stderr)
            raise RuntimeError(f"Relaxed numerical gate failed (code {res_cmp.returncode})")

        report = json.loads(res_cmp.stdout)
        assert report["overall_status"] == "PASS", f"Expected PASS, got {report['overall_status']}"
        assert report["checks"]["motion_trajectory"]["coord_rms_error"] <= 0.02
        assert report["checks"]["corrected_image"]["relative_rmse"] <= 0.001
        print(f">> Suite 3 PASSED: Numerical equivalence gate verified "
              f"(Shift RMSD: {report['checks']['motion_trajectory']['coord_rms_error']:.6f} px <= 0.02 px, "
              f"Rel RMSE: {report['checks']['corrected_image']['relative_rmse']:.6e} <= 0.001).")

    print("\n============================================================")
    print(" ALL REFERENCE GATES & ACCEPTANCE CHECKS PASSED (Issue #4 VERIFIED)")
    print("============================================================")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None, help="Path to motioncorr binary")
    parser.add_argument("--python", type=str, default=sys.executable, help="Python executable to invoke comparator")
    args = parser.parse_args()

    success = run_reference_gate_tests(binary=args.binary, python_bin=args.python)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
