#!/usr/bin/env python3
"""S1.3b: does the cuFFT Nyquist-column row term explain the equal-trajectory
patch-input difference (pairs.py P2) completely?

  hpredict.py <fam> <out.json>     (scratch root; after campaign_b.sh and campaign_c.sh)

For frames 2, 11, 21: h(y) = -Im(ifft_y(S[:, nx/2])) from CUDA's full-frame
spectrum after the global shifts (fullframe.py shows CUDA real - irfft2 = h(y)
per row). Cropping h to each patch and taking CPU's normalised forward FFT gives
a predicted kx = 0 column, which is compared with the measured CUDA - CPU
iteration-1 patch-input difference (cuda-own vs cpu-injcuda) over the CCF window.
"""
import json, re, glob, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze as A
import pairs as P
import fullframe as FF


def bounds(run):
    log = open(glob.glob(f"runs/{run}/Movies/*.log")[0]).read()
    out = {}
    for m in re.finditer(r"Patch \((\d+), (\d+)\): .*?X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\)", log):
        iy, ix, x0, x1, y0, y1 = map(int, m.groups())
        out[(iy, ix)] = (x0, x1, y0, y1)
    return out


def main(fam, out):
    B = bounds(f"{fam}-p5-d2-cpu-own")
    res = {"frames": {}}
    allr = []
    for f in (2, 11, 21):
        S = FF.load(fam, "cuda-own", "spec", f)
        ny = S.shape[0]
        h = -(np.fft.ifft(S[:, -1]) * ny).imag
        rows = []
        for (iy, ix), (x0, x1, y0, y1) in sorted(B.items()):
            a = P.inputs(f"{fam}-p5-d2-cpu-injcuda", "cpu", iy, ix)[f - 1]
            b = P.inputs(f"{fam}-p5-d2-cuda-own", "cuda-batched", iy, ix)[f - 1]
            ph = y1 - y0
            wy, nfx = a.shape
            col = np.fft.fft(h[y0:y1]) / ph  # (1/(w h)) * sum_x sum_y h = (1/h) sum_y h e^{-...}
            ky = A.signed_rows(wy).astype(int)
            pred = np.zeros_like(a)
            pred[:, 0] = col[ky % ph]
            meas = b - a
            rows.append({"patch": [iy, ix],
                         "meas_rel": float(np.linalg.norm(meas) / np.linalg.norm(a)),
                         "unexplained_rel": float(np.linalg.norm(meas - pred) / np.linalg.norm(a)),
                         "explained_fraction_of_energy": float(1 - np.linalg.norm(meas - pred) ** 2 / np.linalg.norm(meas) ** 2)})
        res["frames"][f] = rows
        allr += rows
        print(fam, f, "meas rel median %.2e" % np.median([r["meas_rel"] for r in rows]),
              "unexplained median %.2e max %.2e" % (np.median([r["unexplained_rel"] for r in rows]), max(r["unexplained_rel"] for r in rows)),
              "explained energy min %.6f" % min(r["explained_fraction_of_energy"] for r in rows))
    res["summary"] = {"meas_rel_median": float(np.median([r["meas_rel"] for r in allr])),
                      "unexplained_rel_median": float(np.median([r["unexplained_rel"] for r in allr])),
                      "unexplained_rel_max": float(max(r["unexplained_rel"] for r in allr)),
                      "explained_energy_min": float(min(r["explained_fraction_of_energy"] for r in allr))}
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
