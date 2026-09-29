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

    def test_non_finite_pixel_is_rejected(self) -> None:
        """The finite-payload guard had no control, and every support row that
        claims 'finite complete pixels' rests on it."""
        path = self.candidate / "Movies" / "a.mrc"
        raw = bytearray(path.read_bytes())
        struct.pack_into("<f", raw, 1024 + 8 + 4, float("nan"))
        path.write_bytes(raw)
        self._assert_fails(self.candidate, "non-finite float32 pixel at linear index 1")
        raw = bytearray(path.read_bytes())
        struct.pack_into("<f", raw, 1024 + 8 + 4, float("inf"))
        path.write_bytes(raw)
        self._assert_fails(self.candidate, "non-finite float32 pixel at linear index 1")


class TestDeclaredProductSets(unittest.TestCase):
    """Controls for the declared per-movie product set, per-movie geometry and
    STAR associations that the compact-ingest output-mode rows are graded with.

    Each control removes exactly one property from an otherwise valid tree, so a
    green run means the corresponding check observed it rather than that nothing
    looked."""

    PS_SHAPE = (6, 6, 1)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tree = self.root / "arm"
        self.manifest = {
            "schema_version": 2,
            "movies": ["Movies/a.tiff", "Movies/b.tiff"],
            "expected_shape_xyz": [4, 3, 1],
            "joint_star": "corrected_micrographs.star",
            "products": [
                {"suffix": ""},
                {"suffix": "_noDW", "joint_tag": "_rlnMicrographNameNoDW"},
                {"suffix": "_EVN"},
                {"suffix": "_ODD"},
                {"suffix": "_PS", "shape_xyz": list(self.PS_SHAPE),
                 "joint_tag": "_rlnCtfPowerSpectrum"},
            ],
            "general_tags": {"_rlnMicrographStartFrame": 3, "_rlnMicrographDoseRate": 1.277},
            "optics_group": 1,
            "forbidden_joint_tags": ["_rlnMicrographNameEven", "_rlnMicrographNameOdd"],
        }
        self._write_tree()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _mrc(self, path: Path, dims=(4, 3, 1), pixel0: float = 0.0) -> None:
        nx, ny, nz = dims
        count = nx * ny * nz
        header = bytearray(1024)
        struct.pack_into("<4i", header, 0, nx, ny, nz, 2)
        struct.pack_into("<3i", header, 64, 1, 2, 3)
        struct.pack_into("<4f", header, 76, 0.0, 11.0, 5.5, 2.0)
        header[208:212] = b"MAP "
        header[212:216] = b"DA\0\0"
        struct.pack_into("<i", header, 220, 1)
        header[224:224 + 29] = b"Relion    28-Sep-26  15:38:06"
        values = [pixel0] + [float(i) for i in range(1, count)]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(header) + struct.pack(f"<{count}f", *values))

    def _write_tree(self, *, products=None, shapes=None, star_tags=None,
                    joint_cols=None, joint_values=None) -> None:
        root = self.tree
        if root.exists():
            for item in sorted(root.rglob("*"), reverse=True):
                item.unlink() if item.is_file() else item.rmdir()
        root.mkdir(parents=True, exist_ok=True)
        products = products if products is not None else ["", "_noDW", "_EVN", "_ODD", "_PS"]
        shapes = shapes or {}
        cols = joint_cols if joint_cols is not None else [
            "_rlnMicrographName", "_rlnMicrographMetadata", "_rlnOpticsGroup",
            "_rlnMicrographNameNoDW", "_rlnCtfPowerSpectrum"]
        joint = ["# version 50001", "", "data_micrographs", "", "loop_"]
        joint += [f"{name} #{i}" for i, name in enumerate(cols, 1)]
        tags = star_tags if star_tags is not None else {
            "_rlnMicrographStartFrame": "3", "_rlnMicrographDoseRate": "1.277000"}
        for movie in ("Movies/a.tiff", "Movies/b.tiff"):
            stem = Path(movie).stem
            for suffix in products:
                dims = shapes.get(suffix, self.PS_SHAPE if suffix == "_PS" else (4, 3, 1))
                self._mrc(root / "Movies" / f"{stem}{suffix}.mrc", dims=dims)
            body = "".join(f"{tag} {value}\n" for tag, value in tags.items())
            (root / "Movies" / f"{stem}.star").write_text(
                f"# version 50001\n\ndata_general\n\n_rlnMicrographMovieName {movie}\n{body}")
            supplied = (joint_values or {}).get(stem, {})
            cell = {
                "_rlnMicrographName": str(root / "Movies" / f"{stem}.mrc"),
                "_rlnMicrographMetadata": str(root / "Movies" / f"{stem}.star"),
                "_rlnOpticsGroup": "1",
                "_rlnMicrographNameNoDW": str(root / "Movies" / f"{stem}_noDW.mrc"),
                "_rlnCtfPowerSpectrum": str(root / "Movies" / f"{stem}_PS.mrc"),
                "_rlnMicrographNameEven": str(root / "Movies" / f"{stem}_EVN.mrc"),
                "_rlnMicrographNameOdd": str(root / "Movies" / f"{stem}_ODD.mrc"),
            }
            cell.update(supplied)
            joint.append(" ".join(cell[name] for name in cols))
        (root / "corrected_micrographs.star").write_text("\n".join(joint) + "\n")

    def _fails(self, needle: str, manifest=None) -> None:
        with self.assertRaises(compare.ValidationError) as caught:
            compare.validate_tree(self.tree, manifest or self.manifest)
        self.assertIn(needle, str(caught.exception))

    def test_declared_product_set_validates_and_is_counted(self) -> None:
        info = compare.validate_tree(self.tree, self.manifest)
        self.assertEqual(info["mrc_count"], 10)
        self.assertEqual(info["movie_count"], 2)
        # 2 movies x (4 products of 12 px + one 36 px power spectrum)
        self.assertEqual(info["pixel_count"], 2 * (4 * 12 + 36))

    def test_missing_declared_auxiliary_product_is_rejected(self) -> None:
        (self.tree / "Movies" / "a_noDW.mrc").unlink()
        self._fails("corrected MRC inventory differs")

    def test_undeclared_auxiliary_product_is_rejected(self) -> None:
        reduced = dict(self.manifest)
        reduced["products"] = [{"suffix": ""}, {"suffix": "_noDW",
                                                "joint_tag": "_rlnMicrographNameNoDW"}]
        reduced["forbidden_joint_tags"] = []
        self._fails("corrected MRC inventory differs", manifest=reduced)

    def test_declared_product_with_the_wrong_geometry_is_rejected(self) -> None:
        """_PS.mrc is sized by --ps_size, not by the movie. Writing it at the
        movie geometry is the failure a single expected_shape_xyz cannot see."""
        self._write_tree(shapes={"_PS": (4, 3, 1)})
        self._fails("MRC dimensions (4, 3, 1), expected (6, 6, 1)")

    def test_per_movie_geometry_override_grades_a_mixed_size_batch(self) -> None:
        mixed = {
            "schema_version": 2,
            "movies": ["Movies/a.tiff",
                       {"movie": "Movies/b.tiff", "shape_xyz": [5, 7, 1]}],
            "expected_shape_xyz": [4, 3, 1],
            "joint_star": "corrected_micrographs.star",
        }
        self._write_tree(products=[""], shapes={})
        # b was written at a's geometry, which only a per-movie shape can catch.
        self._fails("MRC dimensions (4, 3, 1), expected (5, 7, 1)", manifest=mixed)
        self._mrc(self.tree / "Movies" / "b.mrc", dims=(5, 7, 1))
        info = compare.validate_tree(self.tree, mixed)
        self.assertEqual(info["pixel_count"], 12 + 35)

    def test_missing_association_column_is_rejected(self) -> None:
        self._write_tree(joint_cols=["_rlnMicrographName", "_rlnMicrographMetadata",
                                     "_rlnOpticsGroup", "_rlnCtfPowerSpectrum"])
        self._fails("missing _rlnMicrographNameNoDW association")

    def test_association_pointing_at_the_wrong_product_is_rejected(self) -> None:
        root = self.tree
        self._write_tree(joint_values={"a": {
            "_rlnCtfPowerSpectrum": str(root / "Movies" / "b_PS.mrc")}})
        self._fails("references Movies/b_PS.mrc, expected Movies/a_PS.mrc")

    def test_wrong_optics_group_is_rejected(self) -> None:
        self._write_tree(joint_values={"b": {"_rlnOpticsGroup": "2"}})
        self._fails("optics group '2', expected '1'")

    def test_changed_exposure_tag_is_rejected_and_reformatting_is_not(self) -> None:
        self._write_tree(star_tags={"_rlnMicrographStartFrame": "4",
                                    "_rlnMicrographDoseRate": "1.277000"})
        self._fails("_rlnMicrographStartFrame is '4', expected '3'")
        self._write_tree(star_tags={"_rlnMicrographStartFrame": "3",
                                    "_rlnMicrographDoseRate": "1.2770000"})
        compare.validate_tree(self.tree, self.manifest)

    def test_forbidden_association_column_is_rejected(self) -> None:
        """--even_odd_split writes _EVN/_ODD images but records no association
        outside tomography. Pinning that keeps the support row honest."""
        compare.validate_tree(self.tree, self.manifest)
        self._write_tree(joint_cols=["_rlnMicrographName", "_rlnMicrographMetadata",
                                     "_rlnOpticsGroup", "_rlnMicrographNameNoDW",
                                     "_rlnCtfPowerSpectrum", "_rlnMicrographNameEven"])
        self._fails("unexpected association column(s) ['_rlnMicrographNameEven']")

    def test_malformed_product_declarations_are_rejected(self) -> None:
        source = self.root / "m.json"
        base = {"movies": ["Movies/a.tiff"], "expected_shape_xyz": [4, 3, 1]}
        cases = [
            ({"products": [{"suffix": ""}, {"suffix": ""}]}, "twice"),
            ({"products": [{"suffix": "_noDW"}]}, "must declare the plain corrected sum"),
            ({"products": [{"suffix": "noDW"}]}, "must be empty or _ALNUM"),
            ({"products": []}, "non-empty list"),
            ({"products": [{"suffix": "", "shape_xyz": [4, 3]}]}, "three positive integers"),
            ({"products": [{"suffix": "", "joint_tag": "ctf"}]}, "must be a _rln STAR tag"),
            ({"general_tags": {"voltage": 200}}, "is not a _rln STAR tag"),
            ({"movies": [{"movie": "Movies/a.tiff", "bogus": 1}]}, "unknown keys"),
            ({"movies": [{"movie": "Movies/a.tiff", "shape_xyz": [0, 3, 1]}]},
             "three positive integers"),
            ({"forbidden_joint_tags": ["even"]}, "list of _rln STAR tags"),
        ]
        for overlay, needle in cases:
            with self.subTest(overlay=sorted(overlay)):
                manifest = dict(base)
                manifest.update(overlay)
                source.write_text(json.dumps(manifest))
                with self.assertRaises(compare.ValidationError) as caught:
                    compare.load_manifest(source)
                self.assertIn(needle, str(caught.exception))

    def test_legacy_manifest_without_products_still_means_one_sum_per_movie(self) -> None:
        legacy = {"movies": ["Movies/a.tiff", "Movies/b.tiff"],
                  "expected_shape_xyz": [4, 3, 1]}
        self._write_tree(products=[""])
        info = compare.validate_tree(self.tree, legacy)
        self.assertEqual(info["mrc_count"], 2)
        self.assertEqual(info["pixel_count"], 24)
        self._mrc(self.tree / "Movies" / "a_noDW.mrc")
        with self.assertRaises(compare.ValidationError):
            compare.validate_tree(self.tree, legacy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
