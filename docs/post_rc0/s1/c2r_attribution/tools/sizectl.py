#!/usr/bin/env python3
"""S1.3c size control: real frames after the global inverse FFT on 10641-01
(5760x4092), CUDA with and without the edge-column projection, frames 2/11/21;
and, for each, against a float64 irfft2 of the dumped spectrum.  sizectl.py <out.json>"""
import glob, json, sys
import numpy as np
res = {}
for f in (2, 11, 21):
    r = {}
    for arm in ("off", "glob"):
        d = f"full/f-e10641-01-p5-{arm}"
        sp = glob.glob(f"{d}/spec_fr{f}_*.bin")[0]; rl = glob.glob(f"{d}/real_fr{f}_*.bin")[0]
        ny, nfx = map(int, sp.split("_")[-1][:-4].split("x")); nx = int(rl.split("_")[-1][:-4].split("x")[1])
        S = np.fromfile(sp, dtype=np.complex64).reshape(ny, nfx).astype(np.complex128)
        R = np.fromfile(rl, dtype=np.float32).reshape(ny, nx).astype(np.float64)
        ref = np.fft.irfft2(S, s=(ny, nx)) * (nx * ny)
        r[arm + "_vs_f64_irfft_rel"] = float(np.linalg.norm(R - ref) / np.linalg.norm(ref))
        D = R - ref; row = D.mean(axis=1)
        r[arm + "_row_mean_rms_over_frame_rms"] = float(np.sqrt((row ** 2).mean()) / np.sqrt((ref ** 2).mean()))
        r[arm] = R
    r["glob_vs_off_rel"] = float(np.linalg.norm(r["glob"] - r["off"]) / np.linalg.norm(r["off"]))
    del r["glob"], r["off"]
    res[f] = r; print(f, r)
json.dump(res, open(sys.argv[1], "w"), indent=1)
