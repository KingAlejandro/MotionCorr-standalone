#!/usr/bin/env python3
"""Which --gain_rot/--gain_flip matches a movie? Correlate pixel-level structure.

For each candidate run directory, MotionCorr writes the gain it applied (rotated
and flipped) to out/gain.mrc. A raw frame sum carries the detector's per-pixel
sensitivity s; the gain is about 1/s. So high-pass(raw sum) correlates with
high-pass(1/gain) only when the gain is oriented like the movie. Usage:
  gain_orientation.py MOVIE.mrc RUN_DIR [RUN_DIR ...]
"""
import struct, sys
import numpy as np

def mrc(path, frames=None):
    d = np.memmap(path, dtype=np.uint8, mode="r")
    nx, ny, nz, mode = struct.unpack("<4i", bytes(d[:16]))
    ns = struct.unpack("<i", bytes(d[92:96]))[0]
    dt = {0: "i1", 1: "<i2", 2: "<f4", 6: "<u2"}[mode]
    a = np.frombuffer(d[1024 + ns:], dtype=dt, count=nx * ny * nz).reshape(nz, ny, nx)
    return a

def highpass(x, k=15):
    c = np.cumsum(np.cumsum(np.pad(x, ((k, k), (k, k)), mode="reflect"), 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    ny, nx = x.shape
    w = 2 * k + 1
    s = c[w:w + ny, w:w + nx] - c[:ny, w:w + nx] - c[w:w + ny, :nx] + c[:ny, :nx]
    return x - s / (w * w)

movie = mrc(sys.argv[1])
raw = movie.astype(np.float64).sum(axis=0)
hr = highpass(raw)
print("raw sum: %d frames, %dx%d, mean %.2f counts/px" % (movie.shape[0], raw.shape[1], raw.shape[0], raw.mean()))
for run in sys.argv[2:]:
    g = mrc(run + "/out/gain.mrc")[0].astype(np.float64)
    if g.shape != raw.shape:
        print(run, "shape", g.shape); continue
    inv = np.where(g > 0, 1.0 / np.where(g > 0, g, 1), 0)
    hg = highpass(inv)
    m = (g > 0)
    r = np.corrcoef(hr[m], hg[m])[0, 1]
    corrected = raw * g
    fano = highpass(corrected)[m].var() / corrected[m].mean()
    print("%-28s corr(hp raw, hp 1/gain) = %+.4f   Fano(hp corrected) = %.3f" % (run.rsplit("/", 1)[-1], r, fano))
