#!/usr/bin/env python3
"""Compare the per-patch final group shifts logged by the W-DIAG-S1 diagnostic build
(MC_DIAG_DUMP=1) for two runs, including patches that did not converge.

Shifts are the alignPatch output (group shifts relative to the patch's first group, before
recentring). For each patch: convergence on each side, RMS/max difference, the frames that
carry differences > 1 px, and the distance of each side's trajectory from the median of its
converged 4-neighbours (a pathology indicator, not a truth measure)."""
import argparse, json, re
from pathlib import Path
import numpy as np

RE = re.compile(r"^DIAG patch (\d+) (\d+) center (\d+) (\d+) converged=(\d) shifts (.*)$")


def load(run):
    log = next((Path(run) / "Movies").glob("*.log"))
    d = {}
    for line in open(log):
        m = RE.match(line.rstrip("\n"))
        if m:
            sh = np.array([[float(v) for v in t.split(",")] for t in m.group(6).split()])
            d[(int(m.group(1)), int(m.group(2)))] = {"center": (int(m.group(3)), int(m.group(4))),
                                                     "converged": m.group(5) == "1", "shifts": sh}
    return d


def neighbour_dev(d, k):
    iy, ix = k
    nb = [d[(iy + a, ix + b)]["shifts"] for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1))
          if (iy + a, ix + b) in d and d[(iy + a, ix + b)]["converged"]]
    if not nb:
        return None
    med = np.median(np.stack(nb), axis=0)
    return float(np.max(np.hypot(*(d[k]["shifts"] - med).T)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--json-out", required=True)
    a = ap.parse_args()
    R, T = load(a.ref), load(a.test)
    rows = []
    for k in sorted(R):
        r, t = R[k], T[k]
        dd = np.hypot(*(r["shifts"] - t["shifts"]).T)
        rows.append({"patch": k, "center": r["center"], "ref_converged": r["converged"], "test_converged": t["converged"],
                     "rms_diff_px": round(float(np.sqrt(np.mean(dd ** 2))), 4), "max_diff_px": round(float(dd.max()), 4),
                     "frames_diff_gt_1px": [int(i) + 1 for i in np.where(dd > 1)[0]],
                     "ref_max_dev_from_neighbours_px": neighbour_dev(R, k),
                     "test_max_dev_from_neighbours_px": neighbour_dev(T, k)})
    json.dump({"ref": a.ref, "test": a.test, "patches": rows}, open(a.json_out, "w"), indent=1)
    print("== %s vs %s" % (a.ref, a.test))
    for x in rows:
        flag = "FLIP" if x["ref_converged"] != x["test_converged"] else ""
        if flag or x["max_diff_px"] > 1 or not x["ref_converged"]:
            nd = lambda v: "-" if v is None else "%.1f" % v
            print(" %s conv %d/%d rms %.3f max %.3f frames>1px %s devnb %s/%s %s" % (
                x["patch"], x["ref_converged"], x["test_converged"], x["rms_diff_px"], x["max_diff_px"],
                x["frames_diff_gt_1px"][:12] + (["..."] if len(x["frames_diff_gt_1px"]) > 12 else []),
                nd(x["ref_max_dev_from_neighbours_px"]), nd(x["test_max_dev_from_neighbours_px"]), flag))


if __name__ == "__main__":
    main()
