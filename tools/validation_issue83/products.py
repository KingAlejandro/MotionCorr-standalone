"""Output inventory, MRC header and movie-metadata checks for issue #83.

This is deliberately *not* a numerical comparator. It answers three questions
that exit status and file counts cannot:

1. Is every declared product present, with a readable header and a payload
   whose length matches that header?
2. Does the movie STAR record original-pixel units -- original pixel size,
   binning, start frame, dose -- rather than binned or defaulted values?
3. Is the global trajectory complete and finite, with one row per summed frame?

Pixel identity between schedules is delegated to ``tools/compare_motioncorr.py``
under its existing ``exact`` profile. Nothing here sets a numerical threshold.
"""

from __future__ import annotations

import math
import os
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MRC_HEADER_BYTES = 1024

#: Sentinel written for frames that were not aligned (src/micrograph_model.cpp:29).
NOT_OBSERVED = -9999.0


def output_stem(movie_relpath: str) -> str:
    """Output stem the runner derives from a movie name in the input STAR.

    Mirrors ``MotioncorrRunner::getOutputFileNames``: the extension is dropped
    and every remaining dot becomes an underscore. The movie's relative
    directory is kept, so a movie listed as ``Movies/x.mrcs`` writes its
    products to ``<outdir>/Movies/x.*`` rather than to the top level.
    """
    text = str(movie_relpath)
    dot = text.rfind(".")
    slash = max(text.rfind("/"), text.rfind(os.sep))
    if dot > slash:
        text = text[:dot]
    head, sep, tail = text.rpartition("/")
    return f"{head}{sep}{tail.replace('.', '_')}" if sep else tail.replace(".", "_")

#: MRC mode -> bytes per sample, restricted to the modes this program writes.
MRC_MODE_ITEMSIZE = {0: 1, 1: 2, 2: 4, 6: 2, 12: 2}


def read_mrc_header(path: Path) -> Dict[str, Any]:
    """Parse the fields needed to validate a product, plus the payload length."""
    size = path.stat().st_size
    if size < MRC_HEADER_BYTES:
        return {"error": f"{path.name}: {size} bytes is shorter than an MRC header"}
    with path.open("rb") as handle:
        raw = handle.read(MRC_HEADER_BYTES)
    nx, ny, nz, mode = struct.unpack_from("<4i", raw, 0)
    mx, my, mz = struct.unpack_from("<3i", raw, 28)
    cella_x, cella_y, cella_z = struct.unpack_from("<3f", raw, 40)
    nsymbt = struct.unpack_from("<i", raw, 92)[0]

    header: Dict[str, Any] = {
        "nx": nx, "ny": ny, "nz": nz, "mode": mode,
        "mx": mx, "my": my, "mz": mz,
        "cella": [cella_x, cella_y, cella_z],
        "nsymbt": nsymbt,
        "file_bytes": size,
    }
    itemsize = MRC_MODE_ITEMSIZE.get(mode)
    if itemsize is None:
        header["error"] = f"{path.name}: unexpected MRC mode {mode}"
        return header
    expected = MRC_HEADER_BYTES + nsymbt + nx * ny * nz * itemsize
    header["expected_bytes"] = expected
    if size != expected:
        header["error"] = (f"{path.name}: payload {size} bytes, header implies {expected} "
                           f"(nx={nx} ny={ny} nz={nz} mode={mode} nsymbt={nsymbt})")
    if mx > 0 and cella_x > 0:
        header["pixel_size_angstrom"] = cella_x / mx
    return header


# --------------------------------------------------------------------- STAR io

_LOOP_FIELD = re.compile(r"^_(\S+)\s*(?:#(\d+))?\s*$")


def parse_star(path: Path) -> Dict[str, Any]:
    """Minimal RELION STAR reader: pairs and loops, keyed by data block name.

    Only what the checks below need. ``tools/compare_motioncorr.py`` keeps its
    own parser; this one is not shared with it so its behaviour is unchanged.
    """
    blocks: Dict[str, Dict[str, Any]] = {}
    current: Optional[str] = None
    fields: List[str] = []
    rows: List[List[str]] = []
    state = "idle"  # idle | loop_fields | loop_rows

    def flush() -> None:
        if current is not None and fields:
            blocks.setdefault(current, {})["fields"] = list(fields)
            blocks[current]["rows"] = [list(r) for r in rows]

    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("data_"):
            flush()
            current = stripped[len("data_"):]
            blocks.setdefault(current, {"pairs": {}, "fields": [], "rows": []})
            fields, rows, state = [], [], "idle"
            continue
        if current is None:
            continue
        if stripped == "loop_":
            fields, rows, state = [], [], "loop_fields"
            continue
        match = _LOOP_FIELD.match(stripped)
        if state == "loop_fields" and match:
            fields.append(match.group(1))
            continue
        if state == "loop_fields" and not match:
            state = "loop_rows"
        if state == "loop_rows":
            rows.append(stripped.split())
            continue
        parts = stripped.split(None, 1)
        if len(parts) == 2 and parts[0].startswith("_"):
            blocks[current].setdefault("pairs", {})[parts[0][1:]] = parts[1].strip()
    flush()
    return blocks


def _pair(blocks: Dict[str, Any], block: str, key: str) -> Optional[str]:
    return blocks.get(block, {}).get("pairs", {}).get(key)


def _as_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def check_movie_star(path: Path, expect: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the per-movie metadata STAR against the requested configuration.

    ``expect`` carries ``original_pixel_size``, ``binning``, ``first_frame``,
    ``dose_per_frame`` (or ``None`` when dose weighting is off), ``pre_exposure``
    and ``n_summed_frames``.
    """
    result: Dict[str, Any] = {"path": str(path), "errors": []}
    if not path.exists():
        result["errors"].append(f"{path.name}: missing")
        return result
    blocks = parse_star(path)
    if "general" not in blocks:
        result["errors"].append(f"{path.name}: no data_general block")
        return result

    observed = {
        "original_pixel_size": _as_float(_pair(blocks, "general", "rlnMicrographOriginalPixelSize")),
        "binning": _as_float(_pair(blocks, "general", "rlnMicrographBinning")),
        "first_frame": _as_float(_pair(blocks, "general", "rlnMicrographStartFrame")),
        "dose_per_frame": _as_float(_pair(blocks, "general", "rlnMicrographDoseRate")),
        "pre_exposure": _as_float(_pair(blocks, "general", "rlnMicrographPreExposure")),
        "motion_model_version": _pair(blocks, "general", "rlnMotionModelVersion"),
    }
    result["observed"] = observed

    # Original pixel size must stay in original pixels even when binning is on:
    # a binned value here is the units defect tracked by #68.
    for key in ("original_pixel_size", "binning", "first_frame"):
        want = expect.get(key)
        got = observed.get(key)
        if want is None:
            continue
        if got is None:
            result["errors"].append(f"{path.name}: {key} absent, expected {want}")
        elif not math.isclose(got, float(want), rel_tol=1e-6, abs_tol=1e-9):
            result["errors"].append(f"{path.name}: {key}={got}, expected {want}")

    if expect.get("dose_per_frame") is not None:
        got = observed["dose_per_frame"]
        if got is None or not math.isclose(got, float(expect["dose_per_frame"]),
                                           rel_tol=1e-6, abs_tol=1e-9):
            result["errors"].append(
                f"{path.name}: rlnMicrographDoseRate={got}, expected {expect['dose_per_frame']}")
    if expect.get("pre_exposure") is not None:
        got = observed["pre_exposure"]
        if got is None or not math.isclose(got, float(expect["pre_exposure"]),
                                           rel_tol=1e-6, abs_tol=1e-9):
            result["errors"].append(
                f"{path.name}: rlnMicrographPreExposure={got}, expected {expect['pre_exposure']}")

    shifts = blocks.get("global_shift", {})
    fields = shifts.get("fields", [])
    rows = shifts.get("rows", [])
    result["n_global_shift_rows"] = len(rows)
    observed = 0
    if not rows:
        result["errors"].append(f"{path.name}: empty global_shift table")
    else:
        try:
            ix = fields.index("rlnMicrographShiftX")
            iy = fields.index("rlnMicrographShiftY")
        except ValueError:
            result["errors"].append(f"{path.name}: global_shift lacks shift columns")
        else:
            for row_index, row in enumerate(rows):
                if len(row) <= max(ix, iy):
                    result["errors"].append(
                        f"{path.name}: global_shift row {row_index} is short")
                    continue
                values = [_as_float(row[column]) for column in (ix, iy)]
                if any(v is None or not math.isfinite(v) for v in values):
                    result["errors"].append(
                        f"{path.name}: nonfinite global shift at row {row_index}")
                    continue
                # Frames outside the summed window are recorded as NOT_OBSERVED,
                # not omitted, so the table always spans the whole movie.
                if not all(v == NOT_OBSERVED for v in values):
                    observed += 1
        result["n_observed_shift_rows"] = observed

        want_rows = expect.get("n_trajectory_rows")
        if want_rows is not None and len(rows) != want_rows:
            result["errors"].append(
                f"{path.name}: {len(rows)} global_shift rows, expected one per "
                f"movie frame ({want_rows})")
        want_observed = expect.get("n_observed_frames")
        if want_observed is not None and observed != want_observed:
            result["errors"].append(
                f"{path.name}: {observed} observed global_shift rows, "
                f"expected {want_observed}")

    local = blocks.get("local_shift", {}).get("rows", [])
    result["n_local_shift_rows"] = len(local)
    result["has_local_motion_model"] = bool(
        blocks.get("local_motion_model", {}).get("rows")) or bool(local)
    return result


def check_products(out_dir: Path, movie_stems: List[str], suffixes: List[str],
                   star_expect: Dict[str, Any],
                   expect_geometry: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Full expected inventory for one output directory.

    A missing pair -- image without metadata or the reverse -- is an error, and
    any unexpected extra product is reported so the inventory is exact in both
    directions.
    """
    report: Dict[str, Any] = {"movies": {}, "errors": [], "inventory_complete": True}
    expected_paths = set()

    for stem in movie_stems:
        entry: Dict[str, Any] = {"headers": {}, "star": None}
        for suffix in suffixes:
            if suffix == ".star":
                path = out_dir / f"{stem}.star"
                expected_paths.add(path.resolve())
                entry["star"] = check_movie_star(path, star_expect)
                report["errors"].extend(entry["star"]["errors"])
                continue
            path = out_dir / f"{stem}{suffix}"
            expected_paths.add(path.resolve())
            if not path.exists():
                report["errors"].append(f"{path.name}: missing declared product")
                continue
            header = read_mrc_header(path)
            entry["headers"][suffix] = header
            if "error" in header:
                report["errors"].append(header["error"])
                continue
            if expect_geometry is not None and suffix in (".mrc", "_noDW.mrc",
                                                          "_EVN.mrc", "_ODD.mrc"):
                want_nx, want_ny = expect_geometry
                if (header["nx"], header["ny"]) != (want_nx, want_ny):
                    report["errors"].append(
                        f"{path.name}: {header['nx']}x{header['ny']}, "
                        f"expected {want_nx}x{want_ny}")
        report["movies"][stem] = entry

    # Products live under the movie's relative directory, so scan recursively.
    produced = {p.resolve() for p in out_dir.rglob("*.mrc")}
    produced |= {p.resolve() for p in out_dir.rglob("*.star")}
    # The joint dataset STAR is written once per run, not per movie.
    produced.discard((out_dir / "corrected_micrographs.star").resolve())
    unexpected = sorted(str(p.relative_to(out_dir.resolve()))
                        for p in produced - expected_paths)
    if unexpected:
        report["unexpected_products"] = unexpected
        report["errors"].append(f"unexpected products present: {', '.join(unexpected)}")
    report["inventory_complete"] = not report["errors"]
    return report
