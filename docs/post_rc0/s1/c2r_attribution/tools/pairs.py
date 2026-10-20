#!/usr/bin/env python3
"""S1.3b: decompose the iteration-1 patch-input difference between two runs.

  pairs.py <fam> <out.json>        (run from the scratch root, after campaign_b.sh)

Runs (all 5x5, diag2 build): <fam>-p5-d2-{cpu,cuda}-own, -cpu-injcuda, -cuda-injcpu.
The global trajectory each run applied is read from shifts/<fam>-<be>.txt.
Pairs (A -> B, dT = trajectory(B) - trajectory(A)):
  P0 cpu-own   -> cuda-own     measured CPU-vs-CUDA difference
  P1 cpu-own   -> cpu-injcuda  CPU arithmetic, CUDA's trajectory: shift/crop geometry only
  P2 cpu-injcuda -> cuda-own   same trajectory, different backend: arithmetic + preprocessing
  P3 cuda-own  -> cuda-injcpu  geometry in CUDA arithmetic
  P4 cpu-own   -> cuda-injcpu  same trajectory, the other way round
Per patch and frame 2..n, over the CCF window: relative difference; a weighted
phase fit of a translation (residual against -dT); the amplitude metric
median(| |B|/|A| - 1 |) over |k| < 40 (the S1.3 phasefit metric); and the
residual after removing the fitted translation, ||B - A e^{i phi}|| / ||A||.
"""
import json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze as A


def traj(fam, be):
    a = np.loadtxt(f"shifts/{fam}-{be}.txt")
    return a[:, 1:3]


def inputs(label, tag, iy, ix):
    I = A.load_index(f"maps/{label}")
    return A.read(I[(tag, iy, ix, A.calls(I, {tag}, iy, ix)[0], 1, "in")], True).astype(np.complex128)


def pair(fam, la, ta, lb, tb, dT, sizes):
    rows = []
    for iy in range(1, 6):
        for ix in range(1, 6):
            Fa, Fb = inputs(la, ta, iy, ix), inputs(lb, tb, iy, ix)
            pnx, pny = sizes[(iy, ix)]
            ny, nfx = Fa.shape[1:]
            KX, KY = np.meshgrid(np.arange(nfx), A.signed_rows(ny))
            m = (KX ** 2 + KY ** 2 < 40 ** 2) & ((KX > 0) | (KY > 0))
            D = np.stack([2 * np.pi * KX[m] / pnx, 2 * np.pi * KY[m] / pny], 1)
            for f in range(Fa.shape[0]):
                a, b = Fa[f], Fb[f]
                r = {"patch": [iy, ix], "frame": f + 1,
                     "rel": float(np.linalg.norm(b - a) / np.linalg.norm(a))}
                if f > 0:
                    W = np.abs(a)[m]
                    sol = np.linalg.lstsq(D * W[:, None], np.angle(b * np.conj(a))[m] * W, rcond=None)[0]
                    ph = 2 * np.pi * (KX * sol[0] / pnx + KY * sol[1] / pny)
                    r["fit_resid_px"] = float(np.hypot(*(sol + dT[f])))
                    r["amp"] = float(np.median(np.abs(np.abs(b) / np.abs(a) - 1)[m]))
                    r["post_translation_rel"] = float(np.linalg.norm(b - a * np.exp(1j * ph)) / np.linalg.norm(a))
                rows.append(r)
    return rows


def agg(rows, k):
    v = np.array([r[k] for r in rows if k in r and r["frame"] > 1])
    return {"median": float(np.median(v)), "p95": float(np.percentile(v, 95)), "max": float(v.max())}


def main(fam, out):
    Tc, Tg = traj(fam, "cpu"), traj(fam, "cuda")
    sizes = A.patch_sizes(f"runs/{fam}-p5-d2-cpu-own")
    L = lambda be, mode: f"{fam}-p5-d2-{be}-{mode}"
    spec = {"P0": (L("cpu", "own"), "cpu", L("cuda", "own"), "cuda-batched", Tg - Tc),
            "P1": (L("cpu", "own"), "cpu", L("cpu", "injcuda"), "cpu", Tg - Tc),
            "P2": (L("cpu", "injcuda"), "cpu", L("cuda", "own"), "cuda-batched", 0 * Tc),
            "P3": (L("cuda", "own"), "cuda-batched", L("cuda", "injcpu"), "cuda-batched", Tc - Tg),
            "P4": (L("cpu", "own"), "cpu", L("cuda", "injcpu"), "cuda-batched", 0 * Tc)}
    res, per = {"fam": fam, "global_traj_diff_px": {"median": float(np.median(np.hypot(*(Tg - Tc).T)[1:])),
                                                    "max": float(np.hypot(*(Tg - Tc).T).max())}}, {}
    for name, (la, ta, lb, tb, dT) in spec.items():
        rows = pair(fam, la, ta, lb, tb, dT, sizes)
        per[name] = rows
        res[name] = {"a": la, "b": lb, "n_patch_frames": sum(1 for r in rows if r["frame"] > 1),
                     "frame1_rel_max": max(r["rel"] for r in rows if r["frame"] == 1)}
        for k in ("rel", "fit_resid_px", "amp", "post_translation_rel"):
            res[name][k] = agg(rows, k)
    # Frame-by-frame agreement of the geometry-only residual with the measured one.
    for k in ("amp", "post_translation_rel"):
        a = np.array([r[k] for r in per["P0"] if k in r]); b = np.array([r[k] for r in per["P1"] if k in r])
        res["P1_vs_P0_" + k] = {"corr": float(np.corrcoef(a, b)[0, 1]), "median_ratio": float(np.median(b / a))}
    json.dump(res, open(out, "w"), indent=1)
    for name in spec:
        x = res[name]
        print(fam, name, "rel %.2e" % x["rel"]["median"], "fit %.4f px" % x["fit_resid_px"]["median"],
              "amp %.2e" % x["amp"]["median"], "post-trans %.2e (p95 %.2e)" % (x["post_translation_rel"]["median"], x["post_translation_rel"]["p95"]),
              "fr1 %.1e" % x["frame1_rel_max"])
    print(fam, "P1 vs P0", res["P1_vs_P0_amp"], res["P1_vs_P0_post_translation_rel"])


if __name__ == "__main__":
    main(*sys.argv[1:3])
