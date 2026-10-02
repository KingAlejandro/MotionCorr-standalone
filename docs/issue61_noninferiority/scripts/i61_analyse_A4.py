#!/usr/bin/env python3
"""Issue 61 endpoint A4 (descriptive): rotationally averaged power spectrum ratio.

CTFFIND-independent check on where in resolution the arms differ from CPU.
Reported, never tested against a margin.
"""
import json, os, struct, sys
import numpy as np

ROOT = "/home/alex/mc-issue61"
RESULTS = "/home/alex/MotionCorr-issue36-full24/results"
REAL = ["cpu", "default", "allfftw"]
CTRL = ["ctrl_noise_f005", "ctrl_noise_f020", "ctrl_envelope_b20"]
ALL = REAL + CTRL
DEV = ["00021", "00046"]
ANGPIX = 0.885
BANDS = [(50.0, 20.0), (20.0, 10.0), (10.0, 6.0), (6.0, 4.0), (4.0, 3.0), (3.0, 2.0)]


def read(path):
    with open(path, "rb") as fh:
        head = fh.read(1024)
        nx, ny, nz, mode = struct.unpack("<4i", head[0:16])
        return np.frombuffer(fh.read(), dtype="<f4").reshape(ny, nx).astype(np.float32)


def src(arm, mid):
    if arm in REAL:
        return f"{RESULTS}/{arm}/{mid}/output/Movies/20170629_{mid}_frameImage.mrc"
    return f"{ROOT}/arms/{arm}/20170629_{mid}_frameImage.mrc"


movies = sorted(os.listdir(f"{RESULTS}/default"))
cache = {}
radial = {}
for arm in ALL:
    radial[arm] = {}
    for mid in movies:
        img = read(src(arm, mid))
        img = img - img.mean()
        ny, nx = img.shape
        F = np.fft.rfft2(img)
        p = (F.real.astype(np.float64) ** 2 + F.imag.astype(np.float64) ** 2)
        if "grid" not in cache:
            fy = np.fft.fftfreq(ny, d=ANGPIX)[:, None]
            fx = np.fft.rfftfreq(nx, d=ANGPIX)[None, :]
            s = np.sqrt(fy * fy + fx * fx)
            nb = 400
            smax = float(fx.max())
            idx = np.clip((s / smax * nb).astype(np.int32), 0, nb - 1)
            cnt = np.bincount(idx.ravel(), minlength=nb)
            centres = (np.arange(nb) + 0.5) / nb * smax
            cache["grid"] = (idx, cnt, centres, smax, nb)
        idx, cnt, centres, smax, nb = cache["grid"]
        prof = np.bincount(idx.ravel(), weights=p.ravel(), minlength=nb) / np.maximum(cnt, 1)
        radial[arm][mid] = prof
        del img, F, p
    print("profiled", arm, flush=True)

idx, cnt, centres, smax, nb = cache["grid"]
d = np.where(centres > 0, 1.0 / np.maximum(centres, 1e-9), np.inf)
out = {"angpix": ANGPIX, "n_bins": nb, "bands_A": BANDS, "movies": movies,
       "development_movies": DEV, "band_power_ratio_vs_cpu": {}}
for arm in ALL:
    if arm == "cpu":
        continue
    out["band_power_ratio_vs_cpu"][arm] = {}
    for lo, hi in BANDS:
        m = (d <= lo) & (d >= hi) & np.isfinite(d)
        per = {}
        for mid in movies:
            a = radial[arm][mid][m].sum()
            c = radial["cpu"][mid][m].sum()
            per[mid] = float(a / c) if c > 0 else None
        held = [per[x] for x in movies if x not in DEV]
        out["band_power_ratio_vs_cpu"][arm][f"{lo:g}-{hi:g}A"] = {
            "per_movie": per,
            "held22_mean": float(np.mean(held)),
            "held22_min": float(np.min(held)),
            "held22_max": float(np.max(held))}

json.dump(out, open(f"{ROOT}/results/stageA4_power.json", "w"), indent=1, sort_keys=True)
print()
hdr = "".join(f"{lo:g}-{hi:g}A".rjust(14) for lo, hi in BANDS)
print(f"{'arm':18s}{hdr}   (mean power ratio vs CPU, 22 held-out movies)")
for arm in ALL:
    if arm == "cpu":
        continue
    row = "".join(f"{out['band_power_ratio_vs_cpu'][arm][f'{lo:g}-{hi:g}A']['held22_mean']:14.6f}"
                  for lo, hi in BANDS)
    print(f"{arm:18s}{row}")
