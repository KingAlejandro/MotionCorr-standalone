#!/usr/bin/env python3
"""Validate and compare complete MotionCorr output trees.

Each arm is structurally validated against an explicit movie manifest before the
arms are compared. In particular, equal files are not enough: an identically
truncated MRC, an unsupported mode, or two missing STAR products must fail.

Only declared nondeterminism is normalized:
* the exact output-root prefix in text products;
* measured-duration lines in ``.log`` files only;
* the date/time token following ``Relion    `` in an MRC label.

All other MRC header bytes (including the extended header), pixels, STAR content,
and non-log products are checked. PDFs are inventoried but not content-compared;
Ghostscript embeds run-specific metadata and they are outside this image/STAR gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import os
import re
import shlex
import struct
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np


SKIP_SUFFIXES = {".pdf"}
TEXT_SUFFIXES = {".log", ".star", ".eps", ".lst", ".txt"}
TIMING_MARKERS = (
    "Full movie wall time",
    "execution time:",
    "transfer time:",
    "Total GPU alignment time:",
    "Kernel:",
    " ms",
    '~~(,_,"',
)
MRC_HEADER_BYTES = 1024
MRC_MAP_OFFSET = 208
MRC_MACHINE_STAMP_OFFSET = 212
MRC_NSYMBT_OFFSET = 92
MRC_NLABL_OFFSET = 220
LABELS_OFFSET = 224
LABEL_BYTES = 80
TIMESTAMP = re.compile(rb"(?<=Relion    )[0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}")
TIMESTAMP_MASK = b"00-XXX-00  00:00:00"


class ValidationError(RuntimeError):
    """An output tree does not satisfy the manifest or product contract."""


@dataclass(frozen=True)
class MrcInfo:
    dimensions: Tuple[int, int, int]
    mode: int
    extended_bytes: int
    file_bytes: int
    header_sha256: str
    extended_sha256: str
    payload_sha256: str


def _relative_product(value: str, name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"manifest {name} must be a non-empty relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise ValidationError(f"unsafe manifest path for {name}: {value!r}")
    return p


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except Exception as exc:
        raise ValidationError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValidationError("manifest root must be an object")
    movies = manifest.get("movies")
    shape = manifest.get("expected_shape_xyz")
    if not isinstance(movies, list) or not movies:
        raise ValidationError("manifest movies inventory is empty or malformed")
    for item in movies:
        if not isinstance(item, str) or not item or "\n" in item or "\r" in item:
            raise ValidationError("manifest movie identities must be non-empty single-line strings")
    if len(set(movies)) != len(movies):
        raise ValidationError("manifest movie inventory contains duplicates")
    if (not isinstance(shape, list) or len(shape) != 3 or
            any(type(v) is not int or v <= 0 for v in shape)):
        raise ValidationError("manifest expected_shape_xyz must contain three positive integers")
    _relative_product(manifest.get("joint_star", "corrected_micrographs.star"), "joint_star")
    return manifest


def validate_input_star(path: Path, manifest: Dict[str, Any]) -> None:
    expected_hash = manifest.get("input_star_sha256")
    if not expected_hash:
        return
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read input STAR {path}: {exc}") from exc
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash.lower() != str(expected_hash).lower():
        raise ValidationError(f"input STAR hash {actual_hash} differs from manifest {expected_hash}")
    try:
        text = raw.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"input STAR is not readable text: {path}") from exc
    rows: List[List[str]] = []
    for block, columns, values in _parse_star_loops(text, path):
        if block == "movies" and "_rlnMicrographMovieName" in columns:
            idx = columns.index("_rlnMicrographMovieName")
            rows.extend([[row[idx]] for row in values])
    observed = [row[0] for row in rows]
    if observed != manifest["movies"]:
        raise ValidationError(
            f"input STAR movie inventory differs from manifest: observed {len(observed)} rows, "
            f"expected {len(manifest['movies'])} in the recorded order"
        )


def _expected_paths(manifest: Dict[str, Any]) -> Tuple[Set[Path], Set[Path], Dict[str, str]]:
    mrcs: Set[Path] = set()
    stars: Set[Path] = set()
    movie_for_stem: Dict[str, str] = {}
    for movie in manifest["movies"]:
        stem = PurePosixPath(movie).stem
        if stem in movie_for_stem:
            raise ValidationError(f"movie stems are not unique: {stem}")
        movie_for_stem[stem] = movie
        mrcs.add(Path("Movies") / f"{stem}.mrc")
        stars.add(Path("Movies") / f"{stem}.star")
    joint = Path(manifest.get("joint_star", "corrected_micrographs.star"))
    if joint in stars:
        raise ValidationError("joint STAR path collides with a per-movie STAR")
    stars.add(joint)
    return mrcs, stars, movie_for_stem


def _star_tokens(line: str, path: Path, line_no: int) -> List[str]:
    try:
        return shlex.split(line, comments=False, posix=True)
    except ValueError as exc:
        raise ValidationError(f"malformed STAR quoting in {path}:{line_no}: {exc}") from exc


def _parse_star_loops(text: str, path: Path) -> List[Tuple[str, List[str], List[List[str]]]]:
    lines = text.splitlines()
    block = ""
    loops: List[Tuple[str, List[str], List[List[str]]]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("data_"):
            block = stripped[5:]
            i += 1
            continue
        if stripped.lower() != "loop_":
            i += 1
            continue
        i += 1
        columns: List[str] = []
        while i < len(lines) and lines[i].lstrip().startswith("_"):
            columns.append(lines[i].split()[0])
            i += 1
        if not columns:
            raise ValidationError(f"STAR loop without columns in {path}")
        rows: List[List[str]] = []
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if stripped.startswith("data_") or stripped.lower() == "loop_" or stripped.startswith("_"):
                break
            values = _star_tokens(lines[i], path, i + 1)
            if len(values) != len(columns):
                raise ValidationError(
                    f"STAR row has {len(values)} values for {len(columns)} columns in {path}:{i + 1}"
                )
            rows.append(values)
            i += 1
        loops.append((block, columns, rows))
    return loops


def _read_star_tag(path: Path, block_name: str, tag: str) -> str:
    try:
        text = path.read_text(encoding="latin-1")
    except OSError as exc:
        raise ValidationError(f"cannot read STAR {path}: {exc}") from exc
    block = ""
    in_loop = False
    found: List[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("data_"):
            block = stripped[5:]
            in_loop = False
            continue
        if stripped.lower() == "loop_":
            in_loop = True
            continue
        if block == block_name and stripped.startswith(tag) and not in_loop:
            values = _star_tokens(stripped, path, number)
            if not values or values[0] != tag:
                continue
            if len(values) != 2:
                raise ValidationError(f"malformed {tag} value in {path}:{number}")
            found.append(values[1])
    if len(found) != 1:
        raise ValidationError(f"expected exactly one {tag} in data_{block_name} of {path}, got {len(found)}")
    return found[0]


def _path_inside_root(root: Path, value: str, rel_expected: Path, star_path: Path) -> None:
    p = Path(value)
    p = p if p.is_absolute() else root / p
    try:
        actual_rel = p.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError(f"{star_path} references a product outside its output root: {value!r}") from exc
    if actual_rel != rel_expected:
        raise ValidationError(f"{star_path} references {actual_rel}, expected {rel_expected}")


def _parse_joint_micrographs(path: Path) -> List[List[str]]:
    try:
        text = path.read_text(encoding="latin-1")
    except OSError as exc:
        raise ValidationError(f"cannot read joint STAR {path}: {exc}") from exc
    matches = []
    for block, cols, rows in _parse_star_loops(text, path):
        if block == "micrographs" and "_rlnMicrographName" in cols and "_rlnMicrographMetadata" in cols:
            matches.append((cols, rows))
    if len(matches) != 1:
        raise ValidationError(f"expected one data_micrographs image/metadata loop in {path}")
    cols, rows = matches[0]
    idx_image = cols.index("_rlnMicrographName")
    idx_metadata = cols.index("_rlnMicrographMetadata")
    return [[row[idx_image], row[idx_metadata]] for row in rows]


def _decode_header(path: Path, raw: bytes) -> Tuple[str, Tuple[int, int, int], int, int, int]:
    if len(raw) != MRC_HEADER_BYTES:
        raise ValidationError(f"{path}: MRC header is {len(raw)} bytes; expected 1024")
    stamp = raw[MRC_MACHINE_STAMP_OFFSET:MRC_MACHINE_STAMP_OFFSET + 2]
    if stamp == b"DA":
        endian = "<"
    elif stamp == b"\x11\x11":
        endian = ">"
    else:
        raise ValidationError(f"{path}: unsupported MRC machine stamp {stamp!r}")
    nx, ny, nz, mode = struct.unpack_from(endian + "4i", raw, 0)
    dims = (nx, ny, nz)
    if any(v <= 0 for v in dims):
        raise ValidationError(f"{path}: malformed non-positive MRC dimensions {dims}")
    nsymbt = struct.unpack_from(endian + "i", raw, MRC_NSYMBT_OFFSET)[0]
    nlabl = struct.unpack_from(endian + "i", raw, MRC_NLABL_OFFSET)[0]
    if nsymbt < 0:
        raise ValidationError(f"{path}: negative MRC extended-header length {nsymbt}")
    if not 0 <= nlabl <= 10:
        raise ValidationError(f"{path}: invalid MRC label count {nlabl}")
    if mode != 2:
        raise ValidationError(f"{path}: unsupported corrected-image MRC mode {mode}; expected float32 mode 2")
    if raw[MRC_MAP_OFFSET:MRC_MAP_OFFSET + 4] != b"MAP ":
        raise ValidationError(f"{path}: missing MRC MAP signature")
    expected_axis = (1, 2, 3)
    axis_map = struct.unpack_from(endian + "3i", raw, 64)
    if sorted(axis_map) != list(expected_axis):
        raise ValidationError(f"{path}: malformed MRC axis mapping {axis_map}")
    stats = (*struct.unpack_from(endian + "3f", raw, 76),
             struct.unpack_from(endian + "f", raw, 216)[0])
    if not all(math.isfinite(value) for value in stats) or stats[0] > stats[1] or stats[3] < 0:
        raise ValidationError(f"{path}: invalid/non-finite MRC statistics {stats}")
    return endian, dims, mode, nsymbt, nlabl


def _normalised_header(raw: bytes, nlabl: int) -> bytes:
    normalized = bytearray(raw)
    label_end = min(LABELS_OFFSET + nlabl * LABEL_BYTES, MRC_HEADER_BYTES)
    label_region = bytes(normalized[LABELS_OFFSET:label_end])
    normalized[LABELS_OFFSET:label_end] = TIMESTAMP.sub(TIMESTAMP_MASK, label_region)
    return bytes(normalized)


def validate_mrc(path: Path, expected_shape: Sequence[int]) -> MrcInfo:
    try:
        file_bytes = path.stat().st_size
        with path.open("rb") as f:
            header = f.read(MRC_HEADER_BYTES)
            endian, dims, mode, nsymbt, nlabl = _decode_header(path, header)
            if tuple(expected_shape) != dims:
                raise ValidationError(f"{path}: MRC dimensions {dims}, expected {tuple(expected_shape)}")
            count = math.prod(dims)
            payload_bytes = count * 4  # mode 2 is exactly float32
            expected_size = MRC_HEADER_BYTES + nsymbt + payload_bytes
            if file_bytes != expected_size:
                raise ValidationError(
                    f"{path}: file length {file_bytes}, expected 1024 + nsymbt({nsymbt}) + "
                    f"float32 payload({payload_bytes}) = {expected_size}"
                )
            ext = f.read(nsymbt)
            if len(ext) != nsymbt:
                raise ValidationError(f"{path}: truncated MRC extended header ({len(ext)}/{nsymbt})")
        dtype = np.dtype(endian + "f4")
        pixels = np.memmap(path, mode="r", dtype=dtype, offset=MRC_HEADER_BYTES + nsymbt, shape=(count,))
        digest = hashlib.sha256()
        chunk_size = 1 << 20
        try:
            for start in range(0, count, chunk_size):
                chunk = pixels[start:start + chunk_size]
                if not bool(np.isfinite(chunk).all()):
                    bad = int(np.flatnonzero(~np.isfinite(chunk))[0]) + start
                    raise ValidationError(f"{path}: non-finite float32 pixel at linear index {bad}")
                digest.update(memoryview(chunk).cast("B"))
        finally:
            del pixels
        normalized = _normalised_header(header, nlabl)
        return MrcInfo(
            dimensions=dims,
            mode=mode,
            extended_bytes=nsymbt,
            file_bytes=file_bytes,
            header_sha256=hashlib.sha256(normalized).hexdigest(),
            extended_sha256=hashlib.sha256(ext).hexdigest(),
            payload_sha256=digest.hexdigest(),
        )
    except ValidationError:
        raise
    except (OSError, ValueError, struct.error) as exc:
        raise ValidationError(f"cannot validate MRC {path}: {exc}") from exc


def validate_tree(root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValidationError(f"output root does not exist or is not a directory: {root}")
    expected_mrcs, expected_stars, movie_for_stem = _expected_paths(manifest)
    actual_mrcs = {p.relative_to(root) for p in root.rglob("*.mrc") if p.is_file()}
    actual_stars = {p.relative_to(root) for p in root.rglob("*.star") if p.is_file()}
    if actual_mrcs != expected_mrcs:
        raise ValidationError(
            f"{root}: corrected MRC inventory differs; missing={sorted(map(str, expected_mrcs-actual_mrcs))}, "
            f"extra={sorted(map(str, actual_mrcs-expected_mrcs))}"
        )
    if actual_stars != expected_stars:
        raise ValidationError(
            f"{root}: STAR inventory differs; missing={sorted(map(str, expected_stars-actual_stars))}, "
            f"extra={sorted(map(str, actual_stars-expected_stars))}"
        )
    for rel in expected_mrcs | expected_stars:
        if (root / rel).is_symlink():
            raise ValidationError(f"{root / rel}: required product must not be a symlink")

    shape = manifest["expected_shape_xyz"]
    mrc_info: Dict[str, MrcInfo] = {}
    for rel in sorted(expected_mrcs):
        mrc_info[rel.as_posix()] = validate_mrc(root / rel, shape)

    for stem, movie in movie_for_stem.items():
        rel = Path("Movies") / f"{stem}.star"
        identity = _read_star_tag(root / rel, "general", "_rlnMicrographMovieName")
        if identity != movie:
            raise ValidationError(f"{root / rel}: movie identity {identity!r}, expected {movie!r}")

    joint_rel = Path(manifest.get("joint_star", "corrected_micrographs.star"))
    joint_rows = _parse_joint_micrographs(root / joint_rel)
    expected_rows = len(movie_for_stem)
    if len(joint_rows) != expected_rows:
        raise ValidationError(f"{root / joint_rel}: {len(joint_rows)} movie rows, expected {expected_rows}")
    seen: Set[str] = set()
    for image_path, metadata_path in joint_rows:
        image_rel = Path(Path(image_path).name)
        if image_rel.suffix != ".mrc" or image_rel.stem not in movie_for_stem:
            raise ValidationError(f"{root / joint_rel}: unexpected movie identity in image path {image_path!r}")
        stem = image_rel.stem
        if stem in seen:
            raise ValidationError(f"{root / joint_rel}: duplicate movie row for {stem}")
        seen.add(stem)
        _path_inside_root(root, image_path, Path("Movies") / f"{stem}.mrc", root / joint_rel)
        _path_inside_root(root, metadata_path, Path("Movies") / f"{stem}.star", root / joint_rel)
    missing_rows = set(movie_for_stem) - seen
    if missing_rows:
        raise ValidationError(f"{root / joint_rel}: missing movie rows {sorted(missing_rows)}")

    all_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return {
        "root": str(root),
        "file_count": len(all_files),
        "files": all_files,
        "mrc_count": len(mrc_info),
        "star_count": len(actual_stars),
        "movie_count": len(movie_for_stem),
        "pixel_count": math.prod(shape) * len(movie_for_stem),
        "mrc": mrc_info,
    }


def _normalise_text(path: Path, root: Path, raw: bytes) -> bytes:
    text = raw.decode("latin-1")
    # Replace both spellings because a symlinked temporary root can be printed
    # lexically by the producer while pathlib resolves it for containment checks.
    for spelling in {str(root), str(root.resolve())}:
        text = text.replace(spelling, "<OUTROOT>")
    if path.suffix.lower() == ".log":
        text = "\n".join(line for line in text.split("\n")
                          if not any(marker in line for marker in TIMING_MARKERS))
    return text.encode("latin-1")


def compare_trees(base: Path, candidate: Path, manifest: Dict[str, Any],
                  compare_auxiliary: bool = True) -> Dict[str, Any]:
    base_info = validate_tree(base, manifest)
    candidate_info = validate_tree(candidate, manifest)
    # Keep the caller's lexical spelling as well as validate_tree's canonical
    # root: producers may have printed the symlinked spelling in STAR paths.
    b_root, c_root = base.absolute(), candidate.absolute()
    b_files = set(base_info["files"])
    c_files = set(candidate_info["files"])
    if compare_auxiliary and b_files != c_files:
        raise ValidationError(
            f"tree file inventories differ; base-only={sorted(b_files-c_files)[:10]}, "
            f"candidate-only={sorted(c_files-b_files)[:10]}"
        )
    different: List[str] = []
    products_different: List[str] = []
    expected_mrcs, expected_stars, _ = _expected_paths(manifest)
    product_paths = expected_mrcs | expected_stars
    if compare_auxiliary:
        paths = sorted(Path(p) for p in b_files)
    else:
        # Each tree has already been checked independently against the required
        # image/STAR inventory. Auxiliary file presence is outside this mode.
        paths = sorted(product_paths)
    for rel in paths:
        if rel.suffix.lower() in SKIP_SUFFIXES:
            continue
        bx, cx = b_root / rel, c_root / rel
        if rel.suffix.lower() == ".mrc":
            bi = base_info["mrc"][rel.as_posix()]
            ci = candidate_info["mrc"][rel.as_posix()]
            equal = (bi.header_sha256 == ci.header_sha256 and
                     bi.extended_sha256 == ci.extended_sha256 and
                     bi.payload_sha256 == ci.payload_sha256)
        else:
            br, cr = bx.read_bytes(), cx.read_bytes()
            if rel.suffix.lower() in TEXT_SUFFIXES:
                br = _normalise_text(bx, b_root, br)
                cr = _normalise_text(cx, c_root, cr)
            equal = br == cr
        if not equal:
            different.append(rel.as_posix())
            if rel in product_paths:
                products_different.append(rel.as_posix())
    return {
        "status": "PASS" if not different else "FAIL",
        "base": {k: v for k, v in base_info.items() if k != "mrc"},
        "candidate": {k: v for k, v in candidate_info.items() if k != "mrc"},
        "different_files": different,
        "different_products": products_different,
        "comparison_scope": "products" if not compare_auxiliary else "complete non-PDF tree",
        "mrc_sha256": {
            rel: {"base_header": base_info["mrc"][rel].header_sha256,
                  "candidate_header": candidate_info["mrc"][rel].header_sha256,
                  "base_extended": base_info["mrc"][rel].extended_sha256,
                  "candidate_extended": candidate_info["mrc"][rel].extended_sha256,
                  "base_payload": base_info["mrc"][rel].payload_sha256,
                  "candidate_payload": candidate_info["mrc"][rel].payload_sha256}
            for rel in sorted(base_info["mrc"])
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="JSON containing exact input movie inventory and corrected-image dimensions")
    parser.add_argument("--input-star", type=Path, default=None,
                        help="input STAR to verify against the manifest hash and movie list")
    parser.add_argument("--products-only", action="store_true",
                        help="Compare validated MRC/STAR products only; omit logs/EPS/other auxiliary files")
    parser.add_argument("--json-out", type=Path, default=None,
                        help="Write the full validation and comparison report as JSON")
    opts = parser.parse_args(argv)
    try:
        manifest = load_manifest(opts.manifest)
        if manifest.get("input_star_sha256") and opts.input_star is None:
            raise ValidationError("--input-star is required because the manifest pins an input STAR hash")
        if opts.input_star is not None:
            validate_input_star(opts.input_star, manifest)
        report = compare_trees(opts.base, opts.candidate, manifest,
                               compare_auxiliary=not opts.products_only)
    except ValidationError as exc:
        report = {"status": "FAIL", "reason": str(exc)}
        print(f"FAIL: {exc}", file=sys.stderr)
        if opts.json_out:
            opts.json_out.parent.mkdir(parents=True, exist_ok=True)
            opts.json_out.write_text(json.dumps(report, indent=2) + "\n")
        return 1
    if opts.json_out:
        opts.json_out.parent.mkdir(parents=True, exist_ok=True)
        opts.json_out.write_text(json.dumps(report, indent=2) + "\n")
    b = report["base"]
    print(f"Validated {b['movie_count']} movies, {b['mrc_count']} MRC images, "
          f"{b['star_count']} STAR files, {b['pixel_count']} pixels per arm")
    print(f"Comparison: {report['comparison_scope']}; status={report['status']}; "
          f"different files={len(report['different_files'])}")
    for rel in report["different_files"][:20]:
        print(f"  DIFF {rel}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
