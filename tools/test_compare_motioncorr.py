"""Regression checks for false passes in the MotionCorr acceptance gate."""

import copy
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from compare_motioncorr import (
    compare_images,
    compare_star_fields,
    compare_trajectories,
    discover_output_files,
    extract_global_shifts,
    parse_mrc,
    parse_star_file,
)


FIXTURES = Path(__file__).resolve().parents[1] / "test-data" / "fixtures"


class ComparatorGateTests(unittest.TestCase):
    def run_gate(self, *args):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("compare_motioncorr.py")), *map(str, args), "--json"],
            text=True, capture_output=True,
        )
        return result.returncode, json.loads(result.stdout)

    def test_star_loop_schema_and_metadata_value_changes_fail(self):
        reference = parse_star_file(FIXTURES / "reference_output" / "synthetic_128x128_8frames.star")
        test = copy.deepcopy(reference)
        test["global_shift"]["labels"][1] = "_rlnWrongShiftColumn"
        result = compare_star_fields(reference, test)
        self.assertGreater(result["num_differences"], 0)

        test = copy.deepcopy(reference)
        test["general"]["fields"]["_rlnVoltage"] = "200.000000"
        result = compare_star_fields(reference, test, compare_motion_values=False)
        self.assertGreater(result["num_differences"], 0)

    def test_exact_checks_loop_values_but_relaxed_checks_structure(self):
        reference = parse_star_file(FIXTURES / "reference_output" / "synthetic_128x128_8frames.star")
        test = copy.deepcopy(reference)
        test["global_shift"]["rows"][2][1] = "-0.500000"
        self.assertGreater(compare_star_fields(reference, test)["num_differences"], 0)
        self.assertEqual(
            compare_star_fields(reference, test, compare_motion_values=False)["num_differences"], 0
        )

    def test_duplicate_and_nonfinite_shifts_fail(self):
        reference = [(1, 0.0, 0.0), (2, 1.0, 0.0)]
        self.assertIn("duplicate", compare_trajectories(reference, reference + [reference[1]])["error"])
        self.assertIn("Non-finite", compare_trajectories(reference, [(1, 0.0, 0.0), (2, float("nan"), 0.0)])["error"])

    def test_malformed_shift_row_fails(self):
        test = parse_star_file(FIXTURES / "reference_output" / "synthetic_128x128_8frames.star")
        test["global_shift"]["rows"][0].pop()
        with self.assertRaisesRegex(ValueError, "Malformed"):
            extract_global_shifts(test)

    def test_mrc_payload_and_nonfinite_pixels_fail(self):
        source = FIXTURES / "reference_output" / "synthetic_128x128_8frames.mrc"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "truncated.mrc"
            path.write_bytes(source.read_bytes()[:-4])
            with self.assertRaisesRegex(ValueError, "payload size"):
                parse_mrc(path)

            raw = bytearray(source.read_bytes())
            struct.pack_into("<f", raw, 1024, float("nan"))
            path.write_bytes(raw)
            ref_header, ref_pixels, ref_raw = parse_mrc(source)
            test_header, test_pixels, test_raw = parse_mrc(path)
            result = compare_images(ref_pixels, test_pixels, ref_header, test_header, ref_raw, test_raw)
            self.assertIn("Non-finite", result["error"])

    def test_non_timestamp_label_difference_is_detected(self):
        source = FIXTURES / "reference_output" / "synthetic_128x128_8frames.mrc"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed-label.mrc"
            raw = bytearray(source.read_bytes())
            raw[224] = ord("X")
            path.write_bytes(raw)
            ref_header, ref_pixels, ref_raw = parse_mrc(source)
            test_header, test_pixels, test_raw = parse_mrc(path)
            result = compare_images(ref_pixels, test_pixels, ref_header, test_header, ref_raw, test_raw)
            self.assertEqual(result["normalized_label_diff_bytes"], 1)

    def test_multiple_movie_outputs_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ("a.mrc", "b.mrc"):
                (Path(temp) / name).write_bytes(b"")
            mrc, _, errors = discover_output_files(Path(temp))
            self.assertIsNone(mrc)
            self.assertTrue(any("Multiple corrected MRCs" in error for error in errors))

    def test_cli_rejects_static_metadata_change(self):
        source = FIXTURES / "reference_output" / "synthetic_128x128_8frames.star"
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed.star"
            changed.write_text(source.read_text().replace("300.000000", "200.000000", 1))
            code, report = self.run_gate("--ref-star", source, "--test-star", changed, "--gate", "relaxed")
            self.assertEqual(code, 1)
            self.assertEqual(report["overall_status"], "FAIL")
            self.assertFalse(report["checks"]["star_fields"]["passed"])

    def test_cli_rejects_absolute_rmse_even_when_relative_error_is_small(self):
        source = FIXTURES / "reference_output" / "synthetic_128x128_8frames.mrc"
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed.mrc"
            raw = bytearray(source.read_bytes())
            for offset in range(1024, len(raw), 4):
                value = struct.unpack_from("<f", raw, offset)[0]
                struct.pack_into("<f", raw, offset, value + 0.03)
            changed.write_bytes(raw)
            code, report = self.run_gate("--ref-mrc", source, "--test-mrc", changed, "--gate", "relaxed")
            self.assertEqual(code, 1)
            self.assertFalse(report["coverage"]["complete"])
            image = report["checks"]["corrected_image"]
            self.assertGreater(image["rmse"], 0.02)
            self.assertLess(image["relative_rmse"], 0.001)

    def test_cli_rejects_nonfinite_tolerance(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("compare_motioncorr.py")),
             "--max-shift-err", "nan"],
            text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite and nonnegative", result.stderr)


if __name__ == "__main__":
    unittest.main()
