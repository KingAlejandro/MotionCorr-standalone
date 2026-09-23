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

import numpy as np


def parse_mrc(filepath: Path) -> Tuple[Dict[str, Any], np.ndarray, bytes]:
    """Parse MRC 2014 file header and pixel data."""
    raw = filepath.read_bytes()
    if len(raw) < 1024:
        raise ValueError(f"File too short for MRC header: {filepath} ({len(raw)} bytes)")

    header_bytes = raw[:1024]
    nx, ny, nz, mode = struct.unpack_from("<4i", header_bytes, 0)
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

    dtype_map = {
        0: np.int8,
        1: np.int16,
        2: np.float32,
        6: np.uint16,
        12: np.float16,
    }
    if mode not in dtype_map:
        raise ValueError(f"Unsupported MRC mode {mode} in {filepath}")

    expected_pixels = nx * ny * nz
    pixel_data = np.frombuffer(raw[1024:], dtype=dtype_map[mode])
    if pixel_data.size != expected_pixels:
        # Some formats have extended header; handle offset if needed
        data_offset = len(raw) - expected_pixels * pixel_data.itemsize
        if data_offset >= 1024:
            pixel_data = np.frombuffer(raw[data_offset:], dtype=dtype_map[mode])

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
        if len(row) > max(frame_idx, x_idx, y_idx):
            f_num = int(row[frame_idx])
            sx = float(row[x_idx])
            sy = float(row[y_idx])
            shifts.append((f_num, sx, sy))
    return shifts


def normalize_path(p: str) -> str:
    """Normalize file path to basename or last 2 segments for fair comparison."""
    parts = Path(p).parts
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return Path(p).name


def compare_trajectories(
    ref_shifts: List[Tuple[int, float, float]],
    test_shifts: List[Tuple[int, float, float]],
) -> Dict[str, Any]:
    """Compare two motion trajectories and compute error metrics."""
    if not ref_shifts or not test_shifts:
        return {"error": "Missing shifts in reference or test STAR file"}

    ref_map = {f: (x, y) for f, x, y in ref_shifts}
    test_map = {f: (x, y) for f, x, y in test_shifts}
    common_frames = sorted(set(ref_map.keys()) & set(test_map.keys()))

    if not common_frames:
        return {"error": "No overlapping frames"}

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
    ref_pixels: np.ndarray,
    test_pixels: np.ndarray,
    ref_header: Dict[str, Any],
    test_header: Dict[str, Any],
    ref_raw_header: bytes,
    test_raw_header: bytes,
) -> Dict[str, Any]:
    """Compare pixel arrays and header metadata, normalizing run timestamps."""
    if ref_pixels.shape != test_pixels.shape:
        return {
            "error": f"Image shape mismatch: {ref_pixels.shape} vs {test_pixels.shape}",
            "passed": False,
        }

    diff = test_pixels.astype(np.float64) - ref_pixels.astype(np.float64)
    abs_diff = np.abs(diff)
    max_abs_err = float(np.max(abs_diff))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    ref_std = float(ref_header.get("rms", np.std(ref_pixels)))
    rel_rmse = (rmse / ref_std) if ref_std > 1e-12 else 0.0

    # Header comparison excluding timestamp labels (offset 224 to 1024)
    # Binary header metadata check (0..224)
    core_header_diff = sum(b1 != b2 for b1, b2 in zip(ref_raw_header[:224], test_raw_header[:224]))

    # Label diff check
    label_diff = sum(b1 != b2 for b1, b2 in zip(ref_raw_header[224:1024], test_raw_header[224:1024]))

    return {
        "num_pixels": int(ref_pixels.size),
        "pixel_identical": (max_abs_err == 0.0),
        "max_abs_pixel_error": max_abs_err,
        "rmse": rmse,
        "relative_rmse": rel_rmse,
        "ref_pixel_min": float(np.min(ref_pixels)),
        "ref_pixel_max": float(np.max(ref_pixels)),
        "ref_pixel_mean": float(np.mean(ref_pixels)),
        "ref_pixel_std": ref_std,
        "test_pixel_min": float(np.min(test_pixels)),
        "test_pixel_max": float(np.max(test_pixels)),
        "test_pixel_mean": float(np.mean(test_pixels)),
        "test_pixel_std": float(np.std(test_pixels)),
        "core_header_diff_bytes": core_header_diff,
        "label_header_diff_bytes": label_diff,
    }


def compare_star_fields(
    ref_star: Dict[str, Any],
    test_star: Dict[str, Any],
    float_tol: float = 1e-4,
) -> Dict[str, Any]:
    """Compare STAR file fields with path and float normalization."""
    diffs = []
    all_blocks = set(ref_star.keys()) | set(test_star.keys())

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
                # Normalize paths
                if "MovieName" in k or "MicrographName" in k or "Metadata" in k:
                    if normalize_path(rv) != normalize_path(tv):
                        diffs.append(f"Path mismatch in {block_name}.{k}: {rv} vs {tv}")
                    continue
                # Try float comparison
                try:
                    rf_val = float(rv)
                    tf_val = float(tv)
                    if abs(rf_val - tf_val) > float_tol:
                        diffs.append(f"Value diff in {block_name}.{k}: {rv} vs {tv}")
                except ValueError:
                    if rv != tv:
                        diffs.append(f"String diff in {block_name}.{k}: {rv} vs {tv}")

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
        tol_image_max_err = 3.0
    else:  # custom
        tol_max_shift = 0.05
        tol_shift_rmse = 0.02
        tol_image_rmse = 0.01
        tol_image_max_err = 0.5

    # Apply command-line overrides
    if args.max_shift_err is not None:
        tol_max_shift = args.max_shift_err
    if args.shift_rmse is not None:
        tol_shift_rmse = args.shift_rmse
    if args.image_rmse is not None:
        tol_image_rmse = args.image_rmse
    if args.image_max_err is not None:
        tol_image_max_err = args.image_max_err

    # Locate files
    ref_mrc = args.ref_mrc
    test_mrc = args.test_mrc
    ref_star = args.ref_star
    test_star = args.test_star

    if args.ref and args.ref.is_dir():
        # Look for movie mrc and star inside ref directory
        mrcs = sorted(args.ref.glob("**/*.mrc"))
        # Exclude noDW if main exists, or pick main
        main_mrcs = [m for m in mrcs if not m.name.endswith("_noDW.mrc")]
        if main_mrcs and not ref_mrc:
            ref_mrc = main_mrcs[0]
        elif mrcs and not ref_mrc:
            ref_mrc = mrcs[0]

        stars = sorted(args.ref.glob("**/*.star"))
        movie_stars = [s for s in stars if not s.name.startswith("corrected_micrographs")]
        if movie_stars and not ref_star:
            ref_star = movie_stars[0]
        elif stars and not ref_star:
            ref_star = stars[0]

    if args.test and args.test.is_dir():
        mrcs = sorted(args.test.glob("**/*.mrc"))
        main_mrcs = [m for m in mrcs if not m.name.endswith("_noDW.mrc")]
        if main_mrcs and not test_mrc:
            test_mrc = main_mrcs[0]
        elif mrcs and not test_mrc:
            test_mrc = mrcs[0]

        stars = sorted(args.test.glob("**/*.star"))
        movie_stars = [s for s in stars if not s.name.startswith("corrected_micrographs")]
        if movie_stars and not test_star:
            test_star = movie_stars[0]
        elif stars and not test_star:
            test_star = stars[0]

    report: Dict[str, Any] = {
        "gate_profile": args.gate,
        "tolerances": {
            "max_shift_error": tol_max_shift,
            "shift_rmse": tol_shift_rmse,
            "image_rmse": tol_image_rmse,
            "image_max_err": tol_image_max_err,
        },
        "checks": {},
        "overall_status": "PASS",
    }

    gate_passed = True

    # 1. Compare motion trajectories from STAR files
    if ref_star and test_star and ref_star.exists() and test_star.exists():
        ref_parsed = parse_star_file(ref_star)
        test_parsed = parse_star_file(test_star)
        ref_shifts = extract_global_shifts(ref_parsed)
        test_shifts = extract_global_shifts(test_parsed)

        traj_res = compare_trajectories(ref_shifts, test_shifts)
        star_diff_res = compare_star_fields(ref_parsed, test_parsed)

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
        report["checks"]["star_fields"] = star_diff_res

        if not check_passed:
            gate_passed = False

    # 2. Compare corrected image pixels
    if ref_mrc and test_mrc and ref_mrc.exists() and test_mrc.exists():
        ref_h, ref_pix, ref_raw_h = parse_mrc(ref_mrc)
        test_h, test_pix, test_raw_h = parse_mrc(test_mrc)

        img_res = compare_images(ref_pix, test_pix, ref_h, test_h, ref_raw_h, test_raw_h)

        img_passed = True
        img_fail_reasons = []
        if "error" in img_res:
            img_passed = False
            img_fail_reasons.append(img_res["error"])
        else:
            if img_res["rmse"] > tol_image_rmse and img_res["relative_rmse"] > 1e-3:
                img_passed = False
                img_fail_reasons.append(f"Image RMSE {img_res['rmse']:.6e} > {tol_image_rmse:.6e} and relative RMSE {img_res['relative_rmse']:.6e} > 1e-3")
            if img_res["max_abs_pixel_error"] > tol_image_max_err:
                img_passed = False
                img_fail_reasons.append(f"Image max pixel error {img_res['max_abs_pixel_error']:.6e} > {tol_image_max_err:.6e}")

        img_res["passed"] = img_passed
        img_res["fail_reasons"] = img_fail_reasons
        report["checks"]["corrected_image"] = img_res

        if not img_passed:
            gate_passed = False

    # 3. Ground truth check (if provided)
    if args.ground_truth and args.ground_truth.exists():
        gt_data = json.loads(args.ground_truth.read_text())
        expected_shifts = gt_data.get("expected_alignment_shifts_xy", [])
        if test_star and test_star.exists():
            test_parsed = parse_star_file(test_star)
            test_shifts = extract_global_shifts(test_parsed)
            # compare against GT
            gt_tuples = [(i + 1, float(sx), float(sy)) for i, (sx, sy) in enumerate(expected_shifts)]
            gt_comp = compare_trajectories(gt_tuples, test_shifts)
            report["checks"]["ground_truth_recovery"] = gt_comp

    # 4. Performance & metrics from log files
    if args.test_log and args.test_log.exists():
        report["metrics"] = parse_time_v_log(args.test_log.read_text())

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
                print(f"   Relative RMSE:        {im['relative_rmse']:.6e}")
                print(f"   Normalized headers:   Core metadata: {im['core_header_diff_bytes']} diff bytes, Label/timestamp: {im['label_header_diff_bytes']} diff bytes")
                print(f"   Status:               {'PASS' if im['passed'] else 'FAIL'}")
                if not im["passed"]:
                    for r in im["fail_reasons"]:
                        print(f"     ! {r}")

        if "star_fields" in report["checks"]:
            sf = report["checks"]["star_fields"]
            print("\n3. STAR FIELDS & METADATA:")
            print(f"   Normalized diff count: {sf['num_differences']}")
            if sf["num_differences"] > 0:
                for d in sf["differences"][:5]:
                    print(f"     - {d}")

        if "ground_truth_recovery" in report["checks"]:
            gt = report["checks"]["ground_truth_recovery"]
            print("\n4. GROUND TRUTH RECOVERY ACCURACY:")
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
