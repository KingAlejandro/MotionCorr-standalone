#!/usr/bin/env python3
"""Bounded CPU contracts and negative controls, no MotionCorr/GPU required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

import check_motion_diagnostics as check

gen = check.gen


class Diagnostics(unittest.TestCase):
    def test_all_mapping_closures(self):
        for name in gen.CASES:
            with self.subTest(name=name):
                self.assertLess(gen.validate_mapping(gen.recipe(name))["forward_inverse_max_px"], 1e-10)

    def test_independent_scalar_affine_inverse(self):
        r = gen.recipe("affine")
        p = np.array([[4.5, 21.3], [119., 70.]])
        for f in range(r["frames"]):
            t = f/4
            aa, bb, cc, dd = 1+.012*t, -.008*t, .006*t, 1-.010*t
            xx = p[:, 0]-3.25*t + .012*t*64 - .008*t*48
            yy = p[:, 1]+2.125*t + .006*t*64 - .010*t*48
            want = np.stack(((dd*xx-bb*yy)/(aa*dd-bb*cc), (aa*yy-cc*xx)/(aa*dd-bb*cc)), axis=-1)
            np.testing.assert_allclose(gen.inverse(r, f, p), want, atol=1e-13)

    def test_negation_is_not_an_inverse(self):
        r = gen.recipe("affine")
        p = gen.grid(r)
        # The historical pattern B(p-M(p)) does not implement B(F^-1(p)).
        naive = p-(gen.forward(r, 4, p)-p)
        residual = gen.forward(r, 4, naive)-p
        self.assertGreater(np.linalg.norm(residual, axis=-1).max(), .03)

    def test_integer_pixels_independently(self):
        r = gen.recipe("integer")
        movie, _, truth = gen.render(r)
        # Interior values must move by (+f,-2f), with no interpolator involved.
        np.testing.assert_array_equal(movie[3, 12:70, 12:100], movie[0, 18:76, 9:97])
        np.testing.assert_array_equal(truth[3, 20, 20], [-3, 6])

    def test_truth_and_mutants(self):
        r = gen.recipe("affine")
        movie, target, truth = gen.render(r)
        def run(field):
            return check.evaluate(r, movie, target, truth, field, [12, 84, 12, 116])
        good = run(truth)
        self.assertEqual(good["accuracy_status"], "PASS")
        self.assertLess(good["signal"]["true_motion_bilinear"]["rmse"], good["signal"]["uncorrected"]["rmse"])
        self.assertEqual(good["signal"]["estimated_motion_bilinear"],
                         good["signal"]["true_motion_bilinear"])
        zero = run(np.zeros_like(truth))
        self.assertEqual(zero["signal"]["estimated_motion_bilinear"],
                         zero["signal"]["uncorrected"])
        self.assertGreater(run(-truth)["signal"]["estimated_motion_bilinear"]["rmse"],
                           good["signal"]["estimated_motion_bilinear"]["rmse"])
        for bad in [-truth, truth[..., ::-1], truth*.885, truth+1,
                    np.roll(truth, 1, axis=0)]:
            with self.subTest(mutant=float(bad.sum())):
                self.assertEqual(run(bad)["accuracy_status"], "FAIL")
        bad = truth.copy()
        bad[2] += (gen.grid(r)-[64, 48])*.05
        self.assertEqual(run(bad)["accuracy_status"], "FAIL")
        for bad in [truth*np.nan, truth+200, truth[:, :-1]]:
            with self.assertRaises(ValueError):
                run(bad)

    def test_bilinear_independent_plane(self):
        y, x = np.mgrid[:20, :30]
        p = np.array([[3.2, 4.7], [12.6, 17.2]])
        np.testing.assert_allclose(check.sample(2*x+3*y+4, p), 2*p[:, 0]+3*p[:, 1]+4)

    def test_ambiguity_and_noise_roles(self):
        for name in ["flat", "repeated", "noisy"]:
            r = gen.recipe(name)
            movie, target, truth = gen.render(r)
            result = check.evaluate(r, movie, target, truth, truth, [12, 84, 12, 116])
            self.assertEqual(result["role"], "characterization")
            if name != "noisy":
                self.assertEqual(result["accuracy_status"], "UNIDENTIFIABLE")
            if name == "flat":
                self.assertIsNone(result["signal"]["true_motion_bilinear"]["contrast_normalized_rmse"])

    def test_artifacts_cli_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root/"a", root/"b"
            ma, mb = gen.generate(a), gen.generate(b)
            self.assertEqual(ma, mb)
            with self.assertRaises(FileExistsError):
                gen.generate(a)
            result = check.check_case(a, "affine", a/"affine_field.npy")
            self.assertEqual(result["accuracy_status"], "PASS")
            # A hand-authored polynomial STAR exercises the existing adapter,
            # including normalized x/y coordinates and the 1-based frame origin.
            text = "data_general\n_rlnImageSizeX 128\n_rlnImageSizeY 96\n_rlnImageSizeZ 5\n_rlnMicrographOriginalPixelSize 0.885\n_rlnMicrographStartFrame 1\n_rlnMicrographBinning 1\n_rlnMotionModelVersion 1\n"
            text += "data_global_shift\nloop_\n_rlnMicrographFrameNumber #1\n_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n"
            text += "".join(f"{f+1} {-3.25*f/4} {2.125*f/4}\n" for f in range(5))
            text += "data_local_motion_model\nloop_\n_rlnMotionModelCoeffsIdx #1\n_rlnMotionModelCoeff #2\n"
            coeff = np.zeros(36)
            coeff[[3, 9, 21, 27]] = [-.384, .192, -.192, .24]
            text += "".join(f"{i} {v}\n" for i, v in enumerate(coeff))
            (root/"candidate.star").write_text(text)
            star_result = check.check_case(a, "affine", root/"candidate.star")
            self.assertLess(star_result["field_px"]["max"], 1e-12)
            # Malformed identifiers must be input errors, never wrapped indices
            # or ignored duplicate coefficients in the permissive legacy reader.
            star_command = [sys.executable, str(Path(check.__file__)), "--fixtures", str(a),
                            "--case", "affine", "--candidate", str(root/"malformed.star"),
                            "--json", str(root/"malformed.json")]
            variants = [
                text.replace("5 -3.25 2.125", "0 -3.25 2.125"),
                text.replace("5 -3.25 2.125", "6 -3.25 2.125"),
                text.replace("5 -3.25 2.125", "4 -3.25 2.125"),
                text.replace("5 -3.25 2.125\n", ""),
                text.replace("1 0.0\n", "0 0.0\n"),
                text.replace("35 0.0", "36 0.0"),
                text.replace("35 0.0", "-1 0.0"),
                text.replace("35 0.0\n", ""),
                text.replace("_rlnImageSizeZ 5", "_rlnImageSizeZ 1"),
                text.replace("_rlnImageSizeZ 5", "_rlnImageSizeZ 9999999999"),
            ]
            for malformed in variants:
                (root/"malformed.star").write_text(malformed)
                proc = subprocess.run(star_command, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("INPUT ERROR:", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
            # Published-pixel accuracy is distinct from a correct field.
            gen.write_mrc_stack(root/"sum.mrc", np.zeros((1, 96, 128)), .885)
            pixels = check.check_case(a, "affine", a/"affine_field.npy", root/"sum.mrc")
            self.assertEqual(pixels["accuracy_status"], "PASS")
            self.assertGreater(pixels["signal"]["published_sum_divided_by_frames"]["rmse"], 90)
            self.assertEqual(pixels["application_consistency_status"], "NOT_TESTED")
            command = [sys.executable, str(Path(check.__file__)), "--fixtures", str(a), "--case", "affine", "--candidate", str(a/"affine_field.npy"), "--json", str(root/"result.json")]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            bad = np.load(a/"affine_field.npy") + 1
            np.save(root/"bad.npy", bad)
            command[command.index("--candidate")+1] = str(root/"bad.npy")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            (a/"affine.mrcs").write_bytes(b"corrupt")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
