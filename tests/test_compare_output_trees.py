#!/usr/bin/env python3
"""Negative controls for the Issue #85 lane C output-tree validator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

SCRIPT = Path(__file__).resolve().parents[1] / "docs" / "issue85_laneC" / "compare_output_trees.py"
SPEC = importlib.util.spec_from_file_location("compare_output_trees", SCRIPT)
compare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = compare
SPEC.loader.exec_module(compare)


class TestOutputTreeComparator(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root / "base"
        self.candidate = self.root / "candidate"
        self.manifest = {
            "schema_version": 1,
            "movies": ["Movies/a.tiff", "Movies/b.tiff"],
            "expected_shape_xyz": [4, 3, 1],
            "joint_star": "corrected_micrographs.star",
        }
        self._write_tree(self.base)
        self._write_tree(self.candidate)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_mrc(self, path: Path, *, mode: int = 2, dims=(4, 3, 1),
                   nsymbt: int = 8, payload: Optional[bytes] = None,
                   timestamp: bytes = b"28-Sep-26  15:38:06") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        nx, ny, nz = dims
        header = bytearray(1024)
        struct.pack_into("<4i", header, 0, nx, ny, nz, mode)
        struct.pack_into("<3i", header, 64, 1, 2, 3)
        struct.pack_into("<4f", header, 76, 0.0, 11.0, 5.5, 2.0)
        struct.pack_into("<i", header, 92, nsymbt)
        header[208:212] = b"MAP "
        header[212:216] = b"DA\0\0"
        struct.pack_into("<i", header, 220, 1)
        label = b"Relion    " + timestamp
        header[224:224 + len(label)] = label
        if payload is None:
            payload = struct.pack("<12f", *[float(i) for i in range(12)])
        path.write_bytes(header + b"EXTBYTES"[:nsymbt].ljust(nsymbt, b"X") + payload)

    def _write_tree(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        joint = ["# version 50001", "", "data_micrographs", "", "loop_",
                 "_rlnMicrographName #1", "_rlnMicrographMetadata #2", "_rlnOpticsGroup #3"]
        for movie in self.manifest["movies"]:
            stem = Path(movie).stem
            mrc_rel = Path("Movies") / f"{stem}.mrc"
            star_rel = Path("Movies") / f"{stem}.star"
            self._write_mrc(root / mrc_rel)
            (root / star_rel).write_text(
                "# version 50001\n\ndata_general\n\n"
                f"_rlnMicrographMovieName {movie}\n"
                "_rlnVoltage 200.0\n"
            )
            joint.append(f"{root / mrc_rel} {root / star_rel} 1")
        (root / "corrected_micrographs.star").write_text("\n".join(joint) + "\n")
        (root / "one.log").write_text(f"out={root}\nFull movie wall time: 1.0 s\n")

    def _assert_fails(self, root: Path, needle: str) -> None:
        with self.assertRaises(compare.ValidationError) as caught:
            compare.validate_tree(root, self.manifest)
        self.assertIn(needle, str(caught.exception))

    def test_equal_complete_trees_pass_with_only_timestamp_and_log_timing_differences(self) -> None:
        mrc = self.candidate / "Movies" / "a.mrc"
        self._write_mrc(mrc, timestamp=b"29-Sep-26  02:22:10")
        (self.candidate / "one.log").write_text(
            f"out={self.candidate}\nFull movie wall time: 7.2 s\n")
        report = compare.compare_trees(self.base, self.candidate, self.manifest)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["base"]["movie_count"], 2)
        self.assertEqual(report["base"]["mrc_count"], 2)
        self.assertEqual(report["base"]["star_count"], 3)
        self.assertEqual(report["base"]["pixel_count"], 24)

    def test_products_only_does_not_require_auxiliary_log_inventory(self) -> None:
        (self.candidate / "one.log").unlink()
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertEqual(report["status"], "PASS")
        with self.assertRaises(compare.ValidationError):
            compare.compare_trees(self.base, self.candidate, self.manifest,
                                  compare_auxiliary=True)

    def test_changed_header_field_is_detected(self) -> None:
        path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(path.read_bytes())
        struct.pack_into("<f", raw, 76, 0.25)  # valid, but changed dmin
        path.write_bytes(raw)
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("Movies/a.mrc", report["different_products"])

    def test_changed_pixel_is_detected(self) -> None:
        path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(path.read_bytes())
        raw[1024 + 8 + 4] ^= 1
        path.write_bytes(raw)
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertIn("Movies/a.mrc", report["different_products"])

    def test_changed_star_is_detected(self) -> None:
        path = self.candidate / "Movies" / "a.star"
        path.write_text(path.read_text().replace("200.0", "201.0"))
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertIn("Movies/a.star", report["different_products"])

    def test_missing_required_image_is_rejected(self) -> None:
        (self.candidate / "Movies" / "a.mrc").unlink()
        self._assert_fails(self.candidate, "corrected MRC inventory differs")

    def test_missing_required_star_is_rejected(self) -> None:
        (self.candidate / "Movies" / "a.star").unlink()
        self._assert_fails(self.candidate, "STAR inventory differs")

    def test_identically_truncated_payloads_fail_independently(self) -> None:
        for root in (self.base, self.candidate):
            path = root / "Movies" / "a.mrc"
            path.write_bytes(path.read_bytes()[:-4])
        self._assert_fails(self.base, "file length")
        self._assert_fails(self.candidate, "file length")

    def test_wrong_movie_identity_is_rejected(self) -> None:
        path = self.candidate / "Movies" / "a.star"
        path.write_text(path.read_text().replace("Movies/a.tiff", "Movies/b.tiff"))
        self._assert_fails(self.candidate, "movie identity")

    def test_wrong_joint_movie_or_product_count_is_rejected(self) -> None:
        path = self.candidate / "corrected_micrographs.star"
        path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
        self._assert_fails(self.candidate, "movie rows")

    def test_extra_movie_product_is_rejected(self) -> None:
        extra = self.candidate / "Movies" / "unexpected.mrc"
        self._write_mrc(extra)
        self._assert_fails(self.candidate, "corrected MRC inventory differs")

    def test_unsupported_mrc_mode_and_malformed_dimensions_are_rejected(self) -> None:
        mode_path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(mode_path.read_bytes())
        struct.pack_into("<i", raw, 12, 6)
        mode_path.write_bytes(raw)
        self._assert_fails(self.candidate, "unsupported corrected-image MRC mode")
        self._write_tree(self.candidate)
        dim_path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(dim_path.read_bytes())
        struct.pack_into("<i", raw, 0, 0)
        dim_path.write_bytes(raw)
        self._assert_fails(self.candidate, "malformed non-positive MRC dimensions")

    def test_extended_header_is_included_in_length_and_payload_offset(self) -> None:
        path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(path.read_bytes())
        struct.pack_into("<i", raw, 92, 16)
        path.write_bytes(raw)
        self._assert_fails(self.candidate, "file length")

    def test_valid_extended_header_length_keeps_payload_offset_and_hashes_header(self) -> None:
        path = self.candidate / "Movies" / "a.mrc"
        self._write_mrc(path, nsymbt=16)
        candidate_info = compare.validate_tree(self.candidate, self.manifest)
        self.assertEqual(candidate_info["mrc_count"], 2)
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertIn("Movies/a.mrc", report["different_products"])
        self.assertEqual(report["mrc_sha256"]["Movies/a.mrc"]["base_payload"],
                         report["mrc_sha256"]["Movies/a.mrc"]["candidate_payload"])
        self.assertNotEqual(report["mrc_sha256"]["Movies/a.mrc"]["base_extended"],
                            report["mrc_sha256"]["Movies/a.mrc"]["candidate_extended"])

    def test_ms_in_star_is_not_mistaken_for_a_timing_line(self) -> None:
        path = self.candidate / "Movies" / "a.star"
        path.write_text(path.read_text().replace("200.0", "200.0 ms"))
        report = compare.compare_trees(self.base, self.candidate, self.manifest,
                                       compare_auxiliary=False)
        self.assertEqual(report["status"], "FAIL")

    def test_input_star_hash_and_ordered_movie_inventory_are_pinned(self) -> None:
        source = self.root / "movies.star"
        source.write_text(
            "data_movies\n\nloop_\n_rlnMicrographMovieName #1\n"
            "Movies/a.tiff\nMovies/b.tiff\n"
        )
        pinned = dict(self.manifest)
        pinned["input_star_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        compare.validate_input_star(source, pinned)
        source.write_text(source.read_text().replace("Movies/b.tiff", "Movies/a.tiff"))
        with self.assertRaises(compare.ValidationError):
            compare.validate_input_star(source, pinned)

    def test_cli_exit_code_agrees_with_the_report_it_writes(self) -> None:
        """A comparator that prints FAIL and exits 0 certifies the opposite of
        what it found. Every case above calls compare_trees directly, so the
        exit path is the one part of the contract nothing else observes: a
        caller that only checks the return code and a reader who only reads the
        JSON would then disagree about the same run.
        """
        import subprocess

        def invoke(out: Path) -> tuple[int, dict]:
            cp = subprocess.run(
                [sys.executable, str(SCRIPT), str(self.base), str(self.candidate),
                 "--manifest", str(manifest_path), "--json-out", str(out),
                 "--products-only"],
                capture_output=True, text=True)
            return cp.returncode, json.loads(out.read_text())

        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest) + "\n")

        rc, report = invoke(self.root / "pass.json")
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(rc, 0, report)

        path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(path.read_bytes())
        raw[1024 + 8 + 4] ^= 1
        path.write_bytes(raw)
        rc, report = invoke(self.root / "fail.json")
        self.assertEqual(report["status"], "FAIL", report)
        self.assertNotEqual(rc, 0, report)

        # And a tree the validator rejects outright, which takes the other
        # return path: the report is still written and still disagrees with 0.
        (self.candidate / "Movies" / "b.mrc").unlink()
        rc, report = invoke(self.root / "invalid.json")
        self.assertEqual(report["status"], "FAIL", report)
        self.assertNotEqual(rc, 0, report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
