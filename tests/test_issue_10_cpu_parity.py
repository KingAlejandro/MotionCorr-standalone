#!/usr/bin/env python3
"""
Test Suite for Issue #10: CPU Optimization & Parity Verification.
Validates that FFTW plan caching and hot loop optimizations maintain
strict bit-exact numerical parity and deterministic multi-threaded execution.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestIssue10CpuParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.binary = cls.repo_root / "build" / "motioncorr"
        cls.fixtures_dir = cls.repo_root / "test-data" / "fixtures"
        cls.synthetic_dir = cls.repo_root / "test-data" / "synthetic"
        cls.comparator = cls.repo_root / "tools" / "compare_motioncorr.py"

        if not cls.binary.is_file():
            raise unittest.SkipTest(f"Binary not found at {cls.binary}")

    def test_multi_threaded_determinism(self):
        """Test that running with 1 thread vs 4 threads produces bit-exact identical outputs."""
        fixture_star = self.fixtures_dir / "synthetic_128x128_8frames.star"
        if not fixture_star.is_file():
            self.skipTest(f"Fixture star not found at {fixture_star}")

        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "out_t1"
            out4 = Path(tmpdir) / "out_t4"
            out1.mkdir()
            out4.mkdir()

            cmd_base = [
                str(self.binary.resolve()),
                "--i", str(fixture_star.resolve()),
                "--use_own",
                "--dose_weighting",
                "--dose_per_frame", "1.0",
                "--voltage", "300",
                "--angpix", "1.0",
                "--patch_x", "3",
                "--patch_y", "3",
                "--bfactor", "150",
            ]

            # Run 1 thread
            cmd1 = cmd_base + ["--o", str(out1.resolve()) + "/", "--j", "1"]
            res1 = subprocess.run(cmd1, cwd=str(self.fixtures_dir), capture_output=True, text=True)
            self.assertEqual(res1.returncode, 0, f"Run 1 thread failed: {res1.stderr}")

            # Run 4 threads
            cmd4 = cmd_base + ["--o", str(out4.resolve()) + "/", "--j", "4"]
            res4 = subprocess.run(cmd4, cwd=str(self.fixtures_dir), capture_output=True, text=True)
            self.assertEqual(res4.returncode, 0, f"Run 4 threads failed: {res4.stderr}")

            # Compare outputs using compare_motioncorr.py under exact gate
            star1 = out1 / "synthetic_128x128_8frames.star"
            star4 = out4 / "synthetic_128x128_8frames.star"
            mrc1 = out1 / "synthetic_128x128_8frames.mrc"
            mrc4 = out4 / "synthetic_128x128_8frames.mrc"

            self.assertTrue(star1.is_file(), f"Missing t=1 star file in {out1}")
            self.assertTrue(star4.is_file(), f"Missing t=4 star file in {out4}")
            self.assertTrue(mrc1.is_file(), f"Missing t=1 mrc file in {out1}")
            self.assertTrue(mrc4.is_file(), f"Missing t=4 mrc file in {out4}")

            cmp_cmd = [
                "python3",
                str(self.comparator),
                "--test-star", str(star4),
                "--ref-star", str(star1),
                "--test-mrc", str(mrc4),
                "--ref-mrc", str(mrc1),
                "--gate", "exact",
            ]
            res_cmp = subprocess.run(cmp_cmd, capture_output=True, text=True)
            self.assertEqual(
                res_cmp.returncode,
                0,
                f"Determinism comparison failed between t=1 and t=4:\n{res_cmp.stdout}\n{res_cmp.stderr}",
            )

    def test_reference_baseline_exact_match(self):
        """Test that synthetic_movie.tiff output exactly matches RELION reference baseline."""
        synth_movie = self.synthetic_dir / "synthetic_movie.tiff"
        expected_mrc = self.synthetic_dir / "expected" / "synthetic_movie.mrc"
        expected_star = self.synthetic_dir / "expected" / "synthetic_movie.star"

        if not synth_movie.is_file() or not expected_mrc.is_file() or not expected_star.is_file():
            self.skipTest("Synthetic test movie and reference baseline not present")

        with tempfile.TemporaryDirectory() as tmpdir:
            test_out = Path(tmpdir)
            cmd_run = [
                str(self.binary.resolve()),
                "--i", str(synth_movie.resolve()),
                "--o", str(test_out.resolve()),
                "--use_own",
                "--j", "4",
                "--dose_weighting",
                "--dose_per_frame", "1.0",
                "--voltage", "300",
                "--angpix", "1.0",
                "--patch_x", "3",
                "--patch_y", "3",
                "--bfactor", "150",
            ]
            res = subprocess.run(cmd_run, cwd=str(test_out), capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Run failed: {res.stderr}")

            out_mrc_list = list(test_out.glob("**/synthetic_movie.mrc"))
            out_star_list = list(test_out.glob("**/synthetic_movie.star"))

            self.assertTrue(len(out_mrc_list) > 0, f"Could not find synthetic_movie.mrc in {test_out}")
            self.assertTrue(len(out_star_list) > 0, f"Could not find synthetic_movie.star in {test_out}")

            out_mrc = out_mrc_list[0]
            out_star = out_star_list[0]

            cmp_cmd = [
                "python3",
                str(self.comparator),
                "--test-star", str(out_star),
                "--ref-star", str(expected_star),
                "--test-mrc", str(out_mrc),
                "--ref-mrc", str(expected_mrc),
                "--gate", "exact",
            ]
            res_cmp = subprocess.run(cmp_cmd, capture_output=True, text=True)
            self.assertEqual(
                res_cmp.returncode,
                0,
                f"Baseline exact gate comparison failed:\n{res_cmp.stdout}\n{res_cmp.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
