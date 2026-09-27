#!/usr/bin/env python3
"""Fast negative controls for the checker verdict; no MotionCorr executable needed."""
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

import motion_field as mf

CHECKER = Path(__file__).with_name("check_known_motion.py")


def write_mrc(path, pixels):
    data = np.asarray(pixels, dtype="<f4")
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, data.shape[2], data.shape[1], data.shape[0], 2)
    path.write_bytes(header + data.tobytes())


class VerdictControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        nx, ny, frames = 32, 24, 3
        self.star = mf.MotionStar(
            path=self.work / "still.star", nx=nx, ny=ny, n_frames=frames,
            first_frame=1, pixel_size=0.885, binning=1.0, motion_model_version=0,
            global_shift_x=np.zeros(frames), global_shift_y=np.zeros(frames),
            general={"rlnImageSizeX": str(nx), "rlnImageSizeY": str(ny),
                     "rlnImageSizeZ": str(frames), "rlnMicrographStartFrame": "1",
                     "rlnMicrographOriginalPixelSize": "0.885",
                     "rlnMicrographBinning": "1", "rlnMotionModelVersion": "0"})
        mf.write_motion_star(self.star, self.star.path)
        gt = {"case": "still", "geometry": {"nx": nx, "ny": ny, "n_frames": frames,
                                              "pixel_size_angstrom": 0.885},
              "grid": {"x": [8, 24], "y": [6, 18]},
              "expected_applied_field": np.zeros((frames, 2, 2)).tolist()}
        self.truth = self.work / "truth.json"
        self.truth.write_text(json.dumps(gt))
        self.movie = self.work / "movie.mrcs"
        self.sum = self.work / "sum.mrc"
        write_mrc(self.movie, np.ones((frames, ny, nx)))
        write_mrc(self.sum, np.full((1, ny, nx), frames))

    def run_checker(self, *extra, witness=True):
        report = self.work / "report.json"
        report.unlink(missing_ok=True)
        cmd = [sys.executable, str(CHECKER), "--ground-truth", str(self.truth),
               "--motion-star", str(self.star.path), "--json", str(report), "--quiet"]
        if witness:
            cmd += ["--movie", str(self.movie), "--summed-image", str(self.sum)]
        result = subprocess.run(cmd + list(extra), capture_output=True, text=True)
        return result, json.loads(report.read_text()) if report.exists() else {}

    def test_consistent_sum_passes(self):
        result, report = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["self_consistency"]["status"], "PASS")
        self.assertEqual(report["gates"]["n_failed"], 0)

    def test_wrong_applied_pixels_fail_despite_exact_reported_field(self):
        write_mrc(self.sum, np.full((1, 24, 32), 4))
        result, report = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(report["status"], "FAIL")
        failed = [c["name"] for c in report["gates"]["checks"] if not c["pass"]]
        self.assertEqual(failed, ["applied_image_self_consistency"])

    def test_nonfinite_pixels_cannot_pass(self):
        for bad in (np.nan, np.inf, -np.inf):
            with self.subTest(value=bad):
                pixels = np.full((1, 24, 32), 3.0)
                pixels[0, 0, 0] = bad
                write_mrc(self.sum, pixels)
                result, report = self.run_checker()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(report["status"], "ERROR")

    def test_nonfinite_shifts_cannot_pass(self):
        self.star.global_shift_y[1] = np.nan
        mf.write_motion_star(self.star, self.star.path)
        result, report = self.run_checker()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(report["status"], "ERROR")

    def test_zero_reference_has_no_finite_relative_witness(self):
        write_mrc(self.movie, np.zeros((3, 24, 32)))
        write_mrc(self.sum, np.zeros((1, 24, 32)))
        result, report = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(report["status"], "FAIL")

    def test_witness_requires_both_paths(self):
        for option, path in (("--movie", self.movie), ("--summed-image", self.sum)):
            with self.subTest(option=option):
                result, _ = self.run_checker(option, str(path), witness=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("must be provided together", result.stderr)

    def test_wrong_sum_shape_is_input_error(self):
        write_mrc(self.sum, np.ones((2, 24, 32)))
        result, report = self.run_checker()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(report["status"], "ERROR")

    def test_dose_difference_is_mandatory(self):
        changed = self.star.copy()
        changed.global_shift_y[1] = 1e-6
        path = self.work / "dose.star"
        mf.write_motion_star(changed, path)
        result, report = self.run_checker("--compare-star", str(path))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(report["dose_weighting_invariance"]["status"], "DIFFERS")


if __name__ == "__main__":
    unittest.main()
