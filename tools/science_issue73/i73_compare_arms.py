#!/usr/bin/env python3
"""Compare two arms' corrected micrographs and trajectories on identical input.

Reports the ADR #66 section 4 backend-comparator quantities directly on the
corrected output, *before* any re-estimation step that could absorb a
difference.  Exit status and run counts are deliberately not part of the
verdict: only pixels and shifts are.

The ADR #66 thresholds are reproduced here as read-only reference values so
the report is self-describing.  This tool does not define, tune or change any
threshold, and nothing here feeds the production comparator.  Relative image
RMSE is carried at its ADR #66 reporting level with blocking = false; it is a
diagnostic and is never promoted to a scientific conclusion.

Usage:
    python3 i73_compare_arms.py --a-mrc A.mrc --a-star A.star \
                                --b-mrc B.mrc --b-star B.star \
                                [--a-label cpu] [--b-label cuda]
"""

import argparse
import json
import struct
import sys

import numpy as np

# ADR #66 section 4, quoted. Read-only: this tool never edits these.
ADR66 = {
    "absolute_image_rmse":            {"threshold": 0.020, "blocking": True},
    "max_abs_pixel_error":            {"threshold": 5.0,   "blocking": True},
    "global_trajectory_vector_rms_px": {"threshold": 0.02,  "blocking": True},
    "max_per_axis_global_shift_diff_px": {"threshold": 0.05, "blocking": True},
    "static_star_discrepancies":      {"threshold": 0,     "blocking": True},
    "relative_image_rmse":            {"threshold": 0.001, "blocking": False},
}

MRC_MODES = {0: np.int8, 1: np.int16, 2: np.float32, 6: np.uint16, 12: np.float16}

# data_general keys that must agree exactly between arms: these describe the
# input and the rendering, so any difference means the arms were not matched.
STATIC_KEYS = (
    "_rlnImageSizeX", "_rlnImageSizeY", "_rlnImageSizeZ",
    "_rlnMicrographBinning", "_rlnMicrographOriginalPixelSize",
    "_rlnMicrographDoseRate", "_rlnMicrographPreExposure", "_rlnVoltage",
    "_rlnMicrographStartFrame", "_rlnEERUpsampling", "_rlnEERGrouping",
    "_rlnMotionModelVersion",
)


def read_mrc(path):
    with open(path, "rb") as fh:
        hdr = fh.read(1024)
        nx, ny, nz, mode = struct.unpack("<4i", hdr[0:16])
        mx, my, _ = struct.unpack("<3i", hdr[28:40])
        xlen, ylen, _ = struct.unpack("<3f", hdr[40:52])
        nsymbt = struct.unpack("<i", hdr[92:96])[0]
        fh.seek(1024 + nsymbt)
        n = nx * ny * max(nz, 1)
        data = np.frombuffer(fh.read(n * np.dtype(MRC_MODES[mode]).itemsize),
                             dtype=MRC_MODES[mode])
    return data.reshape(max(nz, 1), ny, nx)[0].astype(np.float64), {
        "nx": nx, "ny": ny, "mode": int(mode),
        "pixel_size_A": (xlen / mx) if mx else None,
        "pixel_size_A_y": (ylen / my) if my else None,
    }


def read_star(path):
    """Minimal RELION STAR reader: returns {block: {'pairs':…, 'rows':…}}."""
    blocks, cur, mode, cols = {}, None, None, []
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("data_"):
            cur = line
            blocks[cur] = {"pairs": {}, "cols": [], "rows": []}
            mode, cols = "pairs", []
            continue
        if cur is None:
            continue
        if line.startswith("loop_"):
            mode, cols = "loop_header", []
            continue
        if mode == "loop_header" and line.startswith("_"):
            cols.append(line.split()[0])
            blocks[cur]["cols"] = cols
            continue
        if mode == "loop_header":
            mode = "rows"
        if mode == "rows":
            blocks[cur]["rows"].append(line.split())
        elif mode == "pairs" and line.startswith("_"):
            parts = line.split(None, 1)
            blocks[cur]["pairs"][parts[0]] = parts[1].strip() if len(parts) > 1 else ""
    return blocks


def shift_table(blocks):
    b = blocks.get("data_global_shift")
    if not b or not b["rows"]:
        return None
    cols = b["cols"]
    ix = cols.index("_rlnMicrographShiftX")
    iy = cols.index("_rlnMicrographShiftY")
    return np.array([[float(r[ix]), float(r[iy])] for r in b["rows"]], dtype=np.float64)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-mrc", required=True)
    ap.add_argument("--a-star", required=True)
    ap.add_argument("--b-mrc", required=True)
    ap.add_argument("--b-star", required=True)
    ap.add_argument("--a-label", default="a")
    ap.add_argument("--b-label", default="b")
    args = ap.parse_args()

    A, ha = read_mrc(args.a_mrc)
    B, hb = read_mrc(args.b_mrc)
    out = {"arms": {args.a_label: args.a_mrc, args.b_label: args.b_mrc},
           "headers": {args.a_label: ha, args.b_label: hb},
           "adr66_reference_thresholds": ADR66}

    if A.shape != B.shape:
        out["error"] = f"shape mismatch {A.shape} vs {B.shape}: arms are not comparable"
        print(json.dumps(out, indent=2))
        return 1

    diff = A - B
    abs_rmse = float(np.sqrt(np.mean(diff ** 2)))
    max_abs = float(np.max(np.abs(diff)))
    # Relative RMSE normalised by the reference arm's RMS signal, which is the
    # scale the absolute figure is otherwise silent about.
    rms_a = float(np.sqrt(np.mean(A ** 2)))
    rel_rmse = abs_rmse / rms_a if rms_a > 0 else float("nan")

    out["image"] = {
        "absolute_image_rmse": abs_rmse,
        "relative_image_rmse": rel_rmse,
        "max_abs_pixel_error": max_abs,
        "identical_bitwise": bool(np.array_equal(A, B)),
        "n_differing_pixels": int(np.count_nonzero(diff)),
        "n_pixels": int(A.size),
        f"rms_{args.a_label}": rms_a,
        f"mean_{args.a_label}": float(A.mean()),
        f"mean_{args.b_label}": float(B.mean()),
        f"std_{args.a_label}": float(A.std()),
        f"std_{args.b_label}": float(B.std()),
    }

    sa, sb = read_star(args.a_star), read_star(args.b_star)
    ta, tb = shift_table(sa), shift_table(sb)
    if ta is None or tb is None or ta.shape != tb.shape:
        out["trajectory"] = {"error": "global shift tables missing or different length"}
    else:
        d = ta - tb
        out["trajectory"] = {
            "n_frames": int(ta.shape[0]),
            "global_trajectory_vector_rms_px": float(np.sqrt(np.mean(np.sum(d ** 2, axis=1)))),
            "max_per_axis_global_shift_diff_px": float(np.max(np.abs(d))),
            "max_vector_shift_diff_px": float(np.max(np.sqrt(np.sum(d ** 2, axis=1)))),
        }

    ga = sa.get("data_general", {}).get("pairs", {})
    gb = sb.get("data_general", {}).get("pairs", {})
    mismatches = {k: [ga.get(k), gb.get(k)] for k in STATIC_KEYS if ga.get(k) != gb.get(k)}
    out["static_star"] = {
        "compared_keys": list(STATIC_KEYS),
        "static_star_discrepancies": len(mismatches),
        "mismatches": mismatches,
        f"{args.a_label}_general": ga,
        f"{args.b_label}_general": gb,
    }

    checks = {}
    for name, ref in ADR66.items():
        # Look the metric up by key presence, not truthiness: a metric of exactly
        # 0.0 is the *most* informative result there is (perfect agreement) and
        # `a or b or c` would discard it and report UNMEASURED.
        val = None
        for section in (out["image"], out.get("trajectory", {}), out["static_star"]):
            if name in section:
                val = section[name]
                break
        if val is None:
            checks[name] = {"value": None, "state": "UNMEASURED"}
            continue
        within = val <= ref["threshold"]
        checks[name] = {
            "value": val, "threshold": ref["threshold"], "within": bool(within),
            "blocking": ref["blocking"],
            "state": ("WITHIN" if within else
                      ("EXCEEDS_BLOCKING" if ref["blocking"] else "EXCEEDS_NONBLOCKING")),
        }
    out["checks"] = checks
    blocking_fail = [k for k, v in checks.items()
                     if v.get("blocking") and v.get("state") == "EXCEEDS_BLOCKING"]
    out["blocking_failures"] = blocking_fail
    out["scope"] = (
        "Image-level agreement on the corrected micrograph for the movies compared here, "
        "and nothing more. This is not a resolution, FSC or signal-equivalence claim, and "
        "on the feasibility subset it is explicitly underpowered for any such claim "
        "(PROTOCOL.md section 10). Relative image RMSE is a non-blocking diagnostic per "
        "ADR #66 section 4.")

    print(json.dumps(out, indent=2))
    return 1 if blocking_fail else 0


if __name__ == "__main__":
    sys.exit(main())
