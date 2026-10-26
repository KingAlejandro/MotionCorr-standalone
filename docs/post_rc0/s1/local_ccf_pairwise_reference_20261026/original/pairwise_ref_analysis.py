#!/usr/bin/env python3
"""
Bounded saved-data pairwise reference decomposition for Iteration 1, Frame 4
at patches (62, 79) [bad] and (62, 47) [central comparison].
No native jobs, no SSH, no fitting, no global certification claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
import numpy as np

BUNDLE_ROOT = Path("/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1")
BUNDLE = BUNDLE_ROOT / "native-map-bundle-r1"
TRUTH_DIR = BUNDLE_ROOT / "capture-bundle-r1" / "truth-scoring-only"
OUT_DIR = Path("/tmp/mc-local-ccf-pairwise-ref-20261026")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_saved_array(patch_dir: Path, tag: str) -> np.ndarray:
    meta = json.loads((patch_dir / f"{tag}.json").read_text())
    arr = np.fromfile(patch_dir / f"{tag}.bin", dtype=meta["dtype"]).reshape(meta["shape"])
    assert list(arr.strides) == meta["serialized_byte_strides"], f"Stride mismatch on {tag}"
    if len(meta["shape"]) == 3 and meta["shape"][2] == 2:
        # Convert float32 [..., 2] real/imag to complex64
        arr = arr[..., 0] + 1j * arr[..., 1]
    return arr


def trig_basis(n: int, x: float):
    """Symmetric cosine Nyquist splitting matching v3 oracle and parent audit.py."""
    w = 2.0 * np.pi * np.fft.fftfreq(n)
    b = np.exp(1j * w * x)
    db = 1j * w * b
    ddb = -(w * w) * b
    if n % 2 == 0:
        b[n // 2] = np.cos(np.pi * x)
        db[n // 2] = -np.pi * np.sin(np.pi * x)
        ddb[n // 2] = -(np.pi ** 2) * np.cos(np.pi * x)
    return b, db, ddb


def trig_eval(c: np.ndarray, xy: tuple[float, float] | list[float] | np.ndarray):
    """Evaluate value, gradient, and 2x2 Hessian of real trigonometric interpolant with Fourier coeffs c = fft2(m)/m.size."""
    ny, nx = c.shape
    bx, dx, xx = trig_basis(nx, float(xy[0]))
    by, dy, yy = trig_basis(ny, float(xy[1]))
    val = float(np.real(by @ c @ bx))
    grad = np.real([by @ c @ dx, dy @ c @ bx])
    hess = np.real([[by @ c @ xx, dy @ c @ dx], [dy @ c @ dx, yy @ c @ bx]])
    return val, grad, hess


def refine_local_stationary(c: np.ndarray, init_xy, max_iter: int = 50, tol: float = 1e-13):
    """Unconstrained damped Newton refinement on the periodic torus; reports local stationarity/concavity."""
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
    # Wrap to canonical torus [-nx/2, nx/2) x [-ny/2, ny/2)
    x[0] = (x[0] + nx / 2.0) % nx - nx / 2.0
    x[1] = (x[1] + ny / 2.0) % ny - ny / 2.0
    f, g, h = trig_eval(c, x)
    eigs = np.linalg.eigvalsh(h)
    return {
        "xy": [float(x[0]), float(x[1])],
        "value": float(f),
        "grad_norm": float(np.linalg.norm(g)),
        "hess_eigvals": [float(eigs[0]), float(eigs[1])],
        "is_local_concave_stationary": bool(eigs[1] < -1e-9 and np.linalg.norm(g) < 1e-10),
    }


def discrete_and_coupled_fit(m: np.ndarray, search_range: int = 15):
    """Exact native integer search in [-15, 15]^2 and 3x3 coupled/separable subpixel fit."""
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

    v = np.array([[float(m[(iy_best + dy) % ny, (ix_best + dx) % nx]) for dx in (-1, 0, 1)] for dy in (-1, 0, 1)], dtype=np.float64)
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
        verdict = 1
        ox, oy = 0.0, 0.0
        sel_x, sel_y = ix_best + dx_sep, iy_best + dy_sep
    else:
        ox = -(hyy * gx - hxy * gy) / det
        oy = -(hxx * gy - hxy * gx) / det
        if not (abs(ox) <= 1.0 and abs(oy) <= 1.0):
            verdict = 2
            sel_x, sel_y = ix_best + dx_sep, iy_best + dy_sep
        else:
            verdict = 0
            sel_x, sel_y = ix_best + ox, iy_best + oy

    return {
        "integer_xy": [int(ix_best), int(iy_best)],
        "max_value": float(maxval),
        "equal_max_ties_in_search": int(ties),
        "coupled_verdict": int(verdict),
        "coupled_offset_xy": [float(ox), float(oy)],
        "separable_xy": [float(ix_best + dx_sep), float(iy_best + dy_sep)],
        "selected_xy": [float(sel_x), float(sel_y)],
        "within_coupled_verdict0_reach16": bool(verdict == 0 and abs(sel_x) <= search_range + 1.0 and abs(sel_y) <= search_range + 1.0),
    }


def analyze_patch(cy: int, truth: np.ndarray) -> dict:
    p = BUNDLE / f"evidence/runs/ON/capture/patch-62-{cy}"
    W_f32 = load_saved_array(p, "weights")                     # float32 (32, 22)
    W_f64 = W_f32.astype(np.float64)

    # Load entering windowed frame spectra for iteration 1, frames 0..4
    F_f32 = [load_saved_array(p, f"iter1-frame{j}-window-fft") for j in range(5)]  # complex64 (32, 22)
    F_f64 = [f.astype(np.complex128) for f in F_f32]

    # Load saved aggregate artifacts for iteration 1, frame 4
    sum_others_saved = load_saved_array(p, "iter1-frame4-sum-of-others")
    raw_prod_saved = load_saved_array(p, "iter1-frame4-raw-product")
    weighted_pre_dc_saved = load_saved_array(p, "iter1-frame4-weighted-pre-dc")
    weighted_consumed_saved = load_saved_array(p, "iter1-frame4-weighted-api-consumed")
    I_native = load_saved_array(p, "iter1-frame4-real-map").astype(np.float64)

    pk0 = json.loads((p / "iter1-frame0-peak.json").read_text())
    pk4 = json.loads((p / "iter1-frame4-peak.json").read_text())
    G = load_saved_array(p, "global-shifts").astype(np.float64)  # (5, 2)
    local_truth = truth[:, cy, 62, :] - G                        # (5, 2)

    # Fixed evaluation points
    x_nat = np.array(pk4["raw_selected_xy_ccf"], dtype=np.float64)
    x_int = np.array(pk4["integer_xy"], dtype=np.float64)
    r0_iter1 = np.array(pk0["raw_scaled_xy_movie"], dtype=np.float64)
    # Explicit aggregate observed-frame0-gauge physical point:
    x_phys = local_truth[4] + r0_iter1
    # Also record pure frame-0 truth residual without r0_iter1 offset:
    x_truth_unanchored = local_truth[4]

    # Primary native real map trigonometric Fourier coefficients
    c_native = np.fft.fft2(I_native) / float(I_native.size)
    loc_native = refine_local_stationary(c_native, x_nat)
    x_loc = np.array(loc_native["xy"], dtype=np.float64)

    # Construct the 4 individual pairwise spectra j = 0, 1, 2, 3
    # Both in float32 (matching C++ fComplex) and in float64
    S_pair_f32 = []
    S_pair_f64 = []
    I_pair_aux = []
    c_pair_aux = []

    for j in range(4):
        # float32 pairwise cross-spectrum
        prod_f32 = (F_f32[j] * np.conj(F_f32[4])) * W_f32
        prod_f32_dc = prod_f32.copy()
        prod_f32_dc[0, 0] = 0.0 + 0.0j
        S_pair_f32.append(prod_f32_dc)

        # float64 pairwise cross-spectrum
        prod_f64 = (F_f64[j] * np.conj(F_f64[4])) * W_f64
        prod_f64_dc = prod_f64.copy()
        prod_f64_dc[0, 0] = 0.0 + 0.0j
        S_pair_f64.append(prod_f64_dc)

        # Auxiliary regenerated real map via float64 NumPy irfft2 * (32 * 42)
        # Note: at iteration 1, all F_j come directly from r2c forward FFT of real patch pixels,
        # so F_j and S_j are strictly R2C Hermitian-symmetric!
        m_j = np.fft.irfft2(prod_f64_dc, s=(32, 42)) * float(32 * 42)
        I_pair_aux.append(m_j)
        c_pair_aux.append(np.fft.fft2(m_j) / float(m_j.size))

    # Algebraic sum of the 4 pairwise components
    S_sum_f32 = ((S_pair_f32[0] + S_pair_f32[1]) + S_pair_f32[2]) + S_pair_f32[3]
    S_sum_f64 = sum(S_pair_f64)
    I_sum_aux = sum(I_pair_aux)
    c_sum_aux = np.fft.fft2(I_sum_aux) / float(I_sum_aux.size)

    # Also regenerate real map from the exact saved float32 weighted_consumed_saved via float64 irfft2
    I_from_saved_consumed_aux = np.fft.irfft2(weighted_consumed_saved.astype(np.complex128), s=(32, 42)) * float(32 * 42)

    # Verify Hermitian symmetry of each pairwise spectrum S_j at iteration 1
    herm_checks = []
    for j in range(4):
        Sj = S_pair_f64[j]
        c0_err = max(abs(Sj[y, 0] - np.conj(Sj[(32 - y) % 32, 0])) for y in range(1, 16))
        c21_err = max(abs(Sj[y, 21] - np.conj(Sj[(32 - y) % 32, 21])) for y in range(1, 16))
        corner_imag = max(abs(np.imag(Sj[0, 0])), abs(np.imag(Sj[16, 0])), abs(np.imag(Sj[0, 21])), abs(np.imag(Sj[16, 21])))
        herm_checks.append({
            "ref_frame_j": j,
            "max_kx0_conj_err": float(c0_err),
            "max_kx21_conj_err": float(c21_err),
            "max_corner_imag": float(corner_imag),
        })

    # Evaluate primary native interpolant and auxiliary sum interpolant at the fixed points
    def eval_summary(c_mat):
        v_nat = trig_eval(c_mat, x_nat)[0]
        v_int = trig_eval(c_mat, x_int)[0]
        v_loc = trig_eval(c_mat, x_loc)[0]
        v_phys = trig_eval(c_mat, x_phys)[0]
        v_unanch = trig_eval(c_mat, x_truth_unanchored)[0]
        return {
            "val_at_x_nat": v_nat,
            "val_at_x_int": v_int,
            "val_at_x_loc": v_loc,
            "val_at_x_phys_f0_gauge": v_phys,
            "val_at_x_truth_unanchored": v_unanch,
            "gap_nat_minus_phys": float(v_nat - v_phys),
            "gap_int_minus_phys": float(v_int - v_phys),
            "gap_loc_minus_phys": float(v_loc - v_phys),
            "gap_nat_minus_unanch": float(v_nat - v_unanch),
        }

    agg_native_eval = eval_summary(c_native)
    agg_aux_sum_eval = eval_summary(c_sum_aux)

    # Evaluate each pairwise component j = 0, 1, 2, 3
    pairwise_components = []
    for j in range(4):
        ev_j = eval_summary(c_pair_aux[j])
        pk_j = discrete_and_coupled_fit(I_pair_aux[j], search_range=15)
        loc_from_pk_j = refine_local_stationary(c_pair_aux[j], pk_j["selected_xy"])
        loc_from_phys_j = refine_local_stationary(c_pair_aux[j], x_phys)
        # True pairwise relative shift between frame 4 and frame j at patch center:
        x_pair_true_rel = local_truth[4] - local_truth[j]
        val_at_pair_true_rel = trig_eval(c_pair_aux[j], x_pair_true_rel)[0]

        pairwise_components.append({
            "ref_frame_j": j,
            "fixed_point_evaluations": ev_j,
            "true_pairwise_relative_shift_4_minus_j": {
                "xy": x_pair_true_rel.tolist(),
                "val_at_true_pairwise_shift": float(val_at_pair_true_rel),
                "gap_x_nat_minus_true_pairwise_shift": float(ev_j["val_at_x_nat"] - val_at_pair_true_rel),
            },
            "component_own_peaks_descriptive": {
                "native_rule_search_and_3x3": pk_j,
                "local_stationary_from_component_peak": loc_from_pk_j,
                "local_stationary_from_x_phys": loc_from_phys_j,
            },
        })

    # Check exact additive closure across j = 0..3
    sum_val_nat = sum(comp["fixed_point_evaluations"]["val_at_x_nat"] for comp in pairwise_components)
    sum_val_phys = sum(comp["fixed_point_evaluations"]["val_at_x_phys_f0_gauge"] for comp in pairwise_components)
    sum_gap_nat_phys = sum(comp["fixed_point_evaluations"]["gap_nat_minus_phys"] for comp in pairwise_components)
    sum_gap_int_phys = sum(comp["fixed_point_evaluations"]["gap_int_minus_phys"] for comp in pairwise_components)
    sum_gap_loc_phys = sum(comp["fixed_point_evaluations"]["gap_loc_minus_phys"] for comp in pairwise_components)

    gaps_nat_phys = [comp["fixed_point_evaluations"]["gap_nat_minus_phys"] for comp in pairwise_components]
    n_positive_gaps = sum(1 for g in gaps_nat_phys if g > 0.0)
    n_negative_gaps = sum(1 for g in gaps_nat_phys if g < 0.0)
    max_pos_idx = int(np.argmax(gaps_nat_phys))
    min_neg_idx = int(np.argmin(gaps_nat_phys))

    # Leave-one-reference-out (3-of-4) sub-aggregates at fixed points (algebraic combinations only)
    leave_one_ref_out = []
    for drop_j in range(4):
        kept = [j for j in range(4) if j != drop_j]
        I_sub = sum(I_pair_aux[j] for j in kept)
        c_sub = np.fft.fft2(I_sub) / float(I_sub.size)
        ev_sub = eval_summary(c_sub)
        pk_sub = discrete_and_coupled_fit(I_sub, search_range=15)
        leave_one_ref_out.append({
            "dropped_ref_frame": drop_j,
            "kept_ref_frames": kept,
            "fixed_point_evaluations": ev_sub,
            "sub_aggregate_native_rule_peak": pk_sub,
        })

    return {
        "patch_center_xy": [62, cy],
        "fixed_points": {
            "x_nat_raw_selected_xy": x_nat.tolist(),
            "x_int_xy": x_int.tolist(),
            "x_loc_stationary_xy": x_loc.tolist(),
            "x_phys_observed_f0_gauge_xy": x_phys.tolist(),
            "x_truth_unanchored_xy": x_truth_unanchored.tolist(),
            "iter1_frame0_raw_selected_xy": r0_iter1.tolist(),
        },
        "saved_vs_regenerated_discrepancies": {
            "spectrum_f32_sum_vs_saved_consumed_max_abs": float(np.max(np.abs(S_sum_f32 - weighted_consumed_saved))),
            "spectrum_f64_sum_vs_saved_consumed_max_abs": float(np.max(np.abs(S_sum_f64 - weighted_consumed_saved.astype(np.complex128)))),
            "real_map_aux_sum_f64_vs_saved_native_real_map_max_abs": float(np.max(np.abs(I_sum_aux - I_native))),
            "real_map_aux_sum_f64_vs_saved_native_real_map_rms": float(np.sqrt(np.mean((I_sum_aux - I_native) ** 2))),
            "real_map_from_saved_consumed_f64_vs_saved_native_real_map_max_abs": float(np.max(np.abs(I_from_saved_consumed_aux - I_native))),
            "pairwise_iter1_hermitian_checks": herm_checks,
        },
        "aggregate_evaluations": {
            "primary_native_real_map": agg_native_eval,
            "auxiliary_sum_of_4_pairwise": agg_aux_sum_eval,
        },
        "pairwise_components_j0_to_3": pairwise_components,
        "additive_closure_and_cancellation_summary": {
            "component_val_at_x_nat_per_j": [comp["fixed_point_evaluations"]["val_at_x_nat"] for comp in pairwise_components],
            "component_val_at_x_phys_per_j": [comp["fixed_point_evaluations"]["val_at_x_phys_f0_gauge"] for comp in pairwise_components],
            "component_gap_nat_minus_phys_per_j": gaps_nat_phys,
            "component_gap_int_minus_phys_per_j": [comp["fixed_point_evaluations"]["gap_int_minus_phys"] for comp in pairwise_components],
            "component_gap_loc_minus_phys_per_j": [comp["fixed_point_evaluations"]["gap_loc_minus_phys"] for comp in pairwise_components],
            "sum_of_4_component_vals_at_x_nat": float(sum_val_nat),
            "sum_of_4_component_vals_at_x_phys": float(sum_val_phys),
            "sum_of_4_component_gaps_nat_minus_phys": float(sum_gap_nat_phys),
            "aux_sum_map_gap_nat_minus_phys": float(agg_aux_sum_eval["gap_nat_minus_phys"]),
            "primary_native_map_gap_nat_minus_phys": float(agg_native_eval["gap_nat_minus_phys"]),
            "algebraic_closure_error_aux_sum_minus_sum_of_4": float(agg_aux_sum_eval["gap_nat_minus_phys"] - sum_gap_nat_phys),
            "numeric_remainder_native_minus_sum_of_4": float(agg_native_eval["gap_nat_minus_phys"] - sum_gap_nat_phys),
            "n_positive_component_gaps": int(n_positive_gaps),
            "n_negative_component_gaps": int(n_negative_gaps),
            "sum_of_positive_component_gaps": float(sum(g for g in gaps_nat_phys if g > 0.0)),
            "sum_of_negative_component_gaps": float(sum(g for g in gaps_nat_phys if g < 0.0)),
            "largest_positive_gap_ref_j": max_pos_idx,
            "largest_positive_gap_value": float(gaps_nat_phys[max_pos_idx]),
            "most_negative_gap_ref_j": min_neg_idx,
            "most_negative_gap_value": float(gaps_nat_phys[min_neg_idx]),
        },
        "leave_one_reference_out_3of4_diagnostics": leave_one_ref_out,
    }


def main():
    t0 = time.perf_counter()
    index_bytes = (BUNDLE / "INDEX.json").read_bytes()
    assert sha256_bytes(index_bytes) == "5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3"
    manifest = json.loads((TRUTH_DIR / "MANIFEST.json").read_text())
    truth_file = TRUTH_DIR / "noisy_field.npy"
    assert sha256_bytes(truth_file.read_bytes()) == manifest["cases"]["noisy"]["files"]["noisy_field.npy"]
    truth = np.load(truth_file, allow_pickle=False)

    res_bad = analyze_patch(79, truth)
    res_central = analyze_patch(47, truth)

    out = {
        "plan_sha256": sha256_bytes((OUT_DIR / "PLAN.md").read_bytes()),
        "bundle_index_sha256": sha256_bytes(index_bytes),
        "truth_field_sha256": sha256_bytes(truth_file.read_bytes()),
        "capture_source_commit": "927a6890c8864f81ad58e44eac7281b080714af4",
        "python_executable": "/Users/alex.konstantinov/.local/bin/python3 -B",
        "numpy_version": np.__version__,
        "blas_omp_threads": {
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
            "VECLIB_MAXIMUM_THREADS": os.environ.get("VECLIB_MAXIMUM_THREADS"),
        },
        "global_certification_status": "UNPROVEN_GLOBAL",
        "patches": {
            "patch_62_79_bad": res_bad,
            "patch_62_47_central": res_central,
        },
        "elapsed_seconds": float(time.perf_counter() - t0),
    }

    res_path = OUT_DIR / "RESULT.json"
    res_path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({
        "patch_62_79_bad": res_bad["additive_closure_and_cancellation_summary"],
        "patch_62_47_central": res_central["additive_closure_and_cancellation_summary"],
        "elapsed_seconds": out["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
