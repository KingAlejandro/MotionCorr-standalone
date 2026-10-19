#!/usr/bin/env python3
"""Fit the CPU-vs-CUDA patch-input difference at iteration 1 as a translation.

  phasefit.py <case> <out.json>      (run from the scratch root)

For every patch and frame 2..n, fits the phase of Fcuda * conj(Fcpu) over the
CCF window (|k| < 40, weighted by |Fcpu|) to a translation (dx, dy) in patch
pixels and compares it with the difference of the two backends' global
trajectories for that frame (CUDA - CPU). Also reports the amplitude ratio.
"""
import json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze as A


def main(case, out):
    Ic, Ig = A.load_index(f"maps/{case}-diag-cpu-on"), A.load_index(f"maps/{case}-diag-cuda-on")
    T = json.load(open(f"analysis/{case}-traj.json"))
    sizes = A.patch_sizes(f"runs/{case}-diag-cpu-on")
    G = T["patches"]["global"]
    dT = np.array(G["T_final_cuda"]) - np.array(G["T_final_cpu"])
    err, amp, mag = [], [], []
    for key, p in T["patches"].items():
        if key == "global":
            continue
        iy, ix = map(int, key.split(","))
        gt = p["cuda_tag"]
        Fc = A.read(Ic[("cpu", iy, ix, A.calls(Ic, {"cpu"}, iy, ix)[0], 1, "in")], True).astype(np.complex128)
        Fg = A.read(Ig[(gt, iy, ix, A.calls(Ig, {gt}, iy, ix)[0], 1, "in")], True).astype(np.complex128)
        pnx, pny = sizes[(iy, ix)]
        ny, nfx = Fc.shape[1:]
        KX, KY = np.meshgrid(np.arange(nfx), A.signed_rows(ny))
        m = (KX ** 2 + KY ** 2 < 40 ** 2) & ((KX > 0) | (KY > 0))
        D = np.stack([2 * np.pi * KX[m] / pnx, 2 * np.pi * KY[m] / pny], 1)
        for f in range(1, Fc.shape[0]):
            W = np.abs(Fc[f])[m]
            ang = np.angle(Fg[f] * np.conj(Fc[f]))[m]
            sol = np.linalg.lstsq(D * W[:, None], ang * W, rcond=None)[0]
            # The kernels multiply by exp(+i 2pi k.s) with s = -shift/n, so a
            # trajectory difference dT appears as a phase slope of -dT.
            err.append(float(np.hypot(*(sol + dT[f]))))
            mag.append(float(np.hypot(*dT[f])))
            amp.append(float(np.median(np.abs(np.abs(Fg[f]) / np.abs(Fc[f]) - 1)[m])))
    res = {"n_patch_frames": len(err),
           "fit_minus_minus_dT_px": {"median": float(np.median(err)), "p95": float(np.percentile(err, 95)), "max": float(max(err))},
           "global_traj_diff_px": {"median": float(np.median(mag)), "max": float(max(mag))},
           "amplitude_ratio_minus_1_median": {"median": float(np.median(amp)), "max": float(max(amp))}}
    json.dump(res, open(out, "w"), indent=1)
    print(case, json.dumps(res))


if __name__ == "__main__":
    main(*sys.argv[1:3])
