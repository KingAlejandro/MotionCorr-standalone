#!/usr/bin/env python3
"""Compare MotionCorr outputs against reference runs, ground truth, and acceptance gates.

Reports:
1. Motion trajectory error (frame shifts: coordinate RMS error, max absolute error)
2. Corrected image parity (RMSE, max absolute pixel error, relative error)
3. STAR metadata field differences (normalized for run paths)
4. Runtime, peak memory (RSS), and exit status
5. Gate evaluation (pass/fail) against strict parity or relaxed numerical tolerances
"""

import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None


class ArrayProxy:
    """Lightweight 1D array wrapper when NumPy is not installed."""
    def __init__(self, data_tuple: Tuple[Any, ...], shape: Tuple[int, ...], raw_bytes: bytes):
        self._data = data_tuple
        self.shape = shape
        self.size = len(data_tuple)
        self._raw = raw_bytes

    def tobytes(self) -> bytes:
        return self._raw

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, idx):
        return self._data[idx]


def parse_mrc(filepath: Path) -> Tuple[Dict[str, Any], Any, bytes]:
    """Parse MRC 2014 file header and pixel data."""
    raw = filepath.read_bytes()
    if len(raw) < 1024:
        raise ValueError(f"File too short for MRC header: {filepath} ({len(raw)} bytes)")

    header_bytes = raw[:1024]
    nx, ny, nz, mode = struct.unpack_from("<4i", header_bytes, 0)
    nsymbt = struct.unpack_from("<i", header_bytes, 92)[0]
    if min(nx, ny, nz) <= 0 or nsymbt < 0:
        raise ValueError(f"Invalid MRC dimensions or extended-header size in {filepath}")
    dmin, dmax, dmean = struct.unpack_from("<3f", header_bytes, 76)
    rms = struct.unpack_from("<f", header_bytes, 216)[0]

    header_info = {
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "mode": mode,
        "dmin": dmin,
        "dmax": dmax,
        "dmean": dmean,
        "rms": rms,
        "labels": header_bytes[224:1024].decode("ascii", errors="replace").strip(),
    }

    mode_itemsize = {0: 1, 1: 2, 2: 4, 6: 2, 12: 2}
    if mode not in mode_itemsize:
        raise ValueError(f"Unsupported MRC mode {mode} in {filepath}")

    expected_pixels = nx * ny * nz
    data_offset = 1024 + nsymbt
    expected_size = data_offset + expected_pixels * mode_itemsize[mode]
    if len(raw) != expected_size:
        raise ValueError(
            f"MRC payload size mismatch in {filepath}: expected {expected_size} bytes, got {len(raw)}"
        )

    payload_bytes = raw[data_offset:]
    if np is not None:
        dtype_map = {
            0: np.dtype("i1"),
            1: np.dtype("<i2"),
            2: np.dtype("<f4"),
            6: np.dtype("<u2"),
            12: np.dtype("<f2"),
        }
        pixel_data = np.frombuffer(raw, dtype=dtype_map[mode], count=expected_pixels, offset=data_offset)
    else:
        fmt_map = {
            0: f"<{expected_pixels}b",
            1: f"<{expected_pixels}h",
            2: f"<{expected_pixels}f",
            6: f"<{expected_pixels}H",
            12: f"<{expected_pixels}e",
        }
        unpacked = struct.unpack(fmt_map[mode], payload_bytes)
        pixel_data = ArrayProxy(unpacked, shape=(expected_pixels,), raw_bytes=payload_bytes)

    return header_info, pixel_data, header_bytes


def parse_star_file(filepath: Path) -> Dict[str, Any]:
    """Simple parser for RELION 3/5 STAR files containing loop_ tables and key-value blocks."""
    lines = filepath.read_text().splitlines()
    blocks: Dict[str, Any] = {}
    current_block: Optional[str] = None
    in_loop = False
    loop_labels: List[str] = []
    loop_rows: List[List[str]] = []

    def flush_loop():
        nonlocal in_loop, loop_labels, loop_rows
        if in_loop and current_block:
            blocks[current_block] = {
                "type": "loop",
                "labels": loop_labels,
                "rows": loop_rows,
            }
            in_loop = False
            loop_labels = []
            loop_rows = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        if stripped.startswith("data_"):
            flush_loop()
            current_block = stripped[5:].strip()
            blocks[current_block] = {"type": "kv", "fields": {}}
            continue

        if stripped == "loop_":
            flush_loop()
            in_loop = True
            loop_labels = []
            loop_rows = []
            continue

        if in_loop:
            if stripped.startswith("_"):
                # label line e.g. _rlnMicrographShiftX #2
                label_name = stripped.split()[0]
                loop_labels.append(label_name)
            else:
                tokens = stripped.split()
                if tokens:
                    loop_rows.append(tokens)
        else:
            if current_block and stripped.startswith("_"):
                parts = stripped.split(None, 1)
                k = parts[0]
                v = parts[1] if len(parts) > 1 else ""
                blocks[current_block]["fields"][k] = v

    flush_loop()
    return blocks


def extract_global_shifts(star_dict: Dict[str, Any]) -> List[Tuple[int, float, float]]:
    """Extract global frame shifts (frame, shift_x, shift_y) from parsed STAR dict."""
    shifts = []
    block = star_dict.get("global_shift")
    if not block or block.get("type") != "loop":
        return shifts

    labels = block["labels"]
    try:
        frame_idx = labels.index("_rlnMicrographFrameNumber")
        x_idx = labels.index("_rlnMicrographShiftX")
        y_idx = labels.index("_rlnMicrographShiftY")
    except ValueError:
        return shifts

    for row in block["rows"]:
        if len(row) != len(labels):
            raise ValueError("Malformed global_shift row: column count differs from labels")
        f_num = int(row[frame_idx])
        sx = float(row[x_idx])
        sy = float(row[y_idx])
        shifts.append((f_num, sx, sy))
    return shifts


def normalize_path(p: str) -> str:
    """Ignore differing output roots while preserving the named movie or artifact."""
    return Path(p).name


def normalized_mrc_labels(header: bytes) -> bytes:
    """Ignore only RELION's clock stamp in the first 80-byte MRC label."""
    labels = bytearray(header[224:1024])
    timestamp = rb"\b\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}\b"
    labels[:80] = re.sub(timestamp, lambda match: b"0" * len(match.group()), bytes(labels[:80]))
    return bytes(labels)


def compare_trajectories(
    ref_shifts: List[Tuple[int, float, float]],
    test_shifts: List[Tuple[int, float, float]],
) -> Dict[str, Any]:
    """Compare two motion trajectories and compute error metrics."""
    if not ref_shifts or not test_shifts:
        return {"error": "Missing shifts in reference or test STAR file"}

    for name, shifts in (("reference", ref_shifts), ("test", test_shifts)):
        frames = [frame for frame, _, _ in shifts]
        if any(frame < 1 for frame in frames) or len(set(frames)) != len(frames):
            return {"error": f"Invalid or duplicate frame numbers in {name} trajectory"}
        if any(not (math.isfinite(x) and math.isfinite(y)) for _, x, y in shifts):
            return {"error": f"Non-finite shift in {name} trajectory"}

    ref_map = {f: (x, y) for f, x, y in ref_shifts}
    test_map = {f: (x, y) for f, x, y in test_shifts}

    ref_keys = set(ref_map.keys())
    test_keys = set(test_map.keys())
    if ref_keys != test_keys:
        missing = sorted(ref_keys - test_keys)
        extra = sorted(test_keys - ref_keys)
        mismatch_parts = []
        if missing:
            mismatch_parts.append(f"missing in test: {missing}")
        if extra:
            mismatch_parts.append(f"unexpected extra in test: {extra}")
        return {
            "error": f"Frame set mismatch between reference and test STAR files: {'; '.join(mismatch_parts)}",
            "frame_mismatch": True,
            "ref_num_frames": len(ref_keys),
            "test_num_frames": len(test_keys),
        }

    common_frames = sorted(ref_keys)
    if not common_frames:
        return {"error": "No frames present in trajectory"}

    diffs_x = []
    diffs_y = []
    coord_sq_errs = []

    for f in common_frames:
        rx, ry = ref_map[f]
        tx, ty = test_map[f]
        dx = tx - rx
        dy = ty - ry
        diffs_x.append(dx)
        diffs_y.append(dy)
        coord_sq_errs.append(dx * dx + dy * dy)

    max_abs_dx = max(abs(dx) for dx in diffs_x)
    max_abs_dy = max(abs(dy) for dy in diffs_y)
    max_shift_error = max(max_abs_dx, max_abs_dy)
    coord_rms_error = math.sqrt(sum(coord_sq_errs) / len(coord_sq_errs))

    return {
        "num_frames": len(common_frames),
        "max_abs_diff_x": max_abs_dx,
        "max_abs_diff_y": max_abs_dy,
        "max_shift_error": max_shift_error,
        "coord_rms_error": coord_rms_error,
        "per_frame_diffs": [
            {"frame": f, "dx": dx, "dy": dy}
            for f, dx, dy in zip(common_frames, diffs_x, diffs_y)
        ],
    }


def compare_images(
    ref_pixels: Any,
    test_pixels: Any,
    ref_header: Dict[str, Any],
    test_header: Dict[str, Any],
    ref_raw_header: bytes,
    test_raw_header: bytes,
) -> Dict[str, Any]:
    """Compare pixel arrays and header metadata, normalizing run timestamps."""
    if any(ref_header[key] != test_header[key] for key in ("nx", "ny", "nz", "mode")):
        return {"error": "MRC dimensions or mode differ", "passed": False}
    if ref_pixels.shape != test_pixels.shape:
        return {
            "error": f"Image shape mismatch: {ref_pixels.shape} vs {test_pixels.shape}",
            "passed": False,
        }

    if np is not None and isinstance(ref_pixels, np.ndarray) and isinstance(test_pixels, np.ndarray):
        if not np.isfinite(ref_pixels).all() or not np.isfinite(test_pixels).all():
            return {"error": "Non-finite pixel in reference or test MRC", "passed": False}

        diff = test_pixels.astype(np.float64) - ref_pixels.astype(np.float64)
        abs_diff = np.abs(diff)
        max_abs_err = float(np.max(abs_diff))
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        ref_std = float(np.std(ref_pixels.astype(np.float64)))
        rel_rmse = rmse / max(ref_std, 1e-12)
        ref_min = float(np.min(ref_pixels))
        ref_max = float(np.max(ref_pixels))
        ref_mean = float(np.mean(ref_pixels))
        test_min = float(np.min(test_pixels))
        test_max = float(np.max(test_pixels))
        test_mean = float(np.mean(test_pixels))
        test_std = float(np.std(test_pixels))
    else:
        ref_seq = list(ref_pixels)
        test_seq = list(test_pixels)
        for r, t in zip(ref_seq, test_seq):
            if not math.isfinite(r) or not math.isfinite(t):
                return {"error": "Non-finite pixel in reference or test MRC", "passed": False}
        n = len(ref_seq)
        diffs = [float(t) - float(r) for r, t in zip(ref_seq, test_seq)]
        abs_diffs = [abs(d) for d in diffs]
        max_abs_err = max(abs_diffs) if abs_diffs else 0.0
        sum_sq = sum(d * d for d in diffs)
        rmse = math.sqrt(sum_sq / n) if n else 0.0
        ref_min = float(min(ref_seq))
        ref_max = float(max(ref_seq))
        ref_mean = float(sum(ref_seq) / n)
        ref_var = sum((x - ref_mean) ** 2 for x in ref_seq) / n
        ref_std = math.sqrt(ref_var)
        rel_rmse = rmse / max(ref_std, 1e-12)
        test_min = float(min(test_seq))
        test_max = float(max(test_seq))
        test_mean = float(sum(test_seq) / n)
        test_var = sum((x - test_mean) ** 2 for x in test_seq) / n
        test_std = math.sqrt(test_var)

    # Compare every header byte except RELION's run timestamp in the first label.
    core_header_diff = sum(b1 != b2 for b1, b2 in zip(ref_raw_header[:224], test_raw_header[:224]))
    label_diff = sum(b1 != b2 for b1, b2 in zip(ref_raw_header[224:1024], test_raw_header[224:1024]))
    normalized_label_diff = sum(
        b1 != b2 for b1, b2 in zip(
            normalized_mrc_labels(ref_raw_header), normalized_mrc_labels(test_raw_header)
        )
    )

    return {
        "num_pixels": int(ref_pixels.size),
        "pixel_identical": ref_pixels.tobytes() == test_pixels.tobytes(),
        "max_abs_pixel_error": max_abs_err,
        "rmse": rmse,
        "relative_rmse": rel_rmse,
        "ref_pixel_min": ref_min,
        "ref_pixel_max": ref_max,
        "ref_pixel_mean": ref_mean,
        "ref_pixel_std": ref_std,
        "test_pixel_min": test_min,
        "test_pixel_max": test_max,
        "test_pixel_mean": test_mean,
        "test_pixel_std": test_std,
        "core_header_diff_bytes": core_header_diff,
        "label_header_diff_bytes": label_diff,
        "normalized_label_diff_bytes": normalized_label_diff,
    }


def compare_star_fields(
    ref_star: Dict[str, Any],
    test_star: Dict[str, Any],
    float_tol: float = 1e-4,
    compare_motion_values: bool = True,
) -> Dict[str, Any]:
    """Compare STAR schema and metadata; exact mode also compares motion values."""
    diffs = []
    all_blocks = set(ref_star.keys()) | set(test_star.keys())
    path_labels = {
        "_rlnMicrographMovieName", "_rlnMicrographName", "_rlnMicrographMetadata",
        "_rlnMicrographGainName", "_rlnMicrographDefectFile",
    }
    derived_motion_labels = {
        "_rlnMicrographShiftX", "_rlnMicrographShiftY",
        "_rlnMotionModelCoeff", "_rlnAccumMotionTotal",
        "_rlnAccumMotionEarly", "_rlnAccumMotionLate",
    }

    def values_match(label: str, ref_value: str, test_value: str) -> bool:
        if label in path_labels:
            return normalize_path(ref_value) == normalize_path(test_value)
        try:
            ref_number, test_number = float(ref_value), float(test_value)
        except ValueError:
            return ref_value == test_value
        return (
            math.isfinite(ref_number)
            and math.isfinite(test_number)
            and abs(ref_number - test_number) <= float_tol
        )

    for block_name in sorted(all_blocks):
        if block_name not in ref_star:
            diffs.append(f"Block '{block_name}' missing in reference")
            continue
        if block_name not in test_star:
            diffs.append(f"Block '{block_name}' missing in test")
            continue

        rb = ref_star[block_name]
        tb = test_star[block_name]
        if rb["type"] != tb["type"]:
            diffs.append(f"Block '{block_name}' type mismatch: {rb['type']} vs {tb['type']}")
            continue

        if rb["type"] == "kv":
            rf = rb["fields"]
            tf = tb["fields"]
            keys = set(rf.keys()) | set(tf.keys())
            for k in sorted(keys):
                rv = rf.get(k)
                tv = tf.get(k)
                if rv is None or tv is None:
                    diffs.append(f"Field '{k}' presence mismatch in block '{block_name}'")
                    continue
                if not compare_motion_values and k in derived_motion_labels:
                    continue
                if not values_match(k, rv, tv):
                    diffs.append(f"Value diff in {block_name}.{k}: {rv} vs {tv}")
        elif rb["type"] == "loop":
            rc = rb.get("labels", [])
            tc = tb.get("labels", [])
            if rc != tc:
                diffs.append(f"Loop '{block_name}' column mismatch: {rc} vs {tc}")
            rr = rb.get("rows", [])
            tr = tb.get("rows", [])
            if len(rr) != len(tr):
                diffs.append(f"Loop '{block_name}' row count mismatch: {len(rr)} vs {len(tr)}")
            if rc != tc:
                continue
            for row_number, (ref_row, test_row) in enumerate(zip(rr, tr), start=1):
                if len(ref_row) != len(rc) or len(test_row) != len(tc):
                    diffs.append(f"Loop '{block_name}' row {row_number} has malformed column count")
                    continue
                for label, ref_value, test_value in zip(rc, ref_row, test_row):
                    if not compare_motion_values and label in derived_motion_labels:
                        continue
                    if not values_match(label, ref_value, test_value):
                        diffs.append(
                            f"Value diff in {block_name} row {row_number} {label}: "
                            f"{ref_value} vs {test_value}"
                        )

    return {
        "num_differences": len(diffs),
        "differences": diffs,
    }


def parse_time_v_log(text: str) -> Dict[str, Any]:
    """Parse output from /usr/bin/time -v."""
    res = {}
    patterns = {
        "user_time_sec": r"User time \(seconds\):\s*([\d\.]+)",
        "system_time_sec": r"System time \(seconds\):\s*([\d\.]+)",
        "cpu_percent": r"Percent of CPU this job got:\s*([\d]+)%",
        "elapsed_str": r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n\r]+)",
        "max_rss_kb": r"Maximum resident set size \(kbytes\):\s*([\d]+)",
        "exit_status": r"Exit status:\s*([\d]+)",
    }
    for k, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            if k in ("user_time_sec", "system_time_sec"):
                res[k] = float(val)
            elif k in ("cpu_percent", "max_rss_kb", "exit_status"):
                res[k] = int(val)
            elif k == "elapsed_str":
                res[k] = val
                # Parse wall time in seconds
                parts = val.split(":")
                if len(parts) == 2:
                    res["elapsed_sec"] = float(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    res["elapsed_sec"] = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

    if "max_rss_kb" in res:
        res["max_rss_mb"] = round(res["max_rss_kb"] / 1024.0, 2)

    return res


def discover_output_files(directory: Path) -> Tuple[Optional[Path], Optional[Path], List[str]]:
    """Discover one movie's outputs; never silently select one of several movies."""
    mrcs = sorted(
        p for p in directory.glob("**/*.mrc")
        if not p.name.endswith(("_noDW.mrc", "_PS.mrc", "_ODD.mrc", "_EVN.mrc"))
    )
    stars = sorted(
        p for p in directory.glob("**/*.star")
        if not p.name.startswith("corrected_micrographs")
    )
    errors = []
    if len(mrcs) > 1:
        errors.append(f"Multiple corrected MRCs in {directory}; specify --ref-mrc or --test-mrc")
    if len(stars) > 1:
        errors.append(f"Multiple movie STAR files in {directory}; specify --ref-star or --test-star")
    return (mrcs[0] if len(mrcs) == 1 else None,
            stars[0] if len(stars) == 1 else None, errors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", type=Path, help="Reference file (.mrc or .star) or output directory")
    parser.add_argument("--test", type=Path, help="Test file (.mrc or .star) or output directory")
    parser.add_argument("--ref-mrc", type=Path, help="Explicit reference MRC path")
    parser.add_argument("--test-mrc", type=Path, help="Explicit test MRC path")
    parser.add_argument("--ref-star", type=Path, help="Explicit reference STAR path")
    parser.add_argument("--test-star", type=Path, help="Explicit test STAR path")
    parser.add_argument("--ref-log", type=Path, help="Reference process benchmark / time -v log")
    parser.add_argument("--test-log", type=Path, help="Test process benchmark / time -v log")
    parser.add_argument("--ground-truth", type=Path, help="JSON file containing known ground truth frame shifts")

    # Gate profiles and custom tolerances
    parser.add_argument(
        "--gate",
        choices=["exact", "relaxed", "custom"],
        default="exact",
        help="Acceptance gate profile: 'exact' (1-thread exact CPU parity: zero pixel error), 'relaxed' (multi-thread/GPU: tolerance-based), 'custom'",
    )
    parser.add_argument("--max-shift-err", type=float, help="Override max frame shift error tolerance in pixels")
    parser.add_argument("--shift-rmse", type=float, help="Override coordinate RMS shift error tolerance in pixels")
    parser.add_argument("--image-rmse", type=float, help="Override image RMSE tolerance")
    parser.add_argument("--image-max-err", type=float, help="Override image max pixel error tolerance")
    parser.add_argument("--image-relative-rmse", type=float, help="Override relative image RMSE tolerance (relaxed/custom gates)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON to stdout")
    parser.add_argument("--json-out", type=Path, help="Write machine-readable JSON report to file")
    args = parser.parse_args()

    # Determine thresholds based on gate
    if args.gate == "exact":
        tol_max_shift = 1e-4
        tol_shift_rmse = 1e-4
        tol_image_rmse = 1e-7
        tol_image_max_err = 1e-7
    elif args.gate == "relaxed":
        tol_max_shift = 0.05
        tol_shift_rmse = 0.02
        tol_image_rmse = 0.02
        tol_image_max_err = 5.0
    else:  # custom
        tol_max_shift = 0.05
        tol_shift_rmse = 0.02
        tol_image_rmse = 0.01
        tol_image_max_err = 5.0

    # Apply command-line overrides
    if args.max_shift_err is not None:
        tol_max_shift = args.max_shift_err
    if args.shift_rmse is not None:
        tol_shift_rmse = args.shift_rmse
    if args.image_rmse is not None:
        tol_image_rmse = args.image_rmse
    if args.image_max_err is not None:
        tol_image_max_err = args.image_max_err
    tol_image_relative_rmse = 1e-3 if args.image_relative_rmse is None else args.image_relative_rmse
    for name, value in (("max shift", tol_max_shift), ("shift RMS", tol_shift_rmse),
                        ("image RMS", tol_image_rmse), ("image maximum", tol_image_max_err),
                        ("relative image RMS", tol_image_relative_rmse)):
        if not math.isfinite(value) or value < 0:
            parser.error(f"{name} tolerance must be finite and nonnegative")

    # Locate files
    ref_mrc = args.ref_mrc
    test_mrc = args.test_mrc
    ref_star = args.ref_star
    test_star = args.test_star
    input_errors = []
    for name, path in (("reference", args.ref), ("test", args.test)):
        if path is None:
            continue
        if not path.exists():
            input_errors.append(f"{name.capitalize()} input does not exist: {path}")
            continue
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix not in (".mrc", ".star"):
                input_errors.append(f"Unsupported {name} input file type: {path}")
            elif name == "reference":
                if suffix == ".mrc" and not ref_mrc:
                    ref_mrc = path
                elif suffix == ".star" and not ref_star:
                    ref_star = path
            else:
                if suffix == ".mrc" and not test_mrc:
                    test_mrc = path
                elif suffix == ".star" and not test_star:
                    test_star = path
        elif path.is_dir():
            found_mrc, found_star, discovery_errors = discover_output_files(path)
            if name == "reference":
                if not ref_mrc:
                    ref_mrc = found_mrc
                if not ref_star:
                    ref_star = found_star
            else:
                if not test_mrc:
                    test_mrc = found_mrc
                if not test_star:
                    test_star = found_star
            if not (ref_mrc if name == "reference" else test_mrc):
                input_errors.extend(e for e in discovery_errors if "MRC" in e)
            if not (ref_star if name == "reference" else test_star):
                input_errors.extend(e for e in discovery_errors if "STAR" in e)

    report: Dict[str, Any] = {
        "gate_profile": args.gate,
        "tolerances": {
            "max_shift_error": tol_max_shift,
            "shift_rmse": tol_shift_rmse,
            "image_rmse": tol_image_rmse,
            "image_max_err": tol_image_max_err,
            "image_relative_rmse": tol_image_relative_rmse,
        },
        "checks": {},
        "overall_status": "PASS",
    }

    gate_passed = True
    num_comparisons_run = 0
    errors = input_errors

    # 1. Compare motion trajectories from STAR files
    if ref_star or test_star:
        if not ref_star or not ref_star.exists():
            gate_passed = False
            errors.append(f"Reference STAR file not found or unresolved: {ref_star}")
        elif not test_star or not test_star.exists():
            gate_passed = False
            errors.append(f"Test STAR file not found or unresolved: {test_star}")
        else:
            num_comparisons_run += 1
            ref_parsed = parse_star_file(ref_star)
            test_parsed = parse_star_file(test_star)
            ref_shifts = extract_global_shifts(ref_parsed)
            test_shifts = extract_global_shifts(test_parsed)

            traj_res = compare_trajectories(ref_shifts, test_shifts)
            star_tol = 1e-4 if args.gate == "exact" else 1e-3
            star_diff_res = compare_star_fields(
                ref_parsed, test_parsed, float_tol=star_tol,
                compare_motion_values=(args.gate == "exact"),
            )

            check_passed = True
            fail_reasons = []
            if "error" in traj_res:
                check_passed = False
                fail_reasons.append(traj_res["error"])
            else:
                if traj_res["max_shift_error"] > tol_max_shift:
                    check_passed = False
                    fail_reasons.append(f"Max shift error {traj_res['max_shift_error']:.6f} > {tol_max_shift:.6f}")
                if traj_res["coord_rms_error"] > tol_shift_rmse:
                    check_passed = False
                    fail_reasons.append(f"Coord RMS shift error {traj_res['coord_rms_error']:.6f} > {tol_shift_rmse:.6f}")

            traj_res["passed"] = check_passed
            traj_res["fail_reasons"] = fail_reasons
            report["checks"]["motion_trajectory"] = traj_res

            star_passed = (star_diff_res["num_differences"] == 0)
            star_diff_res["passed"] = star_passed
            if not star_passed:
                check_passed = False
                star_diff_res["fail_reasons"] = [f"STAR metadata differences: {star_diff_res['num_differences']} discrepancies found"]
                fail_reasons.append(f"STAR metadata differences: {star_diff_res['num_differences']} discrepancies found")
            report["checks"]["star_fields"] = star_diff_res

            if not check_passed or not star_passed:
                gate_passed = False

    # 2. Compare corrected image pixels
    if ref_mrc or test_mrc:
        if not ref_mrc or not ref_mrc.exists():
            gate_passed = False
            errors.append(f"Reference MRC file not found or unresolved: {ref_mrc}")
        elif not test_mrc or not test_mrc.exists():
            gate_passed = False
            errors.append(f"Test MRC file not found or unresolved: {test_mrc}")
        else:
            num_comparisons_run += 1
            ref_h, ref_pix, ref_raw_h = parse_mrc(ref_mrc)
            test_h, test_pix, test_raw_h = parse_mrc(test_mrc)

            img_res = compare_images(ref_pix, test_pix, ref_h, test_h, ref_raw_h, test_raw_h)

            img_passed = True
            img_fail_reasons = []
            if "error" in img_res:
                img_passed = False
                img_fail_reasons.append(img_res["error"])
            else:
                if args.gate == "exact":
                    if not img_res.get("pixel_identical", False):
                        img_passed = False
                        img_fail_reasons.append(f"Pixels not byte-identical in exact gate (max error: {img_res['max_abs_pixel_error']:.6e})")
                    if img_res.get("core_header_diff_bytes", 0) > 0:
                        img_passed = False
                        img_fail_reasons.append(f"Core MRC header mismatch in exact gate: {img_res['core_header_diff_bytes']} diff bytes (expected 0)")
                    if img_res.get("normalized_label_diff_bytes", 0) > 0:
                        img_passed = False
                        img_fail_reasons.append(f"Non-timestamp MRC label mismatch in exact gate: {img_res['normalized_label_diff_bytes']} diff bytes")
                else:
                    if img_res["rmse"] > tol_image_rmse:
                        img_passed = False
                        img_fail_reasons.append(f"Image RMSE {img_res['rmse']:.6e} > {tol_image_rmse:.6e}")
                    if img_res["relative_rmse"] > tol_image_relative_rmse:
                        img_passed = False
                        img_fail_reasons.append(f"Relative image RMSE {img_res['relative_rmse']:.6e} > {tol_image_relative_rmse:.6e}")
                    if img_res["max_abs_pixel_error"] > tol_image_max_err:
                        img_passed = False
                        img_fail_reasons.append(f"Image max pixel error {img_res['max_abs_pixel_error']:.6e} > {tol_image_max_err:.6e}")

            img_res["passed"] = img_passed
            img_res["fail_reasons"] = img_fail_reasons
            report["checks"]["corrected_image"] = img_res

            if not img_passed:
                gate_passed = False

    # 3. Ground truth check (if provided)
    if args.ground_truth:
        if not args.ground_truth.exists():
            gate_passed = False
            errors.append(f"Ground truth file not found: {args.ground_truth}")
        else:
            gt_data = json.loads(args.ground_truth.read_text())
            expected_shifts = gt_data.get("expected_alignment_shifts_xy", [])
            if test_star and test_star.exists():
                test_parsed = parse_star_file(test_star)
                test_shifts = extract_global_shifts(test_parsed)
                # compare against GT
                gt_tuples = [(i + 1, float(sx), float(sy)) for i, (sx, sy) in enumerate(expected_shifts)]
                gt_comp = compare_trajectories(gt_tuples, test_shifts)
                report["checks"]["ground_truth_recovery"] = gt_comp
                if "error" in gt_comp:
                    gate_passed = False
                    errors.append(f"Ground truth could not be evaluated: {gt_comp['error']}")
            else:
                gate_passed = False
                errors.append("Ground truth requested but no test movie STAR was resolved")

    # 4. Performance & metrics from log files
    if args.test_log:
        if not args.test_log.exists():
            gate_passed = False
            errors.append(f"Test log file not found: {args.test_log}")
        else:
            log_metrics = parse_time_v_log(args.test_log.read_text())
            report["metrics"] = log_metrics
            for required in ("elapsed_sec", "max_rss_kb", "exit_status"):
                if required not in log_metrics:
                    gate_passed = False
                    errors.append(f"Test process log has no parseable {required}")
            if log_metrics.get("exit_status") is None:
                gate_passed = False
            elif log_metrics["exit_status"] != 0:
                gate_passed = False
                errors.append(f"Test process log indicates failure: Exit status {log_metrics['exit_status']} != 0")

    if args.ref_log:
        if not args.ref_log.exists():
            gate_passed = False
            errors.append(f"Reference log file not found: {args.ref_log}")
        else:
            report["ref_metrics"] = parse_time_v_log(args.ref_log.read_text())

    # Require at least one complete comparison check to run
    if num_comparisons_run == 0:
        gate_passed = False
        errors.append(
            "No comparison inputs were resolved or found. Specify valid reference and test files/directories with --ref and --test, or explicit --ref-star / --test-star / --ref-mrc / --test-mrc."
        )

    report["coverage"] = {
        "motion_and_star": "motion_trajectory" in report["checks"] and "star_fields" in report["checks"],
        "corrected_image": "corrected_image" in report["checks"],
    }
    report["coverage"]["complete"] = all(report["coverage"].values())

    if errors:
        report["errors"] = errors

    report["overall_status"] = "PASS" if gate_passed else "FAIL"

    # Write output
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        # Formatted human-readable output
        print("=" * 72)
        print(" MOTIONCORR ACCEPTANCE GATE REPORT")
        print("=" * 72)
        print(f"Gate Profile:      {args.gate.upper()}")
        print(f"Overall Status:    {report['overall_status']}")
        if not report["coverage"]["complete"]:
            print("Coverage:          PARTIAL (PASS/FAIL applies only to supplied comparison pairs)")
        print("-" * 72)

        if errors:
            print("ERRORS / UNRESOLVED INPUTS:")
            for err in errors:
                print(f"   ! {err}")
            print("-" * 72)

        if "motion_trajectory" in report["checks"]:
            t = report["checks"]["motion_trajectory"]
            print("1. MOTION TRAJECTORY:")
            if "error" in t:
                print(f"   ERROR: {t['error']}")
            else:
                print(f"   Frames evaluated:     {t['num_frames']}")
                print(f"   Coordinate RMS error: {t['coord_rms_error']:.6f} px (threshold: {tol_shift_rmse:.6f})")
                print(f"   Max absolute shift:   {t['max_shift_error']:.6f} px (threshold: {tol_max_shift:.6f})")
                print(f"   Status:               {'PASS' if t['passed'] else 'FAIL'}")
                if not t["passed"]:
                    for r in t["fail_reasons"]:
                        print(f"     ! {r}")

        if "corrected_image" in report["checks"]:
            im = report["checks"]["corrected_image"]
            print("\n2. CORRECTED IMAGE PARITY:")
            if "error" in im:
                print(f"   ERROR: {im['error']}")
            else:
                print(f"   Pixel-identical:      {im['pixel_identical']}")
                print(f"   Image RMSE:           {im['rmse']:.6e} (threshold: {tol_image_rmse:.6e})")
                print(f"   Max absolute diff:    {im['max_abs_pixel_error']:.6e} (threshold: {tol_image_max_err:.6e})")
                print(f"   Relative RMSE:        {im['relative_rmse']:.6e} (threshold: {tol_image_relative_rmse:.6e} in relaxed/custom gate)")
                print(f"   Normalized headers:   Core metadata: {im['core_header_diff_bytes']} diff bytes, Non-timestamp labels: {im['normalized_label_diff_bytes']} diff bytes")
                print(f"   Status:               {'PASS' if im['passed'] else 'FAIL'}")
                if not im["passed"]:
                    for r in im["fail_reasons"]:
                        print(f"     ! {r}")

        if "star_fields" in report["checks"]:
            sf = report["checks"]["star_fields"]
            print("\n3. STAR FIELDS & METADATA:")
            print(f"   Normalized diff count: {sf['num_differences']}")
            print(f"   Status:                {'PASS' if sf['passed'] else 'FAIL'}")
            if sf["num_differences"] > 0:
                for d in sf["differences"][:5]:
                    print(f"     - {d}")

        if "ground_truth_recovery" in report["checks"]:
            gt = report["checks"]["ground_truth_recovery"]
            print("\n4. GROUND TRUTH RECOVERY ACCURACY:")
            if "error" in gt:
                print(f"   ERROR: {gt['error']}")
            else:
                print(f"   Coordinate RMS error against known shifts: {gt['coord_rms_error']:.6f} px")
                print(f"   Max absolute shift error against known shifts: {gt['max_shift_error']:.6f} px")

        if "metrics" in report:
            m = report["metrics"]
            print("\n5. PROCESS METRICS:")
            if "elapsed_str" in m:
                print(f"   Wall clock time:      {m['elapsed_str']}")
            if "user_time_sec" in m:
                print(f"   User CPU time:        {m['user_time_sec']:.2f} s")
            if "max_rss_mb" in m:
                print(f"   Peak RSS memory:      {m['max_rss_mb']} MB ({m['max_rss_kb']} KB)")
            if "exit_status" in m:
                print(f"   Process exit status:  {m['exit_status']}")

        print("=" * 72)

    sys.exit(0 if gate_passed else 1)


if __name__ == "__main__":
    main()
