#!/usr/bin/env python3
"""S1.3 analysis of the per-frame CCF records (MC_DIAG_CCF) and raw dumps (MC_DIAG_MAPS).

  analyze.py traj <cpu_run_dir> <cuda_run_dir> <out.json>
      Per patch: iterations, convergence, reconstructed trajectories, first
      separation, and the per-frame events at the first separating iteration.
  analyze.py maps <cpu_map_dir> <cuda_map_dir> <traj.json> <out.json>
      Per patch and iteration: CPU-vs-CUDA CCF map difference, each backend's
      float32 map against a float64 recomputation from its own dumped inputs,
      the float64 maps of the two backends' inputs against each other, and the
      input-spectrum difference (with a global-shift phase-ramp test at it 1).

Conventions: frame numbers are 1-based as logged. Integer peak positions are in
CCF pixels; shifts ("cur", trajectories) are in patch pixels. alignPatch pins
frame 1's per-iteration increment to +0.0, so accumulated trajectories of the
two backends are directly comparable frame by frame.
"""
import json, math, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

SEP_PX = 0.5  # an event: CPU and CUDA candidate shifts for one frame differ by more than this (px)


def ordered(x):
    """float32 -> integer with the same ordering, so differences count ulps."""
    i = np.asarray(x, dtype=np.float32).view(np.int32).astype(np.int64)
    return np.where(i < 0, -(i & 0x7FFFFFFF), i)


def ulps(a, b):
    return int(ordered(np.float32(a)) - ordered(np.float32(b)))


def parse_ccf(path):
    """{tag: {(iy, ix): {iter: {frame: rec}}}}"""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for line in open(path):
        t = line.split()
        r = {"sel": (int(t[8]), int(t[9])), "max": float(t[11]), "cpu": (int(t[13]), int(t[14])),
             "lane": (int(t[16]), int(t[17])), "ties": int(t[19]), "p2": float(t[21]),
             "p2pos": (int(t[22]), int(t[23])), "nlm": int(t[25]),
             "sub": [float(v) for v in t[27:32]], "cur": (float(t[33]), float(t[34])), "note": t[35]}
        out[t[0]][(int(t[1]), int(t[2]))][int(t[4])][int(t[6])] = r
    return out


def trajectory(iters, is_cuda):
    """Accumulate per-iteration increments exactly as the backend does."""
    n = len(iters[1])
    T = np.zeros((n, 2))
    per_iter, rmsd = {}, {}
    for k in sorted(iters):
        cur = np.array([iters[k][f + 1]["cur"] for f in range(n)])
        if is_cuda:
            c = cur.astype(np.float32)
            inc = (c - c[0]).astype(np.float64)  # float subtraction in updatePatchShifts
        else:
            inc = cur - cur[0]
        T = T + inc
        per_iter[k] = T.copy()
        rmsd[k] = math.sqrt((inc ** 2).sum() / n)
    return per_iter, rmsd


def first_attempt(recs):
    for tag in ("cuda-batched", "cuda-single"):
        if tag in recs:
            return tag
    return None


def event_detail(rc, rg):
    """One frame where the two candidate shifts differ."""
    d = {"cpu_sel": rc["sel"], "cuda_sel": rg["sel"], "same_peak": rc["sel"] == rg["sel"],
         "cpu_max": rc["max"], "cuda_max": rg["max"],
         "cpu_p2": rc["p2"], "cpu_p2pos": rc["p2pos"], "cuda_p2": rg["p2"], "cuda_p2pos": rg["p2pos"],
         "cpu_ties": rc["ties"], "cuda_ties": rg["ties"],
         "cpu_cur": rc["cur"], "cuda_cur": rg["cur"]}
    # Margin of each backend's maximum over its own second local maximum.
    d["cpu_margin_ulps"] = ulps(rc["max"], rc["p2"])
    d["cuda_margin_ulps"] = ulps(rg["max"], rg["p2"])
    d["cpu_margin_rel"] = (rc["max"] - rc["p2"]) / abs(rc["max"])
    d["cuda_margin_rel"] = (rg["max"] - rg["p2"]) / abs(rg["max"])
    # Does each backend's second peak sit where the other backend's maximum is?
    near = lambda a, b: abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1
    d["swap"] = (not d["same_peak"]) and near(rc["p2pos"], rg["sel"]) and near(rg["p2pos"], rc["sel"])
    d["adjacent"] = (not d["same_peak"]) and near(rc["sel"], rg["sel"])
    for be, r in (("cpu", rc), ("cuda", rg)):
        m, vpx, vnx, vpy, vny = r["sub"]
        d[be + "_curv_ulps"] = [round((vpx + vnx - 2 * m) / float(np.spacing(np.float32(m))), 1),
                                round((vpy + vny - 2 * m) / float(np.spacing(np.float32(m))), 1)]
    return d


def cmd_traj(cpu_dir, cuda_dir, out):
    C = parse_ccf(Path(cpu_dir) / "ccf.txt")
    G = parse_ccf(Path(cuda_dir) / "ccf.txt")
    patches = sorted(C["cpu"])
    res = {"cpu_run": str(cpu_dir), "cuda_run": str(cuda_dir), "patches": {}}
    emul_bad = sum(1 for tag in G for p in G[tag] for k in G[tag][p] for f in G[tag][p][k]
                   if G[tag][p][k][f]["note"] != "emul-ok")
    res["cuda_emulation_mismatches"] = emul_bad
    res["cuda_frame_iterations"] = sum(len(G[tag][p][k]) for tag in G for p in G[tag] for k in G[tag][p])
    res["cpu_frame_iterations"] = sum(len(C[tag][p][k]) for tag in C for p in C[tag] for k in C[tag][p])
    # Global alignment, same comparison (patch key (0, 0)).
    for tagc, tagg, key in [("cpu-global", "cuda-global", "global")] + [("cpu", None, p) for p in patches]:
        if key == "global":
            if tagc not in C or tagg not in G:
                continue
            ci, gi = C[tagc][(0, 0)], G[tagg][(0, 0)]
            retry = None
        else:
            ci = C["cpu"][key]
            tagg = first_attempt({t: 1 for t in G if key in G[t]})
            gi = G[tagg][key]
            retry = G["cuda-full"][key] if "cuda-full" in G and key in G["cuda-full"] else None
        Tc, rc = trajectory(ci, False)
        Tg, rg = trajectory(gi, True)
        kc, kg = max(Tc), max(Tg)
        p = {"cuda_tag": tagg, "iters_cpu": kc, "iters_cuda": kg,
             "rmsd_cpu": [round(rc[k], 6) for k in sorted(rc)], "rmsd_cuda": [round(rg[k], 6) for k in sorted(rg)],
             "converged_cpu": rc[kc] < 0.5, "converged_cuda": rg[kg] < 0.5}
        if retry is not None:
            Tr, rr = trajectory(retry, True)
            same = max(Tr) == kg and all(retry[k][f]["cur"] == gi[k][f]["cur"] and retry[k][f]["sel"] == gi[k][f]["sel"]
                                         for k in gi for f in gi[k])
            p["cuda_retry"] = {"iters": max(Tr), "converged": rr[max(Tr)] < 0.5, "identical_to_first_attempt": same}
            if not same:  # the retry is what reaches the fit when it converges
                p["cuda_retry"]["note"] = "retry differs from first attempt"
        dfin = np.hypot(*(Tc[kc] - Tg[kg]).T)
        p["final_traj_diff_max_px"] = float(dfin.max())
        p["final_traj_diff_frames_gt1px"] = [int(i) + 1 for i in np.nonzero(dfin > 1.0)[0]]
        # Per-iteration comparison over common iterations.
        first_sel = None
        first_event_iter = None
        per_iter = []
        for k in range(1, min(kc, kg) + 1):
            n = len(ci[k])
            dc = [math.hypot(ci[k][f]["cur"][0] - gi[k][f]["cur"][0], ci[k][f]["cur"][1] - gi[k][f]["cur"][1])
                  for f in range(1, n + 1)]
            seldiff = [f for f in range(1, n + 1) if ci[k][f]["sel"] != gi[k][f]["sel"]]
            if seldiff and first_sel is None:
                first_sel = {"iter": k, "frames": seldiff}
            ev = [f for f in range(1, n + 1) if dc[f - 1] > SEP_PX]
            dT = np.hypot(*(Tc[k] - Tg[k]).T)
            per_iter.append({"iter": k, "cand_diff_max_px": round(max(dc), 6),
                             "cand_diff_median_px": round(float(np.median(dc)), 6),
                             "sel_diff_frames": seldiff, "event_frames": ev,
                             "traj_diff_max_px": round(float(dT.max()), 6)})
            if ev and first_event_iter is None:
                first_event_iter = k
                p["first_event"] = {"iter": k, "frames": {f: event_detail(ci[k][f], gi[k][f]) for f in ev}}
        p["first_sel_diff"] = first_sel
        if key == "global":
            p["T_final_cpu"] = Tc[kc].tolist()
            p["T_final_cuda"] = Tg[kg].tolist()
        p["per_iter"] = per_iter
        p["acceptance_flip"] = p["converged_cpu"] != p["converged_cuda"]
        p["iteration_count_differs"] = kc != kg
        p["divergent"] = p["acceptance_flip"] or p["final_traj_diff_max_px"] > 1.0
        # Classification of the first separation (iteration-major).
        if "first_event" in p:
            evs = p["first_event"]["frames"].values()
            if all(not e["same_peak"] for e in evs):
                p["first_separation_kind"] = "different integer peak"
            elif all(e["same_peak"] for e in evs):
                p["first_separation_kind"] = "same integer peak, subpixel"
            else:
                p["first_separation_kind"] = "mixed"
        elif kc != kg:
            p["first_separation_kind"] = "no frame event; RMSD either side of 0.5 px"
        else:
            p["first_separation_kind"] = "none (no frame event, same iteration count)"
        res["patches"][key if key == "global" else "%d,%d" % key] = p
    json.dump(res, open(out, "w"), indent=1, default=lambda o: list(o) if isinstance(o, tuple) else str(o))
    for k, p in res["patches"].items():
        if p["divergent"] or k == "global" or p["iteration_count_differs"] or "first_event" in p:
            fe = p.get("first_event", {})
            print(k, p["first_separation_kind"], "conv", p["converged_cpu"], p["converged_cuda"], "iters", p["iters_cpu"], p["iters_cuda"],
                  "finaldiff %.3f" % p["final_traj_diff_max_px"], "first_sel", p["first_sel_diff"],
                  "first_event", fe.get("iter"), list(fe.get("frames", {}).keys()))
    print("emulation mismatches", emul_bad, "of", res["cuda_frame_iterations"])


# ---------------------------------------------------------------- maps
def load_index(d):
    idx = {}
    for line in open(Path(d) / "index.txt"):
        name, tag, iy, ix, call, it, kind, nf, dy, dx = line.split()
        idx[(tag, int(iy), int(ix), int(call), int(it), kind)] = (name, int(nf), int(dy), int(dx))
    return idx


def calls(idx, tagset, iy, ix):
    return sorted({k[3] for k in idx if k[0] in tagset and k[1] == iy and k[2] == ix})


def read(entry, cplx):
    name, nf, dy, dx = entry
    a = np.fromfile(name, dtype=np.complex64 if cplx else np.float32)
    return a.reshape(nf, dy, dx)


def map64(F, w, ny, nx):
    F = F.astype(np.complex128)
    ref = F.sum(axis=0)
    cc = (ref[None] - F) * np.conj(F) * w.astype(np.float64)[None]
    return np.fft.irfft2(cc, s=(ny, nx), axes=(1, 2)) * (ny * nx)  # unnormalised inverse, as FFTW/cuFFT


def window(M, sr):
    """Search window in signed (y, x) order, as the peak search enumerates it."""
    ys = np.r_[np.arange(M.shape[-2] - sr, M.shape[-2]), np.arange(0, sr + 1)]
    xs = np.r_[np.arange(M.shape[-1] - sr, M.shape[-1]), np.arange(0, sr + 1)]
    return M[..., ys[:, None], xs[None, :]]


def rel(a, b):
    """per-frame ||a-b|| / ||b|| over the given arrays"""
    ax = tuple(range(1, a.ndim))
    return np.sqrt((np.abs(a - b) ** 2).sum(axis=ax) / (np.abs(b) ** 2).sum(axis=ax))


def signed_rows(ny):
    """Row frequency as the reference/CCF/shift kernels remap it: y > ny/2 is negative,
    the Nyquist row ny/2 stays positive (numpy's fftfreq would make it negative)."""
    y = np.arange(ny)
    return np.where(y > ny // 2, y - ny, y).astype(np.float64)


def ramp(F, dxy, pny, pnx, sign):
    ny, nfx = F.shape[-2:]
    ky = signed_rows(ny)  # signed CCF-window rows, the remap of the kernels
    kx = np.arange(nfx)
    ph = 2 * np.pi * (kx[None, None, :] * dxy[:, 0, None, None] / pnx + ky[None, :, None] * dxy[:, 1, None, None] / pny)
    return F * np.exp(sign * 1j * ph)


def patch_sizes(run_dir):
    """{(iy, ix): (pnx, pny)} from the movie log's patch ranges; (0, 0) = full frame."""
    import re, glob
    log = open(glob.glob(str(Path(run_dir) / "Movies" / "*.log"))[0]).read()
    out = {}
    for m in re.finditer(r"Patch \((\d+), (\d+)\): .*?X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\)", log):
        iy, ix, x0, x1, y0, y1 = map(int, m.groups())
        out[(iy, ix)] = (x1 - x0, y1 - y0)
    return out


def movie_size(run_dir):
    import re, glob
    log = open(glob.glob(str(Path(run_dir) / "Movies" / "*.log"))[0]).read()
    m = re.search(r"Movie size: X = (\d+) Y = (\d+)", log)
    return int(m.group(1)), int(m.group(2))


def shift_test(idx, tag, iy, ix, call, recs, pnx, pny, is_cuda):
    """Apply the backend's own logged increments of iteration k to its dumped
    iteration-k input in float64 and compare with its dumped iteration-(k+1)
    input. Measures that backend's phase-shift (and storage) error only."""
    out = []
    k = 1
    while (tag, iy, ix, call, k + 1, "in") in idx and k in recs:
        F0 = read(idx[(tag, iy, ix, call, k, "in")], True).astype(np.complex128)
        F1 = read(idx[(tag, iy, ix, call, k + 1, "in")], True).astype(np.complex128)
        n = F0.shape[0]
        cur = np.array([recs[k][f + 1]["cur"] for f in range(n)])
        if is_cuda:
            c = cur.astype(np.float32); inc = (c - c[0]).astype(np.float64)
            sx = (-inc[:, 0].astype(np.float32) / np.float32(pnx)).astype(np.float64)
            sy = (-inc[:, 1].astype(np.float32) / np.float32(pny)).astype(np.float64)
        else:
            inc = cur - cur[0]; sx = -inc[:, 0] / pnx; sy = -inc[:, 1] / pny
        ny, nfx = F0.shape[1:]
        ky = signed_rows(ny); kx = np.arange(nfx)
        ph = 2 * np.pi * (kx[None, None, :] * sx[:, None, None] + ky[None, :, None] * sy[:, None, None])
        pred = F0 * np.exp(1j * ph)
        r = rel(F1[1:], pred[1:])
        pmax = np.abs(ph[1:]).reshape(n - 1, -1).max(1)
        out.append({"iter": k, "resid_rel_median": float(np.median(r)), "resid_rel_max": float(r.max()),
                    "max_phase_rad": float(pmax.max()),
                    "corr_resid_vs_max_phase": float(np.corrcoef(r, pmax)[0, 1]) if n > 2 and np.std(pmax) > 0 else None,
                    "unshifted_frame1_rel": float(rel(F1[:1], F0[:1])[0])})
        k += 1
    return out


def ramp_test(Fc, Fg, dxy, pnx, pny):
    """Input difference before and after phase-shifting the CPU spectra by the
    per-frame global-shift difference dxy (CUDA - CPU, px); both signs tried."""
    Fc = Fc.astype(np.complex128); Fg = Fg.astype(np.complex128)
    before = rel(Fg, Fc)
    after = {s: rel(Fg, ramp(Fc, dxy, pny, pnx, s)) for s in (+1, -1)}
    best = min(after, key=lambda s: np.median(after[s]))
    mag = np.hypot(dxy[:, 0], dxy[:, 1])
    return {"before": [float(np.median(before)), float(before.max())],
            "after": [float(np.median(after[best])), float(after[best].max())], "sign": best,
            "frame1_input_rel_diff": float(before[0]),
            "corr_input_diff_vs_global_shift_diff": float(np.corrcoef(before[1:], mag[1:])[0, 1])}


def cmd_maps(cdir, gdir, traj_json, out, search_ranges=None):
    I_c, I_g = load_index(cdir), load_index(gdir)
    T = json.load(open(traj_json))
    sizes = patch_sizes(T["cpu_run"])
    gdiff = None
    if "global" in T["patches"]:
        gp = T["patches"]["global"]
        gdiff = np.array(gp["T_final_cuda"]) - np.array(gp["T_final_cpu"])
    res = {"rows": [], "shift_tests": {}}
    Rc, Rg = parse_ccf(Path(T["cpu_run"]) / "ccf.txt"), parse_ccf(Path(T["cuda_run"]) / "ccf.txt")
    nxy = movie_size(T["cpu_run"])
    keys = ["global"] + [k for k in T["patches"] if k != "global"]
    for key in keys:
        if key not in T["patches"]:
            continue
        iy, ix = (0, 0) if key == "global" else map(int, key.split(","))
        ctag = {"cpu"}
        gtag = {"cuda-global"} if key == "global" else {T["patches"][key]["cuda_tag"]}
        cc, gc = calls(I_c, ctag, iy, ix), calls(I_g, gtag, iy, ix)
        if not cc or not gc:
            continue
        c_call, g_call = cc[0], gc[0]
        (gt,) = gtag
        pnx, pny = nxy if key == "global" else sizes[(iy, ix)]
        res["shift_tests"][key] = {
            "cpu": shift_test(I_c, "cpu", iy, ix, c_call, Rc["cpu-global" if key == "global" else "cpu"][(iy, ix)], pnx, pny, False),
            "cuda": shift_test(I_g, gt, iy, ix, g_call, Rg[gt][(iy, ix)], pnx, pny, True)}
        st = res["shift_tests"][key]
        print("shift-test", key, "cpu", [("%.1e" % x["resid_rel_max"], "%.0f" % x["max_phase_rad"]) for x in st["cpu"]],
              "cuda", [("%.1e" % x["resid_rel_max"], "%.0f" % x["max_phase_rad"]) for x in st["cuda"]])
        wc = read(I_c[("cpu", iy, ix, c_call, 0, "wt")], False)[0]
        wg = read(I_g[(gt, iy, ix, g_call, 0, "wt")], False)[0]
        kmax = min(T["patches"][key]["iters_cpu"], T["patches"][key]["iters_cuda"])
        for k in range(1, kmax + 1):
            ec, eg = I_c.get(("cpu", iy, ix, c_call, k, "map")), I_g.get((gt, iy, ix, g_call, k, "map"))
            fc, fg = I_c.get(("cpu", iy, ix, c_call, k, "in")), I_g.get((gt, iy, ix, g_call, k, "in"))
            if not (ec and eg and fc and fg):
                continue
            Mc, Mg = read(ec, False), read(eg, False)
            Fc, Fg = read(fc, True), read(fg, True)
            ny, nx = Mc.shape[1:]
            Mc64, Mg64 = map64(Fc, wc, ny, nx), map64(Fg, wg, ny, nx)
            Mx64 = map64(Fg, wc, ny, nx)  # CUDA inputs with CPU weights: isolates the weight rounding
            row = {"patch": key, "iter": k, "n_frames": int(Mc.shape[0]), "ccf": [int(ny), int(nx)]}
            # Whole-map relative norms (median and max over frames).
            stats = {
                "map_cpu_vs_cuda": rel(Mc.astype(np.float64), Mc64),
                "cpu_f32_vs_f64_own": rel(Mc.astype(np.float64), Mc64),
                "cuda_f32_vs_f64_own": rel(Mg.astype(np.float64), Mg64),
                "f64_cpu_in_vs_f64_cuda_in": rel(Mx64, Mc64),
                "f64_weight_effect": rel(Mg64, Mx64),
                "input_cpu_vs_cuda": rel(Fg.astype(np.complex128), Fc.astype(np.complex128)),
            }
            stats["map_cpu_vs_cuda"] = rel(Mg.astype(np.float64), Mc.astype(np.float64))
            for n, v in stats.items():
                row[n] = [float(np.median(v)), float(v.max())]
            # Peak-scale quantities: |D| in ulps of each frame's peak value.
            peak = np.abs(Mc).reshape(Mc.shape[0], -1).max(axis=1).astype(np.float32)
            ulp = np.spacing(peak).astype(np.float64)
            D = Mg.astype(np.float64) - Mc.astype(np.float64)
            off = D.reshape(D.shape[0], -1).mean(axis=1)
            loc = D - off[:, None, None]
            lr = np.sqrt((loc ** 2).reshape(D.shape[0], -1).mean(1)) / ulp
            lm = np.abs(loc).reshape(D.shape[0], -1).max(1) / ulp
            row["D_offset_ulps"] = [float(np.median(np.abs(off) / ulp)), float((np.abs(off) / ulp).max())]
            row["D_local_rms_ulps"] = [float(np.median(lr)), float(lr.max())]
            row["D_local_max_ulps"] = [float(np.median(lm)), float(lm.max())]
            row["D_max_ulps_at_peak"] = [float(np.median(np.abs(D).reshape(D.shape[0], -1).max(1) / ulp)),
                                         float((np.abs(D).reshape(D.shape[0], -1).max(1) / ulp).max())]
            row["D_rms_ulps_at_peak"] = [float(np.median(np.sqrt((D ** 2).reshape(D.shape[0], -1).mean(1)) / ulp)),
                                         float((np.sqrt((D ** 2).reshape(D.shape[0], -1).mean(1)) / ulp).max())]
            row["D_offset_over_rms"] = float(np.median(np.abs(off) / np.sqrt((D ** 2).reshape(D.shape[0], -1).mean(1))))
            row["cpu_comp_max_ulps_at_peak"] = float((np.abs(Mc - Mc64).reshape(Mc.shape[0], -1).max(1) / ulp).max())
            row["cuda_comp_max_ulps_at_peak"] = float((np.abs(Mg - Mg64).reshape(Mg.shape[0], -1).max(1) / ulp).max())
            if k == 1 and key != "global" and gdiff is not None and (iy, ix) in sizes:
                row["input_ramp_test_global_shift_diff"] = ramp_test(Fc, Fg, gdiff, *sizes[(iy, ix)])
            # Event frames: each map's value at both backends' selected peaks.
            fe = T["patches"][key].get("first_event")
            if fe and fe["iter"] == k:
                row["events"] = {}
                for f, ev in fe["frames"].items():
                    i = int(f) - 1
                    at = lambda M, p: float(M[i, p[1] % ny, p[0] % nx])
                    sc, sg = ev["cpu_sel"], ev["cuda_sel"]
                    pk = np.float32(max(abs(at(Mc, sc)), abs(at(Mg, sg))))
                    u = float(np.spacing(pk))
                    e = {"cpu_sel": sc, "cuda_sel": sg,
                         "cpu_map_margin_ulps": ulps(at(Mc, sc), at(Mc, sg)),
                         "cuda_map_margin_ulps": ulps(at(Mg, sg), at(Mg, sc)),
                         "cpu_map_margin_rel": (at(Mc, sc) - at(Mc, sg)) / float(pk),
                         "cuda_map_margin_rel": (at(Mg, sg) - at(Mg, sc)) / float(pk),
                         "D_at_cpu_sel_ulps": (at(Mg, sc) - at(Mc, sc)) / u,
                         "D_at_cuda_sel_ulps": (at(Mg, sg) - at(Mc, sg)) / u,
                         "D_frame_rms_ulps": float(np.sqrt((D[i] ** 2).mean()) / u),
                         "D_frame_offset_ulps": float(D[i].mean() / u),
                         "D_frame_local_max_ulps": float(np.abs(D[i] - D[i].mean()).max() / u),
                         "D_frame_max_ulps": float(np.abs(D[i]).max() / u),
                         "input_rel_diff": float(rel(Fg[i:i + 1].astype(np.complex128), Fc[i:i + 1].astype(np.complex128))[0]),
                         "f64_maps_rel_diff": float(rel(Mx64[i:i + 1], Mc64[i:i + 1])[0]),
                         "f64_cpu_in_margin_ulps": (Mc64[i, sc[1] % ny, sc[0] % nx] - Mc64[i, sg[1] % ny, sg[0] % nx]) / u,
                         "f64_cuda_in_margin_ulps": (Mg64[i, sg[1] % ny, sg[0] % nx] - Mg64[i, sc[1] % ny, sc[0] % nx]) / u}
                    row["events"][f] = e
            res["rows"].append(row)
            print(key, k, {n: ("%.2e/%.2e" % tuple(row[n])) for n in stats}, "Dmax_ulps %.1f" % row["D_max_ulps_at_peak"][1],
                  "off %.1f local_max %.1f" % (row["D_offset_ulps"][1], row["D_local_max_ulps"][1]),
                  "comp_ulps cpu %.1f cuda %.1f" % (row["cpu_comp_max_ulps_at_peak"], row["cuda_comp_max_ulps_at_peak"]))
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "traj":
        cmd_traj(*sys.argv[2:5])
    elif sys.argv[1] == "maps":
        cmd_maps(*sys.argv[2:6])
