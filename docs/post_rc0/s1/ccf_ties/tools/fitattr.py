#!/usr/bin/env python3
"""Fit-level attribution: which patches' trajectory differences move the local model.

  fitattr.py <cpu_run_dir> <cuda_run_dir> <out.json>

Refits the 18-term local-motion model (design of motioncorr_runner.cpp, as in
docs/rc0/diag_s1/tools/diag_analyze.py) from each backend's STAR local_shift
observations, then refits CUDA's observations with one patch at a time taken
from CPU instead. Reports the model-field difference against CPU's fit
(33x33 grid, all frames). Counterfactual on the fit only; no images are made.
"""
import glob, json, re, sys
from pathlib import Path

import numpy as np


def star_loop(text, block):
    m = re.search(r"data_%s\s*\n(.*?)(?=\n# version|\ndata_|\Z)" % block, text, re.S)
    if not m:
        return np.zeros((0, 0))
    cols, rows = [], []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("_rln"):
            cols.append(s.split()[0])
        elif s and not s.startswith("loop_") and cols:
            rows.append([float(x) for x in s.split()])
    return np.array(rows)


def parse(run):
    star = glob.glob(str(Path(run) / "Movies" / "*.star"))[0]
    t = open(star).read()
    c = star_loop(t, "local_motion_model")
    local = {}
    for f, x, y, sx, sy in star_loop(t, "local_shift"):
        local.setdefault((int(x), int(y)), []).append((f, sx, sy))
    m = re.search(r"_rlnImageSizeX\s+(\d+).*?_rlnImageSizeY\s+(\d+).*?_rlnMicrographMovieName", t, re.S)
    nx, ny = int(m.group(1)), int(m.group(2))
    return {k: np.array(v) for k, v in local.items()}, c[:, 1], nx, ny


def design(xc, yc, z, nx, ny):
    x = xc / nx - 0.5
    y = yc / ny - 0.5
    z2, z3 = z * z, z * z * z
    cols = []
    for s in (np.ones_like(x), x, x * x, y, y * y, x * y):
        cols += [s * z, s * z2, s * z3]
    return np.stack(cols, axis=1)


def refit(local, nx, ny):
    xs, ys, zs, vx, vy = [], [], [], [], []
    for k, a in sorted(local.items()):
        n = len(a)
        xs += [k[0]] * n; ys += [k[1]] * n
        zs += list(a[:, 0] - 1 + 0.5)
        vx += list(a[:, 1]); vy += list(a[:, 2])
    A = design(np.array(xs, float), np.array(ys, float), np.array(zs, float), nx, ny)
    return np.concatenate([np.linalg.lstsq(A, np.array(vx), rcond=None)[0],
                           np.linalg.lstsq(A, np.array(vy), rcond=None)[0]])


def field(coeffs, nx, ny, nframes, grid=33):
    g = np.linspace(0, 1, grid)
    X, Y = np.meshgrid(g, g)
    out = np.zeros((nframes, grid, grid, 2))
    for z in range(nframes):
        A = design(X.ravel() * nx, Y.ravel() * ny, np.full(X.size, float(z)), nx, ny)
        out[z, :, :, 0] = (A @ coeffs[:18]).reshape(grid, grid)
        out[z, :, :, 1] = (A @ coeffs[18:]).reshape(grid, grid)
    return out


def diff(fa, fb):
    m = np.sqrt(((fa - fb) ** 2).sum(-1))
    return {"max": round(float(m.max()), 3), "rms": round(float(np.sqrt((m ** 2).mean())), 3)}


def main(cpu, cuda, out):
    Lc, Cc, nx, ny = parse(cpu)
    Lg, Cg, _, _ = parse(cuda)
    nz = int(max(a[:, 0].max() for a in Lc.values()))
    fc, fg = field(refit(Lc, nx, ny), nx, ny, nz), field(refit(Lg, nx, ny), nx, ny, nz)
    res = {"cpu_patches": len(Lc), "cuda_patches": len(Lg),
           "refit_reproduces_star": {"cpu": diff(fc, field(Cc, nx, ny, nz)), "cuda": diff(fg, field(Cg, nx, ny, nz))},
           "cpu_vs_cuda": diff(fc, fg), "obs_diff_max_px": {}, "cuda_with_one_patch_from_cpu": {}}
    common = sorted(set(Lc) & set(Lg))
    for k in common:
        res["obs_diff_max_px"][str(k)] = round(float(np.hypot(*(Lc[k][:, 1:] - Lg[k][:, 1:]).T).max()), 3)
        h = dict(Lg); h[k] = Lc[k]
        res["cuda_with_one_patch_from_cpu"][str(k)] = diff(fc, field(refit(h, nx, ny), nx, ny, nz))
    big = [k for k in common if res["obs_diff_max_px"][str(k)] > 0.25]
    h = dict(Lg); h.update({k: Lc[k] for k in big})
    res["cuda_with_all_patches_over_0.25px_from_cpu"] = {"patches": [str(k) for k in big],
                                                        "field": diff(fc, field(refit(h, nx, ny), nx, ny, nz))}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("cpu_patches", "cuda_patches", "refit_reproduces_star", "cpu_vs_cuda",
                                          "cuda_with_all_patches_over_0.25px_from_cpu")}))
    for k in common:
        print(k, "obs diff max", res["obs_diff_max_px"][str(k)], "-> field diff after swap", res["cuda_with_one_patch_from_cpu"][str(k)])


if __name__ == "__main__":
    main(*sys.argv[1:4])
