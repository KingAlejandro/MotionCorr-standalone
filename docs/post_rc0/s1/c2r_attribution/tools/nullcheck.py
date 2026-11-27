#!/usr/bin/env python3
"""S1.3c-null size check on 10216-00 5x5 (frames 2/11/21): the null arm's change to
the real frames after the global inverse FFT must be a pure per-row constant of rms
sigma equal to the rms of the cuFFT row term h(y), which the off arm carries
(off minus float64 irfft2 of the dumped spectrum).  nullcheck.py <out.json>"""
import glob, json, sys
import numpy as np
res = {}
for f in (2, 11, 21):
    ld = lambda arm, k: glob.glob(f"full/nv-e10216-00-p5-{arm}/{k}_fr{f}_*.bin")[0]
    S = np.fromfile(ld("off", "spec"), dtype=np.complex64).reshape(4096, 2049).astype(np.complex128)
    Roff = np.fromfile(ld("off", "real"), dtype=np.float32).reshape(4096, 4096).astype(np.float64)
    Rnull = np.fromfile(ld("null1", "real"), dtype=np.float32).reshape(4096, 4096).astype(np.float64)
    h = (Roff - np.fft.irfft2(S, s=(4096, 4096)) * 4096 * 4096).mean(axis=1)
    D = Rnull - Roff; row = D.mean(axis=1)
    r = {"h_rms": float(np.sqrt((h ** 2).mean())), "null_row_rms": float(np.sqrt((row ** 2).mean())),
         "null_within_row_rms": float(np.sqrt(((D - row[:, None]) ** 2).mean())),
         "null_row_abs_constant": bool(np.allclose(np.abs(row), np.abs(row).mean(), rtol=1e-3)),
         "corr_null_rows_with_h": float(np.corrcoef(row, h)[0, 1])}
    res[f] = r; print(f, r)
json.dump(res, open(sys.argv[1], "w"), indent=1)
