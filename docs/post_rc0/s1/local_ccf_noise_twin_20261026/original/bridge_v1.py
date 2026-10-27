#!/usr/bin/env python3
"""Source-pinned NumPy bridge: noisy-state reproduction (phase control) and noise twin (phase twin).

Auxiliary saved-data diagnosis only. Operator transcribed from commit 927a6890 (see PLAN.md section 4).
trig_basis/trig_eval/refine_local_stationary/discrete_and_coupled_fit are copied from
/tmp/mc-local-ccf-pairwise-ref-20261026/pairwise_ref_analysis.py (sha256 50aabc84...d49) unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

SCRATCH = Path("/tmp/mc-local-ccf-noise-twin-bridge-20261026")
ROOT = Path("/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1")
BUNDLE = ROOT / "native-map-bundle-r1"
TRUTH_DIR = ROOT / "capture-bundle-r1" / "truth-scoring-only"
INDEX_SHA = "5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3"
MOVIE_SHA = {"noisy": "5000fbfc0d87cb4be7a8197685297176a2200f9c0d1866f94a7202aa5e85dab3",
             "affine": "1cf918d5da48d4c746020983017222829db9c949e362d07169a823bdc118260a"}
G_EXPECT = [[0.0, 0.0], [-.604719206927727, .5450050278665695], [-1.0768416731350752, .7762553844192274],
            [-1.7222530225852142, .8919129738766326], [-2.2801393506129037, .5656077519907101]]
PROMPT_GAPS_79 = [+.038256127285, +.015335707995, +.000159011673, -.014874256971]
AGG_GAP_79 = 0.0388765339324812
NF, NY, NX = 5, 96, 128
PNY, PNX = 32, 42
NFX_G = NX // 2 + 1
NFX_P = PNX // 2 + 1
AREA_P = PNY * PNX
AREA_G = NY * NX
ARMS = ("B32", "B64")
PATCHES = {79: "patch_62_79_bad", 47: "patch_62_47_central"}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


# ---------------------------------------------------------------- captured arrays
_INDEX = None


def index_sha_map():
    global _INDEX
    if _INDEX is None:
        raw = (BUNDLE / "INDEX.json").read_bytes()
        assert sha256_bytes(raw) == INDEX_SHA, "INDEX.json sha mismatch"
        _INDEX = {f["path"]: f["sha256"] for f in json.loads(raw)["files"]}
    return _INDEX


def load_saved(patch_dir: Path, tag: str):
    """Load <tag>.bin per its json; verify INDEX sha for both files."""
    idx = index_sha_map()
    rel = patch_dir.relative_to(BUNDLE).as_posix()
    for ext in ("bin", "json"):
        key = f"{rel}/{tag}.{ext}"
        assert key in idx, f"not in INDEX: {key}"
        assert sha256_file(patch_dir / f"{tag}.{ext}") == idx[key], f"hash mismatch {key}"
    meta = json.loads((patch_dir / f"{tag}.json").read_text())
    arr = np.fromfile(patch_dir / f"{tag}.bin", dtype=meta["dtype"]).reshape(meta["shape"])
    assert list(arr.strides) == meta["serialized_byte_strides"], f"stride mismatch {tag}"
    if len(meta["shape"]) == 3 and meta["shape"][2] == 2:
        arr = (arr[..., 0] + 1j * arr[..., 1]).astype(np.complex64)
    return arr


def load_json(patch_dir: Path, name: str):
    idx = index_sha_map()
    key = f"{patch_dir.relative_to(BUNDLE).as_posix()}/{name}"
    assert key in idx and sha256_file(patch_dir / name) == idx[key], f"hash mismatch {key}"
    return json.loads((patch_dir / name).read_text())


def patch_dir(cy):
    return BUNDLE / f"evidence/runs/ON/capture/patch-62-{cy}"


# ---------------------------------------------------------------- MRC
def read_mrc(path: Path):
    raw = path.read_bytes()
    nx, ny, nz, mode = np.frombuffer(raw[:16], "<i4")
    assert (nx, ny, nz, mode) == (NX, NY, NF, 2), (nx, ny, nz, mode)
    assert len(raw) == 1024 + NF * NY * NX * 4
    return np.frombuffer(raw[1024:], "<f4").reshape(NF, NY, NX).astype(np.float32)


# ---------------------------------------------------------------- native operator transcription
def fourier_ramp(shift_x_px, shift_y_px, pnx, pny, nfy, nfx):
    """shiftNonSquareImageInFourierTransform(frame, -sx/pnx, -sy/pny) multiplier, double precision.
    Returns (a, b) with multiplier a + i b, native table formulas and ly sign convention (Nyquist row = +nfy/2)."""
    sx, sy = -shift_x_px / pnx, -shift_y_px / pny
    y = np.arange(nfy)
    ly = np.where(y > nfy // 2, y - nfy, y)
    phase_y = 2.0 * np.pi * ly * sy
    phase_x = 2.0 * np.pi * np.arange(nfx) * sx
    siny, cosy = np.sin(phase_y)[:, None], np.cos(phase_y)[:, None]
    sinx, cosx = np.sin(phase_x)[None, :], np.cos(phase_x)[None, :]
    b = sinx * cosy + cosx * siny
    a = cosx * cosy - sinx * siny
    return a, b


def native_cmul_shift(F, a, b):
    """c,d float -> double; ac-bd, (a+b)(c+d)-ac-bd in double; stored back at F's dtype (native: fComplex(float))."""
    c = F.real.astype(np.float64)
    d = F.imag.astype(np.float64)
    ac, bd = a * c, b * d
    out = (ac - bd) + 1j * ((a + b) * (c + d) - ac - bd)
    return out.astype(F.dtype)


def global_to_patches(movie, G, extents, arm):
    """movie [5,96,128] f32 -> list of 5 patch sample arrays [32,42] (arm dtype) and diagnostics."""
    dt = np.float32 if arm == "B32" else np.float64
    cdt = np.complex64 if arm == "B32" else np.complex128
    x0, x1, y0, y1 = extents
    frames, herm = [], []
    for f in range(NF):
        F = np.fft.rfft2(movie[f].astype(dt), norm="forward").astype(cdt)  # /(96*128)
        if f >= 1:
            a, b = fourier_ramp(G[f, 0], G[f, 1], NX, NY, NY, NFX_G)
            F = native_cmul_shift(F, a, b)
        col = {}
        for name, x in (("kx0", 0), ("kxNyq", NFX_G - 1)):
            c = F[:, x].astype(np.complex128)
            col[name] = float(np.max(np.abs(c[1:NY // 2] - np.conj(c[NY - 1:NY // 2:-1]))))
            col[name + "_self_imag_max"] = float(max(abs(c[0].imag), abs(c[NY // 2].imag)))
        herm.append(col)
        I = np.fft.irfft2(F, s=(NY, NX), norm="forward")  # FFTW c2r unnormalized
        assert I.dtype == dt, (I.dtype, dt)
        frames.append(np.ascontiguousarray(I[y0:y1, x0:x1]))
    return frames, herm


def patch_fft(samples, arm):
    cdt = np.complex64 if arm == "B32" else np.complex128
    return np.fft.rfft2(samples, norm="forward").astype(cdt)  # /1344


def agg_native_like(F, W, arm):
    """alignPatch iteration 1, frame 4: Fref float sum j=0..4; ((Fref-F4)*conj(F4))*W; DC zero."""
    cdt = np.complex64 if arm == "B32" else np.complex128
    Wc = W.astype(np.float32 if arm == "B32" else np.float64)
    Fref = F[0].copy()
    for j in range(1, 5):
        Fref = (Fref + F[j]).astype(cdt)
    others = (Fref - F[4]).astype(cdt)
    raw = (others * np.conj(F[4])).astype(cdt)
    pre = (raw * Wc).astype(cdt)
    S = pre.copy()
    S[0, 0] = 0
    return dict(reference=Fref, others=others, raw=raw, pre=pre, S=S)


def pair_spectrum(F, W, j, arm):
    """S_j = F_j conj(F4) W, DC zero; arm precision, returned float64 complex."""
    cdt = np.complex64 if arm == "B32" else np.complex128
    Wc = W.astype(np.float32 if arm == "B32" else np.float64)
    S = ((F[j] * np.conj(F[4])).astype(cdt) * Wc).astype(cdt)
    S[0, 0] = 0
    return S.astype(np.complex128)


def c2r(S):
    return np.fft.irfft2(np.asarray(S).astype(np.complex128), s=(PNY, PNX), norm="forward")  # unnormalized, float64


# ---------------------------------------------------------------- objective (copied from original)
def trig_basis(n, x):
    w = 2.0 * np.pi * np.fft.fftfreq(n)
    b = np.exp(1j * w * x)
    db = 1j * w * b
    ddb = -(w * w) * b
    if n % 2 == 0:
        b[n // 2] = np.cos(np.pi * x)
        db[n // 2] = -np.pi * np.sin(np.pi * x)
        ddb[n // 2] = -(np.pi ** 2) * np.cos(np.pi * x)
    return b, db, ddb


def trig_eval(c, xy):
    ny, nx = c.shape
    bx, dx, xx = trig_basis(nx, float(xy[0]))
    by, dy, yy = trig_basis(ny, float(xy[1]))
    val = float(np.real(by @ c @ bx))
    grad = np.real([by @ c @ dx, dy @ c @ bx])
    hess = np.real([[by @ c @ xx, dy @ c @ dx], [dy @ c @ dx, yy @ c @ bx]])
    return val, grad, hess


def refine_local_stationary(c, init_xy, max_iter=50, tol=1e-13):
    ny, nx = c.shape
    x = np.asarray(init_xy, dtype=np.float64).copy()
    for _ in range(max_iter):
        f, g, h = trig_eval(c, x)
        if np.linalg.norm(g) < tol:
            break
        eigs = np.linalg.eigvalsh(h)
        if eigs[1] < -1e-12:
            step = np.linalg.solve(h, g)
        else:
            h_reg = h - (eigs[1] + 1.0) * np.eye(2)
            step = np.linalg.solve(h_reg, g)
        scale = 1.0
        while scale > 2.0 ** -20:
            xn = x - scale * step
            if trig_eval(c, xn)[0] >= f - 1e-14:
                x = xn
                break
            scale *= 0.5
    x[0] = (x[0] + nx / 2.0) % nx - nx / 2.0
    x[1] = (x[1] + ny / 2.0) % ny - ny / 2.0
    f, g, h = trig_eval(c, x)
    eigs = np.linalg.eigvalsh(h)
    return {"xy": [float(x[0]), float(x[1])], "value": float(f), "grad_norm": float(np.linalg.norm(g)),
            "hess_eigvals": [float(eigs[0]), float(eigs[1])],
            "is_local_concave_stationary": bool(eigs[1] < -1e-9 and np.linalg.norm(g) < 1e-10)}


def discrete_and_coupled_fit(m, search_range=15):
    ny, nx = m.shape
    maxval = -1e30
    ix_best, iy_best = 0, 0
    ties = 0
    for dy in range(-search_range, search_range + 1):
        iy = dy % ny
        for dx in range(-search_range, search_range + 1):
            ix = dx % nx
            val = float(m[iy, ix])
            if val > maxval:
                maxval = val
                ix_best, iy_best = dx, dy
                ties = 1
            elif val == maxval:
                ties += 1
    v = np.array([[float(m[(iy_best + dy) % ny, (ix_best + dx) % nx]) for dx in (-1, 0, 1)] for dy in (-1, 0, 1)])
    gx = 0.5 * (v[1, 2] - v[1, 0])
    gy = 0.5 * (v[2, 1] - v[0, 1])
    hxx = v[1, 2] + v[1, 0] - 2.0 * v[1, 1]
    hyy = v[2, 1] + v[0, 1] - 2.0 * v[1, 1]
    hxy = 0.25 * (v[2, 2] - v[2, 0] - v[0, 2] + v[0, 0])
    det = hxx * hyy - hxy * hxy
    eps = 1e-15
    dx_sep = -0.5 * (v[1, 2] - v[1, 0]) / hxx if abs(hxx) > eps else 0.0
    dy_sep = -0.5 * (v[2, 1] - v[0, 1]) / hyy if abs(hyy) > eps else 0.0
    if not (hxx < 0.0 and det > 0.0):
        verdict, ox, oy = 1, 0.0, 0.0
        sel = (ix_best + dx_sep, iy_best + dy_sep)
    else:
        ox = -(hyy * gx - hxy * gy) / det
        oy = -(hxx * gy - hxy * gx) / det
        if not (abs(ox) <= 1.0 and abs(oy) <= 1.0):
            verdict = 2
            sel = (ix_best + dx_sep, iy_best + dy_sep)
        else:
            verdict = 0
            sel = (ix_best + ox, iy_best + oy)
    return {"integer_xy": [int(ix_best), int(iy_best)], "max_value": float(maxval),
            "equal_max_ties_in_search": int(ties), "coupled_verdict": int(verdict),
            "coupled_offset_xy": [float(ox), float(oy)], "selected_xy": [float(sel[0]), float(sel[1])]}


def coeffs(M):
    return np.fft.fft2(M) / float(M.size)


# ---------------------------------------------------------------- bounds
def beta(xy):
    bx, _, _ = trig_basis(PNX, float(xy[0]))
    by, _, _ = trig_basis(PNY, float(xy[1]))
    return np.outer(by, bx)


def l1_bounds(dS, x_a, x_b):
    """Full-grid Hermitian-completed spectral L1 of a half-spectrum perturbation, plus the gap weighting.
    dS half spectrum [32,22]; completion = fft2(irfft2(dS,norm=forward))/N (columns kx=0,21 projected, others doubled)."""
    dC = coeffs(c2r(dS))
    w = np.abs(beta(x_a) - beta(x_b))
    return {"L1_value": float(np.sum(np.abs(dC))), "L1_gap_weighted": float(np.sum(np.abs(dC) * w)),
            "gap_weight_max": float(w.max())}


def stage_err(b, c):
    b = np.asarray(b)
    c = np.asarray(c)
    d = np.abs(b.astype(np.complex128) - c.astype(np.complex128))
    scale = float(np.max(np.abs(c)))
    return {"max_abs": float(d.max()), "rms": float(np.sqrt(np.mean(d ** 2))), "rel_to_max": float(d.max() / scale),
            "exact_equal_fraction": float(np.mean(b.astype(np.complex128) == c.astype(np.complex128)))}


def fixed_points(cy, G, truth):
    p = patch_dir(cy)
    pk0, pk4 = load_json(p, "iter1-frame0-peak.json"), load_json(p, "iter1-frame4-peak.json")
    lt = truth[:, cy, 62, :] - G
    x_nat = np.array(pk4["raw_selected_xy_ccf"])
    return {"x_nat": x_nat, "x_int": np.array(pk4["integer_xy"], float),
            "x_phys": lt[4] + np.array(pk0["raw_scaled_xy_movie"]),
            "x_truth_unanchored": lt[4], "pair_true_rel_after_G": [lt[4] - lt[j] for j in range(4)],
            "iter1_frame0_raw_selected": np.array(pk0["raw_scaled_xy_movie"])}


def eval_points(M, pts, x_loc_seed):
    c = coeffs(M)
    loc = refine_local_stationary(c, x_loc_seed)
    vals = {k: trig_eval(c, v)[0] for k, v in pts.items() if k != "pair_true_rel_after_G" and k != "iter1_frame0_raw_selected"}
    vals["x_loc"] = loc["value"]
    return {"values": vals, "x_loc": loc,
            "gap_nat_minus_phys": vals["x_nat"] - vals["x_phys"], "gap_int_minus_phys": vals["x_int"] - vals["x_phys"],
            "gap_loc_minus_phys": vals["x_loc"] - vals["x_phys"]}


# ---------------------------------------------------------------- phases
def common_setup():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    index_sha_map()
    mani_path = TRUTH_DIR / "MANIFEST.json"
    mani = json.loads(mani_path.read_text())
    tf = TRUTH_DIR / "noisy_field.npy"
    assert sha256_file(tf) == mani["cases"]["noisy"]["files"]["noisy_field.npy"]
    truth = np.load(tf, allow_pickle=False)
    G_all = {}
    movies = {}
    for name in ("noisy", "affine"):
        pth = SCRATCH / "inputs" / f"{name}.mrcs"
        assert sha256_file(pth) == MOVIE_SHA[name] == mani["cases"][name]["files"][f"{name}.mrcs"], name
        movies[name] = read_mrc(pth)
    return mani, truth, movies


def captured_patch(cy):
    p = patch_dir(cy)
    G = load_saved(p, "global-shifts").astype(np.float64)
    assert G.tolist() == G_EXPECT, "global-shifts.bin differs from prompt G"
    pj = json.loads((p / "patch.json").read_text())
    xs, xe, ys, ye = pj["extents_xy_halfopen"]
    cap = {"G": G, "extents": (xs, xe, ys, ye), "patch_json": pj,
           "W": load_saved(p, "weights"),
           "samples": [load_saved(p, f"initial-frame{j}-samples") for j in range(5)],
           "F": [load_saved(p, f"initial-frame{j}-fft") for j in range(5)],
           "Fwin": [load_saved(p, f"iter1-frame{j}-window-fft") for j in range(5)],
           "reference": load_saved(p, "iter1-reference"),
           "others4": load_saved(p, "iter1-frame4-sum-of-others"),
           "raw4": load_saved(p, "iter1-frame4-raw-product"),
           "pre4": load_saved(p, "iter1-frame4-weighted-pre-dc"),
           "S4": load_saved(p, "iter1-frame4-weighted-api-consumed"),
           "c2rbefore4": load_saved(p, "iter1-frame4-c2r-temporary-before"),
           "Sj": [load_saved(p, f"iter1-frame{j}-weighted-api-consumed") for j in range(5)],
           "Mj": [load_saved(p, f"iter1-frame{j}-real-map").astype(np.float64) for j in range(5)]}
    return cap


def control_patch(cy, movie_noisy, truth):
    cap = captured_patch(cy)
    G, W = cap["G"], cap["W"]
    pts = fixed_points(cy, G, truth)
    x0, x1, y0, y1 = cap["extents"]
    ext = (x0, x1, y0, y1)
    out = {"patch": PATCHES[cy], "extents_x0x1y0y1": list(ext), "G_equals_prompt_bitwise": True,
           "fixed_points": {k: (v.tolist() if hasattr(v, "tolist") else [t.tolist() for t in v]) for k, v in pts.items()}}
    # captured-state reference (original method replay)
    Fc = [f.astype(np.complex128) for f in cap["F"]]
    Sc_pair = [pair_spectrum(cap["F"], W, j, "B64") for j in range(4)]
    Mc_pair = [c2r(s) for s in Sc_pair]
    M_nat = cap["Mj"][4]
    Sc4 = cap["S4"].astype(np.complex128)
    M_reg = c2r(Sc4)
    ev_nat = eval_points(M_nat, pts, pts["x_nat"])
    ev_reg = eval_points(M_reg, pts, pts["x_nat"])
    ev_pair_c = [eval_points(Mc_pair[j], pts, pts["x_nat"]) for j in range(4)]
    eng = {}
    for j in range(5):
        e = np.abs(cap["Mj"][j] - c2r(cap["Sj"][j].astype(np.complex128)))
        eng[f"frame{j}_native_map_vs_numpy_irfft2_of_captured_consumed_max_abs"] = float(e.max())
    dC_eng = coeffs(M_nat) - coeffs(M_reg)
    w_gap = np.abs(beta(pts["x_nat"]) - beta(pts["x_phys"]))
    eng["L1_value_B_eng"] = float(np.sum(np.abs(dC_eng)))
    eng["L1_gap_weighted_B_eng"] = float(np.sum(np.abs(dC_eng) * w_gap))
    eng["gap_native_map"] = ev_nat["gap_nat_minus_phys"]
    eng["gap_numpy_regen_from_captured_consumed"] = ev_reg["gap_nat_minus_phys"]
    eng["gap_difference_measured"] = ev_nat["gap_nat_minus_phys"] - ev_reg["gap_nat_minus_phys"]
    eng["c2r_temporary_before_equals_consumed_exactly"] = bool(np.array_equal(cap["c2rbefore4"], cap["S4"]))
    eng["consumed_equals_pre_dc_except_DC"] = bool(np.array_equal(np.delete(cap["pre4"].ravel(), 0), np.delete(cap["S4"].ravel(), 0)))
    eng["consumed_DC"] = [float(cap["S4"][0, 0].real), float(cap["S4"][0, 0].imag)]
    out["captured_state"] = {
        "gap_agg_native_map": ev_nat["gap_nat_minus_phys"], "native_map_values": ev_nat["values"],
        "pairwise_gap_nat_minus_phys": [e["gap_nat_minus_phys"] for e in ev_pair_c],
        "pairwise_values": [e["values"] for e in ev_pair_c],
        "sum_of_pairwise_gaps": float(sum(e["gap_nat_minus_phys"] for e in ev_pair_c)),
        "remainder_native_minus_sum_pairwise": ev_nat["gap_nat_minus_phys"] - float(sum(e["gap_nat_minus_phys"] for e in ev_pair_c)),
        "engine_check": eng}
    if cy == 79:
        out["captured_state"]["replay_vs_prompt_pairwise_gaps_abs_diff"] = [abs(a - b) for a, b in zip(
            out["captured_state"]["pairwise_gap_nat_minus_phys"], PROMPT_GAPS_79)]
        out["captured_state"]["replay_vs_prompt_agg_gap_abs_diff"] = abs(ev_nat["gap_nat_minus_phys"] - AGG_GAP_79)
    # window geometry and linkage
    out["geometry_checks"] = {
        "window_fft_equals_initial_fft_exactly": [bool(np.array_equal(cap["Fwin"][j], cap["F"][j])) for j in range(5)],
        "fft_config": json.loads((patch_dir(cy) / "fft-config.json").read_text()),
        "sample_shape": list(cap["samples"][0].shape), "fft_shape": list(cap["F"][0].shape)}
    out["arms"] = {}
    for arm in ARMS:
        samples, herm = global_to_patches(movie_noisy, G, ext, arm)
        Fb = [patch_fft(s, arm) for s in samples]
        # sample->FFT linkage: captured samples through the bridge patch FFT vs captured FFT
        link = [stage_err(patch_fft(cap["samples"][j].astype(np.float32 if arm == "B32" else np.float64), arm), cap["F"][j]) for j in range(5)]
        st = {"samples": [stage_err(samples[j], cap["samples"][j]) for j in range(5)],
              "samples_bytes_identical": [bool(np.array_equal(samples[j].astype(np.float32), cap["samples"][j])) for j in range(5)],
              "fft": [stage_err(Fb[j], cap["F"][j]) for j in range(5)],
              "sample_to_fft_linkage_captured_samples_through_bridge_fft": link,
              "global_shifted_spectrum_hermitian_residuals": herm}
        ag = agg_native_like(Fb, W, arm)
        st["reference"] = stage_err(ag["reference"], cap["reference"])
        st["sum_of_others_f4"] = stage_err(ag["others"], cap["others4"])
        st["raw_product_f4"] = stage_err(ag["raw"], cap["raw4"])
        st["weighted_pre_dc_f4"] = stage_err(ag["pre"], cap["pre4"])
        st["weighted_consumed_f4"] = stage_err(ag["S"], cap["S4"])
        # propagation: aggregate
        dS = ag["S"].astype(np.complex128) - Sc4
        M_arm = c2r(ag["S"])
        ev_arm = eval_points(M_arm, pts, pts["x_nat"])
        bnd = l1_bounds(dS, pts["x_nat"], pts["x_phys"])
        agg = {"measured_gap_arm_map": ev_arm["gap_nat_minus_phys"],
               "measured_gap_numpy_regen_captured": ev_reg["gap_nat_minus_phys"],
               "measured_delta_gap_state": ev_arm["gap_nat_minus_phys"] - ev_reg["gap_nat_minus_phys"],
               "B_state_L1_gap_weighted": bnd["L1_gap_weighted"], "B_state_L1_value": bnd["L1_value"],
               "B_eng_gap_weighted": eng["L1_gap_weighted_B_eng"],
               "B_total_gap": bnd["L1_gap_weighted"] + eng["L1_gap_weighted_B_eng"],
               "measured_delta_gap_vs_native": ev_arm["gap_nat_minus_phys"] - ev_nat["gap_nat_minus_phys"],
               "measured_inside_state_bound": bool(abs(ev_arm["gap_nat_minus_phys"] - ev_reg["gap_nat_minus_phys"]) <= bnd["L1_gap_weighted"] * (1 + 1e-9)),
               "measured_vs_native_inside_total_bound": bool(abs(ev_arm["gap_nat_minus_phys"] - ev_nat["gap_nat_minus_phys"]) <= (bnd["L1_gap_weighted"] + eng["L1_gap_weighted_B_eng"]) * (1 + 1e-9))}
        # propagation: pairwise
        pw = []
        for j in range(4):
            Sb = pair_spectrum(Fb, W, j, arm)
            dSj = Sb - Sc_pair[j]
            b = l1_bounds(dSj, pts["x_nat"], pts["x_phys"])
            evb = eval_points(c2r(Sb), pts, pts["x_nat"])
            # cross-product identity bound (float64 products only)
            F64b = [f.astype(np.complex128) for f in Fb]
            dFj, dF4 = F64b[j] - Fc[j], F64b[4] - Fc[4]
            prod_b = W.astype(np.float64) * (np.abs(dFj) * np.abs(Fc[4]) + np.abs(Fc[j]) * np.abs(dF4) + np.abs(dFj) * np.abs(dF4))
            dS64 = (F64b[j] * np.conj(F64b[4]) - Fc[j] * np.conj(Fc[4])) * W.astype(np.float64)
            dS64[0, 0] = 0
            pw.append({"ref_j": j, "gap_arm": evb["gap_nat_minus_phys"], "gap_captured_state": ev_pair_c[j]["gap_nat_minus_phys"],
                       "measured_delta_gap": evb["gap_nat_minus_phys"] - ev_pair_c[j]["gap_nat_minus_phys"],
                       "B_state_L1_gap_weighted": b["L1_gap_weighted"], "B_state_L1_value": b["L1_value"],
                       "measured_inside_bound": bool(abs(evb["gap_nat_minus_phys"] - ev_pair_c[j]["gap_nat_minus_phys"]) <= b["L1_gap_weighted"] * (1 + 1e-9)),
                       "cross_product_identity_bound_holds_f64": bool(np.all(np.abs(dS64) <= prod_b * (1 + 1e-9) + 1e-300)),
                       "cross_product_bound_sum_over_half_spectrum": float(prod_b.sum()),
                       "dS_half_L1": float(np.abs(dSj).sum())})
        sum_pairs_gap = float(sum(p["gap_arm"] for p in pw))
        st["aggregate_propagation"] = agg
        st["pairwise_propagation"] = pw
        st["sum_of_pairwise_gaps_arm"] = sum_pairs_gap
        # controlled-state criterion (bad patch gates; central reported)
        agg["captured_aggregate_gap"] = ev_nat["gap_nat_minus_phys"]
        agg["resolves_sign_B_total_lt_captured_gap"] = bool(agg["B_total_gap"] < abs(ev_nat["gap_nat_minus_phys"]))
        for p in pw:
            p["resolved_abs_gap_gt_bound"] = bool(abs(p["gap_captured_state"]) > p["B_state_L1_gap_weighted"])
        out["arms"][arm] = st
    return out


def controlled_flags(res):
    return {arm: bool(res["patches"][PATCHES[79]]["arms"][arm]["aggregate_propagation"]["resolves_sign_B_total_lt_captured_gap"]
                      and all(p["measured_inside_bound"] for p in res["patches"][PATCHES[79]]["arms"][arm]["pairwise_propagation"])
                      and res["patches"][PATCHES[79]]["arms"][arm]["aggregate_propagation"]["measured_inside_state_bound"])
            for arm in ARMS}


def phase_control(mani, truth, movies):
    t0 = time.perf_counter()
    res = {"phase": "control", "plan_sha256": sha256_file(SCRATCH / "PLAN.md"), "numpy": np.__version__,
           "script_sha256": sha256_file(Path(__file__)), "bundle_index_sha256": INDEX_SHA,
           "fft_dtype_probe": {"rfft2_f32": str(np.fft.rfft2(np.zeros((4, 4), np.float32)).dtype),
                               "irfft2_c64": str(np.fft.irfft2(np.zeros((4, 3), np.complex64), s=(4, 4)).dtype)},
           "patches": {}}
    for cy in (79, 47):
        res["patches"][PATCHES[cy]] = control_patch(cy, movies["noisy"], truth)
    res["controlled_bad_patch_by_arm"] = controlled_flags(res)
    res["controlled"] = bool(any(res["controlled_bad_patch_by_arm"].values()))
    res["elapsed_seconds"] = time.perf_counter() - t0
    (SCRATCH / "RESULT_control.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


# ---------------------------------------------------------------- twin verification
def twin_verification(mani, movies):
    rn, ra = mani["cases"]["noisy"]["recipe"], mani["cases"]["affine"]["recipe"]
    diff_keys = sorted(k for k in set(rn) | set(ra) if rn.get(k) != ra.get(k))
    noise = np.random.Generator(np.random.PCG64(rn["seed"])).normal(0, rn["noise"] * rn["contrast"], (NF, NY, NX))
    d = movies["noisy"].astype(np.float64) - movies["affine"].astype(np.float64)
    rb = np.spacing(np.abs(movies["noisy"])).astype(np.float64) / 2 + np.spacing(np.abs(movies["affine"])).astype(np.float64) / 2
    resid = np.abs(d - noise)
    fn, fa = mani["cases"]["noisy"]["files"], mani["cases"]["affine"]["files"]
    return {"recipe_keys_differing": diff_keys,
            "only_noise_and_role_differ": diff_keys == ["noise", "role"],
            "field_hash_equal": fn["noisy_field.npy"] == fa["affine_field.npy"],
            "target_hash_equal": fn["noisy_target.npy"] == fa["affine_target.npy"],
            "manifest_numpy": mani["numpy"], "numpy_now": np.__version__,
            "noise_regen_convention": "Generator(PCG64(seed)).normal(0, noise*contrast, (5,96,128)) from render()",
            "noisy_minus_affine_mean": float(d.mean()), "noisy_minus_affine_std": float(d.std()),
            "regen_noise_std": float(noise.std()),
            "resid_max_abs": float(resid.max()), "resid_rounding_bound_max": float(rb.max()),
            "resid_within_float32_rounding_bound_everywhere": bool(np.all(resid <= rb * (1 + 1e-12))),
            "n_elements_exceeding_bound": int(np.sum(resid > rb * (1 + 1e-12))),
            "movie_shapes": [list(movies["noisy"].shape), list(movies["affine"].shape)],
            "movie_min_max_noisy": [float(movies["noisy"].min()), float(movies["noisy"].max())],
            "movie_min_max_affine": [float(movies["affine"].min()), float(movies["affine"].max())]}


def twin_patch(cy, movies, truth, arm, ctrl):
    cap = captured_patch(cy)
    G, W = cap["G"], cap["W"]
    pts = fixed_points(cy, G, truth)
    ext = cap["extents"]
    ext = (ext[0], ext[1], ext[2], ext[3])
    out = {}
    for name in ("noisy", "affine"):
        samples, _ = global_to_patches(movies[name], G, ext, arm)
        Fb = [patch_fft(s, arm) for s in samples]
        ag = agg_native_like(Fb, W, arm)
        M_agg = c2r(ag["S"])
        ev_agg = eval_points(M_agg, pts, pts["x_nat"])
        comps = []
        sum_map = np.zeros((PNY, PNX))
        for j in range(4):
            Sj = pair_spectrum(Fb, W, j, arm)
            Mj = c2r(Sj)
            sum_map += Mj
            ev = eval_points(Mj, pts, pts["x_nat"])
            c = coeffs(Mj)
            v_rel = trig_eval(c, pts["pair_true_rel_after_G"][j])[0]
            pk = discrete_and_coupled_fit(Mj)
            comps.append({"ref_j": j, "values": ev["values"], "gap_nat_minus_phys": ev["gap_nat_minus_phys"],
                          "gap_int_minus_phys": ev["gap_int_minus_phys"], "gap_loc_minus_phys": ev["gap_loc_minus_phys"],
                          "x_loc": ev["x_loc"]["xy"], "x_loc_is_concave_stationary": ev["x_loc"]["is_local_concave_stationary"],
                          "val_at_true_pairwise_rel_after_G": v_rel,
                          "gap_true_pair_rel_minus_phys": v_rel - ev["values"]["x_phys"],
                          "native_rule_integer_peak_descriptive": pk})
        ev_sum = eval_points(sum_map, pts, pts["x_nat"])
        out[name] = {"aggregate": {"values": ev_agg["values"], "gap_nat_minus_phys": ev_agg["gap_nat_minus_phys"],
                                   "gap_int_minus_phys": ev_agg["gap_int_minus_phys"], "gap_loc_minus_phys": ev_agg["gap_loc_minus_phys"],
                                   "x_loc": ev_agg["x_loc"]["xy"], "native_rule_integer_peak_descriptive": discrete_and_coupled_fit(M_agg),
                                   "state_energy_rms_Fj_nonDC": float(np.sqrt(np.mean(np.abs(np.stack([f.astype(np.complex128) for f in Fb]))[:, 1:, 1:] ** 2)))},
                     "sum_of_pairwise_aux_map": {"gap_nat_minus_phys": ev_sum["gap_nat_minus_phys"],
                                                  "numeric_remainder_agg_minus_sum": ev_agg["gap_nat_minus_phys"] - ev_sum["gap_nat_minus_phys"]},
                     "components": comps, "sum_of_component_gaps": float(sum(c["gap_nat_minus_phys"] for c in comps))}
    return out


def phase_twin(mani, truth, movies):
    ctrl_path = SCRATCH / "RESULT_control.json"
    ctrl = json.loads(ctrl_path.read_text())
    assert ctrl["controlled"] is True, "twin refused: control not controlled"
    ver = twin_verification(mani, movies)
    res = {"phase": "twin", "plan_sha256": sha256_file(SCRATCH / "PLAN.md"), "script_sha256": sha256_file(Path(__file__)),
           "control_result_sha256": sha256_file(ctrl_path), "twin_verification": ver, "arms": {}}
    if not (ver["only_noise_and_role_differ"] and ver["field_hash_equal"] and ver["target_hash_equal"]
            and ver["resid_within_float32_rounding_bound_everywhere"]):
        res["stopped"] = "twin verification failed; no twin values computed"
        (SCRATCH / "RESULT_twin.json").write_text(json.dumps(res, indent=1) + "\n")
        return res
    for arm in ARMS:
        if not ctrl["controlled_bad_patch_by_arm"][arm]:
            res["arms"][arm] = {"skipped": "arm not controlled in control phase (C1/C2)"}
            continue
        res["arms"][arm] = {PATCHES[cy]: twin_patch(cy, movies, truth, arm, ctrl) for cy in (79, 47)}
    (SCRATCH / "RESULT_twin.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["control", "twin"], required=True)
    a = ap.parse_args()
    mani, truth, movies = common_setup()
    r = phase_control(mani, truth, movies) if a.phase == "control" else phase_twin(mani, truth, movies)
    if a.phase == "control":
        print(json.dumps({"controlled": r["controlled"], "by_arm": r["controlled_bad_patch_by_arm"]}, indent=1))
    else:
        print(json.dumps({"stopped": r.get("stopped"), "arms": list(r["arms"])}, indent=1))
