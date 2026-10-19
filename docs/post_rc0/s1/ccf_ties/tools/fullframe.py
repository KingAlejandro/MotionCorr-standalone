#!/usr/bin/env python3
"""S1.3b: where does the equal-trajectory CPU/CUDA real-space difference arise?

  fullframe.py <fam> <out.json>     (scratch root; after campaign_c.sh)

Compares, for frames 2, 11, 21 of <fam>-p5-d3-cpu-injcuda-full and
<fam>-p5-d3-cuda-own-full (same global trajectory): the full-frame spectra
after the global shifts, the real frames after each backend's inverse FFT, the
real frames' row means (x-constant part) and column means, and each backend's
real frame against a float64 inverse FFT of its own spectrum.
"""
import json, sys
import numpy as np


def load(fam, be, kind, f):
    lab = f"{fam}-p5-d3-{be}-full"
    if kind == "spec":
        a = np.fromfile(f"full/{lab}/spec_fr{f}_4096x2049.bin", dtype=np.complex64).reshape(4096, 2049)
    else:
        a = np.fromfile(f"full/{lab}/real_fr{f}_4096x4096.bin", dtype=np.float32).reshape(4096, 4096)
    return a.astype(np.complex128 if kind == "spec" else np.float64)


def rel(a, b):
    return float(np.linalg.norm(a - b) / np.linalg.norm(b))


def main(fam, out):
    res = {}
    for f in (2, 11, 21):
        Sc, Sg = load(fam, "cpu-injcuda", "spec", f), load(fam, "cuda-own", "spec", f)
        Rc, Rg = load(fam, "cpu-injcuda", "real", f), load(fam, "cuda-own", "real", f)
        ny, nx = Rc.shape
        r = {"spec_rel": rel(Sg, Sc),
             "spec_rel_col0": rel(Sg[:, 0], Sc[:, 0]), "spec_rel_colnyq": rel(Sg[:, -1], Sc[:, -1]),
             "real_rel": rel(Rg, Rc)}
        D = Rg - Rc
        row = D.mean(axis=1, keepdims=True); col = D.mean(axis=0, keepdims=True)
        r["real_diff_rms"] = float(np.sqrt((D ** 2).mean()))
        r["row_mean_part_rms"] = float(np.sqrt((row ** 2).mean()))
        r["col_mean_part_rms"] = float(np.sqrt((col ** 2).mean()))
        r["after_removing_row_means_rms"] = float(np.sqrt(((D - row) ** 2).mean()))
        r["frame_rms"] = float(np.sqrt((Rc ** 2).mean()))
        # Row-mean difference: alternating (-1)^y part vs the rest.
        g = row[:, 0]; alt = (-1.0) ** np.arange(ny)
        ca = float((g * alt).mean())
        r["row_mean_alternating_coeff"] = ca
        r["row_mean_non_alternating_rms"] = float(np.sqrt(((g - ca * alt) ** 2).mean()))
        # Each backend's inverse against float64 of its own spectrum. The forward
        # FFT is normalised by 1/(nx*ny) in both backends, so the inverse is unnormalised.
        for name, S, R in (("cpu", Sc, Rc), ("cuda", Sg, Rg)):
            ref = np.fft.irfft2(S, s=(ny, nx)) * (nx * ny)
            r[name + "_real_vs_f64_irfft_rel"] = rel(R, ref)
        # Non-Hermitian parts that a C2R may treat differently: column 0 and the Nyquist column.
        for name, S in (("cpu", Sc), ("cuda", Sg)):
            for cname, c in (("col0", S[:, 0]), ("colnyq", S[:, -1])):
                part = np.conj(c[(-np.arange(ny)) % ny])
                r[f"{name}_{cname}_antiherm_rel"] = float(np.linalg.norm(c - part) / np.linalg.norm(c))
        res[f] = r
        print(fam, f, {k: ("%.3e" % v) for k, v in r.items()})
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
