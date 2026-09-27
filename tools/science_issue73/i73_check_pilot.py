#!/usr/bin/env python3
"""Check a corrected micrograph against the deposited EMPIAR-12963 particles.

This answers the three questions PROTOCOL.md section 8 step 2 asks of the
feasibility pilot, and nothing else:

  1. Is the corrected micrograph 8192 x 8192 at 0.485 A?   (MRC header)
  2. Is the gain orientation right?                        (particle contrast)
  3. Do the deposited fractional coordinates land on real particles?

Question 3 is scored by local contrast: for each deposited particle, the mean
of an inner disc minus the mean of a surrounding annulus, compared against the
same statistic at matched random positions.  Protein is denser than vitreous
ice, so a correctly rendered micrograph separates the two populations.  The
separation is reported as an AUC (Mann-Whitney U / n1 n2): 0.5 is no signal,
1.0 is perfect separation.

Both y-axis conventions are scored, because CryoSPARC's fractional origin and
the MRC row order need not agree.  Whichever wins is a property of the
metadata, not of either backend, and is reported rather than assumed.

This is a plumbing and orientation check on two development movies.  It is NOT
an endpoint, it evaluates no backend difference, and it establishes no signal
equivalence -- see PROTOCOL.md section 10.

Usage:
    python3 i73_check_pilot.py --mrc CORRECTED.mrc --movie BASENAME \
        --passthrough J189_passthrough_particles.cs [--seed 73]
"""

import argparse
import json
import re
import struct
import sys

import numpy as np

MRC_MODES = {0: np.int8, 1: np.int16, 2: np.float32, 6: np.uint16, 12: np.float16}

# Contrast measure, in pixels at 0.485 A (box is 448 px in the deposition).
R_INNER, R_IN_ANN, R_OUT_ANN = 80, 110, 150


def read_mrc(path):
    """Read an MRC2014 image; return (array, header dict). No external deps."""
    with open(path, "rb") as fh:
        hdr = fh.read(1024)
        nx, ny, nz, mode = struct.unpack("<4i", hdr[0:16])
        mx, my, mz = struct.unpack("<3i", hdr[28:40])
        xlen, ylen, zlen = struct.unpack("<3f", hdr[40:52])
        nsymbt = struct.unpack("<i", hdr[92:96])[0]
        if mode not in MRC_MODES:
            raise ValueError(f"{path}: unsupported MRC mode {mode}")
        fh.seek(1024 + nsymbt)
        data = np.frombuffer(fh.read(nx * ny * max(nz, 1) * np.dtype(MRC_MODES[mode]).itemsize),
                             dtype=MRC_MODES[mode])
    info = {
        "nx": nx, "ny": ny, "nz": nz, "mode": int(mode),
        "pixel_size_A_x": (xlen / mx) if mx else None,
        "pixel_size_A_y": (ylen / my) if my else None,
    }
    return data.reshape(max(nz, 1), ny, nx)[0].astype(np.float32), info


def contrast(img, xs, ys):
    """Inner-disc minus annulus mean at each (x, y). Positions too close to an
    edge are dropped, so the caller must compare returned lengths, not inputs."""
    h, w = img.shape
    yy, xx = np.ogrid[-R_OUT_ANN:R_OUT_ANN + 1, -R_OUT_ANN:R_OUT_ANN + 1]
    rr = xx * xx + yy * yy
    disc = rr <= R_INNER * R_INNER
    ann = (rr >= R_IN_ANN * R_IN_ANN) & (rr <= R_OUT_ANN * R_OUT_ANN)

    out = []
    for x, y in zip(xs, ys):
        x, y = int(round(x)), int(round(y))
        if not (R_OUT_ANN <= x < w - R_OUT_ANN and R_OUT_ANN <= y < h - R_OUT_ANN):
            continue
        patch = img[y - R_OUT_ANN:y + R_OUT_ANN + 1, x - R_OUT_ANN:x + R_OUT_ANN + 1]
        out.append(float(patch[disc].mean() - patch[ann].mean()))
    return np.asarray(out)


def auc(pos, neg):
    """Mann-Whitney AUC that |pos| exceeds |neg| in magnitude, ties at 0.5.

    Contrast sign depends on display convention, so rank on |contrast|: the
    question is whether particle sites differ from background, not which way."""
    if len(pos) == 0 or len(neg) == 0:
        return None
    a, b = np.abs(pos), np.abs(neg)
    allv = np.concatenate([a, b])
    ranks = np.empty(len(allv), dtype=np.float64)
    order = np.argsort(allv, kind="mergesort")
    sortv = allv[order]
    i = 0
    while i < len(sortv):  # average ranks within tie groups
        j = i
        while j + 1 < len(sortv) and sortv[j + 1] == sortv[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    r1 = ranks[:len(a)].sum()
    return float((r1 - len(a) * (len(a) + 1) / 2.0) / (len(a) * len(b)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mrc", required=True, help="corrected micrograph from either arm")
    ap.add_argument("--movie", required=True, help="movie basename to select particles for")
    ap.add_argument("--passthrough", required=True, help="J189_passthrough_particles.cs")
    ap.add_argument("--seed", type=int, default=73, help="seed for the random control positions")
    args = ap.parse_args()

    img, info = read_mrc(args.mrc)
    h, w = img.shape

    t = np.load(args.passthrough, allow_pickle=False)
    paths = np.array([x.decode() for x in t["location/micrograph_path"]])
    key = re.compile(re.escape(args.movie))
    sel = np.array([bool(key.search(p)) for p in paths])
    fx = t["location/center_x_frac"][sel].astype(np.float64)
    fy = t["location/center_y_frac"][sel].astype(np.float64)

    rng = np.random.default_rng(args.seed)
    # 20x as many controls as particles, so the null is well sampled.
    n_ctrl = max(200, 20 * len(fx))
    cx = rng.uniform(0, 1, n_ctrl) * w
    cy = rng.uniform(0, 1, n_ctrl) * h
    neg = contrast(img, cx, cy)

    result = {
        "mrc": args.mrc,
        "movie": args.movie,
        "header": info,
        "geometry_expected": {"nx": 8192, "ny": 8192, "pixel_size_A": 0.485},
        "geometry_ok": bool(info["nx"] == 8192 and info["ny"] == 8192 and
                            info["pixel_size_A_x"] is not None and
                            abs(info["pixel_size_A_x"] - 0.485) < 1e-3),
        "image_stats": {"mean": float(img.mean()), "std": float(img.std()),
                        "min": float(img.min()), "max": float(img.max()),
                        "n_nonfinite": int((~np.isfinite(img)).sum())},
        "n_deposited_particles": int(sel.sum()),
        "n_control_positions": int(len(neg)),
        "y_conventions": {},
    }

    for name, ys in (("y_as_is", fy * h), ("y_flipped", (1.0 - fy) * h)):
        pos = contrast(img, fx * w, ys)
        result["y_conventions"][name] = {
            "n_scored": int(len(pos)),
            "mean_abs_contrast": float(np.abs(pos).mean()) if len(pos) else None,
            "auc_vs_random": auc(pos, neg),
        }
    result["control_mean_abs_contrast"] = float(np.abs(neg).mean()) if len(neg) else None

    best = max(result["y_conventions"],
               key=lambda k: (result["y_conventions"][k]["auc_vs_random"] or 0.0))
    result["preferred_y_convention"] = best
    result["best_auc"] = result["y_conventions"][best]["auc_vs_random"]
    result["interpretation"] = (
        "AUC near 0.5 means deposited coordinates are indistinguishable from random "
        "positions: either the gain orientation is wrong, the coordinate frame does not "
        "match, or the render is bad. AUC well above 0.5 means the pipeline reproduces "
        "the depositors' micrograph frame. This is a plumbing check on development data "
        "and is not evidence of signal equivalence between backends.")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
