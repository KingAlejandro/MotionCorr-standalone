#!/usr/bin/env python3
"""Independent read-only mathematical/statistical challenge for Native B2 (PR #287)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import numpy as np

ROOT = Path("/tmp/mc-b2-challenge-gemini4argon-20261026")
import sys
sys.path.insert(0, str(ROOT))
from motion_field import read_motion_star


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def spatial_row(u: float, v: float) -> np.ndarray:
    return np.array([1.0, u, u * u, v, v * v, u * v], dtype=np.float64)


def temporal_operators(N: int):
    """
    Construct exact temporal operators for N frames (g = 0..N-1).
    Pre-pin shift vector L has length N-1: L = [L_1, L_2, ..., L_{N-1}]^T (since L_0 = 0).
    Tr maps R^{N-1} -> R^N:
      obs_0 = 0.5 * L_1
      obs_g = L_g + 0.5 * L_1  for g = 1..N-1
    Also E_pin maps raw frame errors eps = [eps_0, eps_1, ..., eps_{N-1}]^T in R^N
    to L in R^{N-1} via L_g = eps_g - eps_0.
    """
    Tr = np.zeros((N, N - 1), dtype=np.float64)
    Tr[0, 0] = 0.5
    for g in range(1, N):
        Tr[g, 0] += 0.5
        Tr[g, g - 1] += 1.0

    E_pin = np.zeros((N - 1, N), dtype=np.float64)
    E_pin[:, 0] = -1.0
    E_pin[:, 1:] = np.eye(N - 1, dtype=np.float64)

    g = np.arange(N, dtype=np.float64)
    z_off = g + 0.5
    Z_OFF = np.column_stack([z_off, z_off**2, z_off**3])      # (N, 3)
    Z_B2 = np.column_stack([g, g**2, g**3])                   # (N, 3)
    Z_eval = Z_B2.copy()                                      # evaluated at f = 0..N-1

    M = np.eye(N, dtype=np.float64) - np.ones((N, N), dtype=np.float64) / N
    MZ_B2 = M @ Z_B2

    # Map from observation y in R^N to published trajectory h_hat in R^N (at f=0..N-1)
    H_OFF_obs = Z_eval @ np.linalg.pinv(Z_OFF)                # (N, N)
    H_B2_obs = Z_eval @ np.linalg.pinv(MZ_B2)                 # (N, N)

    # Map from pre-pin L in R^{N-1} to published trajectory h_hat in R^N
    K_OFF = H_OFF_obs @ Tr                                    # (N, N-1)
    K_B2 = H_B2_obs @ Tr                                      # (N, N-1)

    # Map from raw frame errors eps in R^N (before frame-0 pinning) to h_hat in R^N
    G_OFF_eps = K_OFF @ E_pin                                 # (N, N)
    G_B2_eps = K_B2 @ E_pin                                   # (N, N)

    # Residual projectors in observation space
    R_OFF_obs = np.eye(N) - Z_OFF @ np.linalg.pinv(Z_OFF)
    R_B2_obs = M - MZ_B2 @ np.linalg.pinv(MZ_B2)

    return {
        "Tr": Tr,
        "E_pin": E_pin,
        "Z_OFF": Z_OFF,
        "Z_B2": Z_B2,
        "MZ_B2": MZ_B2,
        "Z_eval": Z_eval,
        "H_OFF_obs": H_OFF_obs,
        "H_B2_obs": H_B2_obs,
        "K_OFF": K_OFF,
        "K_B2": K_B2,
        "G_OFF_eps": G_OFF_eps,
        "G_B2_eps": G_B2_eps,
        "R_OFF_obs": R_OFF_obs,
        "R_B2_obs": R_B2_obs,
    }


def eval_field_from_model(global_xy: np.ndarray, coeff_x: np.ndarray, coeff_y: np.ndarray, nx: int = 128, ny: int = 96, n_frames: int = 5) -> np.ndarray:
    """Evaluate dense (F, ny, nx, 2) displacement field in px."""
    iy, ix = np.mgrid[0:ny, 0:nx]
    u = ix / nx - 0.5
    v = iy / ny - 0.5
    S_grid = np.stack([np.ones_like(u), u, u * u, v, v * v, u * v], axis=0)  # (6, ny, nx)
    f = np.arange(n_frames, dtype=np.float64)
    T_grid = np.stack([f, f * f, f * f * f], axis=0)                         # (3, F)

    field = np.zeros((n_frames, ny, nx, 2), dtype=np.float64)
    for axis, coeff in ((0, coeff_x), (1, coeff_y)):
        C = coeff.reshape(6, 3)  # (6, 3)
        # local(f, y, x) = sum_{s,k} C[s,k] * T_grid[k, f] * S_grid[s, y, x]
        local = np.einsum("sk,kf,syx->fyx", C, T_grid, S_grid)
        field[:, :, :, axis] = local + global_xy[:, axis][:, None, None]
    return field


def largest_delta_check(coeff_x: np.ndarray, coeff_y: np.ndarray, nx: int = 128, ny: int = 96, n_frames: int = 5) -> float:
    """Exact replica of C++ ThirdOrderPolynomialModel corner neighbour delta check."""
    corners = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    dx, dy = 1.0 / nx, 1.0 / ny

    def get_shift(z: float, x: float, y: float):
        z2, z3 = z * z, z * z * z
        x2, y2, xy = x * x, y * y, x * y
        vec = np.array([
            z, z2, z3,
            x * z, x * z2, x * z3,
            x2 * z, x2 * z2, x2 * z3,
            y * z, y * z2, y * z3,
            y2 * z, y2 * z2, y2 * z3,
            xy * z, xy * z2, xy * z3,
        ], dtype=np.float64)
        return float(vec @ coeff_x), float(vec @ coeff_y)

    largest = 0.0
    for z in range(n_frames):
        for cx, cy in corners:
            x1, y1 = get_shift(z, cx, cy)
            x2, y2 = get_shift(z, cx + dx, cy)
            x3, y3 = get_shift(z, cx, cy + dy)
            largest = max(largest, abs(x2 - x1), abs(x3 - x1), abs(y2 - y1), abs(y3 - y1))
    return largest


def vector_metrics(err: np.ndarray):
    v = np.linalg.norm(err, axis=-1)
    return {
        "rms": float(np.sqrt(np.mean(v * v))),
        "p95": float(np.percentile(v, 95)),
        "max": float(v.max()),
    }


def main():
    out = {}

    # 1. Check Temporal Operators at N=5 and N=40
    t5 = temporal_operators(5)
    t40 = temporal_operators(40)

    # Check K_B2 vs K_OFF at N=5!
    # Wait: For any true polynomial h(f) = c1*f + c2*f^2 + c3*f^3 (which has L_g = h(g) for g=1..4),
    # K_B2 @ L_true == h(f) MUST BE EXACT!
    g5 = np.arange(5, dtype=np.float64)
    L_basis5 = np.column_stack([g5[1:], g5[1:]**2, g5[1:]**3]) # (4, 3)
    H_basis5 = np.column_stack([g5, g5**2, g5**3])             # (5, 3)

    # What is the 1D orthogonal complement of L_basis5 in R^4?
    # Since L_basis5 is [g, g^2, g^3] for g=1,2,3,4, any L in R^4 has a unique interpolation
    # by a degree-4 polynomial p(g) with p(0)=0: p(g) = a1 g + a2 g^2 + a3 g^3 + a4 g^4.
    # The ONLY vector orthogonal to span(L_basis5) is the 4th difference vector on g=1..4!
    # Wait: what does K_B2 do to ANY L in R^4 at N=5?!
    out["N5_operators"] = {
        "Tr": t5["Tr"].tolist(),
        "K_OFF": t5["K_OFF"].tolist(),
        "K_B2": t5["K_B2"].tolist(),
        "G_OFF_eps": t5["G_OFF_eps"].tolist(),
        "G_B2_eps": t5["G_B2_eps"].tolist(),
        "K_OFF_singular_values": np.linalg.svd(t5["K_OFF"], compute_uv=False).tolist(),
        "K_B2_singular_values": np.linalg.svd(t5["K_B2"], compute_uv=False).tolist(),
        "K_OFF_frobenius": float(np.linalg.norm(t5["K_OFF"], "fro")),
        "K_B2_frobenius": float(np.linalg.norm(t5["K_B2"], "fro")),
        "G_OFF_eps_frobenius": float(np.linalg.norm(t5["G_OFF_eps"], "fro")),
        "G_B2_eps_frobenius": float(np.linalg.norm(t5["G_B2_eps"], "fro")),
    }

    # Compare analytic noise transfer across N = 5, 9, 13, 20, 40
    # Model 1: Pre-pin raw frame noise eps_0..eps_{N-1} ~ iid(0, I_N), so L_g = eps_g - eps_0, Cov(L) = I_{N-1} + 1 1^T
    # Model 2: Independent increment noise L_1..L_{N-1} ~ iid(0, I_{N-1}) (i.e. eps_0 = 0)
    # Model 3: Constant shift error L = 1_{N-1} (i.e. pure frame-0 reference error eps_0 = -1, eps_{g>=1} = 0)
    n_comparison = {}
    for N in [5, 9, 13, 20, 40]:
        tn = temporal_operators(N)
        K_off = tn["K_OFF"]
        K_b2 = tn["K_B2"]
        G_off = tn["G_OFF_eps"]
        G_b2 = tn["G_B2_eps"]

        # Per-frame variance under iid raw frame noise eps ~ (0, I_N)
        var_f_off_eps = np.sum(G_off**2, axis=1)
        var_f_b2_eps = np.sum(G_b2**2, axis=1)

        # Per-frame variance under iid increment noise L ~ (0, I_{N-1})
        var_f_off_inc = np.sum(K_off**2, axis=1)
        var_f_b2_inc = np.sum(K_b2**2, axis=1)

        # Response to pure frame-0 error: eps = [1, 0, ..., 0]^T => L = -1_{N-1}
        resp_eps0_off = G_off[:, 0]
        resp_eps0_b2 = G_b2[:, 0]

        # Worst single-frame impulse amplification: max_{g>=1} ||K[:, g-1]||_rms and max_{f, g>=1} |K[f, g-1]|
        col_rms_off = np.sqrt(np.mean(K_off**2, axis=0))
        col_rms_b2 = np.sqrt(np.mean(K_b2**2, axis=0))
        col_max_off = np.max(np.abs(K_off), axis=0)
        col_max_b2 = np.max(np.abs(K_b2), axis=0)

        n_comparison[str(N)] = {
            "rms_factor_iid_eps_OFF": float(np.sqrt(np.mean(var_f_off_eps))),
            "rms_factor_iid_eps_B2": float(np.sqrt(np.mean(var_f_b2_eps))),
            "ratio_B2_over_OFF_iid_eps": float(np.sqrt(np.mean(var_f_b2_eps) / np.mean(var_f_off_eps))),
            "max_frame_sd_iid_eps_OFF": float(np.sqrt(np.max(var_f_off_eps))),
            "max_frame_sd_iid_eps_B2": float(np.sqrt(np.max(var_f_b2_eps))),
            "rms_factor_iid_L_OFF": float(np.sqrt(np.mean(var_f_off_inc))),
            "rms_factor_iid_L_B2": float(np.sqrt(np.mean(var_f_b2_inc))),
            "ratio_B2_over_OFF_iid_L": float(np.sqrt(np.mean(var_f_b2_inc) / np.mean(var_f_off_inc))),
            "max_frame_sd_iid_L_OFF": float(np.sqrt(np.max(var_f_off_inc))),
            "max_frame_sd_iid_L_B2": float(np.sqrt(np.max(var_f_b2_inc))),
            "eps0_only_rms_OFF": float(np.sqrt(np.mean(resp_eps0_off**2))),
            "eps0_only_rms_B2": float(np.sqrt(np.mean(resp_eps0_b2**2))),
            "max_impulse_rms_OFF": float(np.max(col_rms_off)),
            "max_impulse_rms_B2": float(np.max(col_rms_b2)),
            "max_impulse_linf_OFF": float(np.max(col_max_off)),
            "max_impulse_linf_B2": float(np.max(col_max_b2)),
        }
    out["analytic_N_comparison"] = n_comparison

    # 2. Load retained K267 noisy and affine data & truth
    truth_field = np.load(ROOT / "v2fixtures" / "noisy_field.npy", allow_pickle=False)  # (5, 96, 128, 2)
    roi = (12, 84, 12, 116)
    y0, y1, x0, x1 = roi
    sl = np.s_[y0:y1, x0:x1]
    px_size = 0.885

    rt_noisy_off = json.loads((ROOT / "OFF" / "runtime.json").read_text())
    rt_noisy_on = json.loads((ROOT / "ON-v3" / "runtime.json").read_text())
    star_noisy_off = read_motion_star(ROOT / "OFF" / "noisy.star")
    star_noisy_on = read_motion_star(ROOT / "ON-v3" / "noisy.star")

    rt_affine_off = json.loads((ROOT / "affine_OFF" / "runtime.json").read_text())
    rt_affine_on = json.loads((ROOT / "affine_ON" / "runtime.json").read_text())
    star_affine_off = read_motion_star(ROOT / "affine_OFF" / "affine.star")
    star_affine_on = read_motion_star(ROOT / "affine_ON" / "affine.star")

    # Extract 9x5 observation matrices Yx, Yy from STAR (identical in OFF and ON)
    patch_coords = [(20.0, 15.0), (62.0, 15.0), (104.0, 15.0),
                    (20.0, 47.0), (62.0, 47.0), (104.0, 47.0),
                    (20.0, 79.0), (62.0, 79.0), (104.0, 79.0)]
    nx, ny = 128, 96
    S_patch = np.array([spatial_row(x / nx - 0.5, y / ny - 0.5) for x, y in patch_coords], dtype=np.float64) # (9, 6)
    P_S = S_patch @ np.linalg.pinv(S_patch) # (9, 9)

    def extract_obs_matrix(star_obj):
        Yx = np.zeros((9, 5), dtype=np.float64)
        Yy = np.zeros((9, 5), dtype=np.float64)
        for idx, row in enumerate(star_obj.local_shifts):
            p = idx // 5
            g = idx % 5
            Yx[p, g] = row["rlnMicrographShiftX"]
            Yy[p, g] = row["rlnMicrographShiftY"]
        return Yx, Yy

    Yx_noisy, Yy_noisy = extract_obs_matrix(star_noisy_off)
    Yx_affine, Yy_affine = extract_obs_matrix(star_affine_off)

    # Check obs1 = 3 * obs0 identity and recover pre-pin L (9 x 4)
    # Note: L_{p,1} = 2 * obs_{p,0}, L_{p,g} = obs_{p,g} - obs_{p,0} for g=1..4
    def obs_to_prepin(Y):
        obs1_minus_3obs0 = np.max(np.abs(Y[:, 1] - 3.0 * Y[:, 0]))
        L = Y[:, 1:] - Y[:, [0]]
        return L, float(obs1_minus_3obs0)

    Lx_noisy, err_tr_x_noisy = obs_to_prepin(Yx_noisy)
    Ly_noisy, err_tr_y_noisy = obs_to_prepin(Yy_noisy)
    Lx_affine, err_tr_x_affine = obs_to_prepin(Yx_affine)
    Ly_affine, err_tr_y_affine = obs_to_prepin(Yy_affine)

    # Verify Kronecker formula vs Augmented 27-col SVD vs Native runtime.json
    S_pinv = np.linalg.pinv(S_patch)
    Z_OFF_pinv = np.linalg.pinv(t5["Z_OFF"])
    MZ_B2_pinv = np.linalg.pinv(t5["MZ_B2"])

    Cx_off_kron = (S_pinv @ Yx_noisy @ Z_OFF_pinv.T).ravel()
    Cy_off_kron = (S_pinv @ Yy_noisy @ Z_OFF_pinv.T).ravel()
    Cx_b2_kron = (S_pinv @ Yx_noisy @ MZ_B2_pinv.T).ravel()
    Cy_b2_kron = (S_pinv @ Yy_noisy @ MZ_B2_pinv.T).ravel()

    # Augmented 27-col SVD
    A_aug = np.hstack([np.kron(S_patch, t5["Z_B2"]), np.kron(np.eye(9), np.ones((5, 1)))])
    sol_aug_x = np.linalg.lstsq(A_aug, Yx_noisy.ravel(), rcond=None)[0]
    sol_aug_y = np.linalg.lstsq(A_aug, Yy_noisy.ravel(), rcond=None)[0]
    Cx_b2_aug, nuis_x_aug = sol_aug_x[:18], sol_aug_x[18:]
    Cy_b2_aug, nuis_y_aug = sol_aug_y[:18], sol_aug_y[18:]

    # Acceptance gates comparison (largest_delta and fit_rmsd)
    # In OFF: fit_rmsd is ||Y - (S C_off Z_OFF^T)||_F / sqrt(45)
    # In ON (B2): native computes residual WITH nuisance subtracted: ||M (Y - S C_b2 Z_B2^T)||_F / sqrt(45)
    # What if nuisance were NOT subtracted in B2? ||Y - S C_b2 Z_B2^T||_F / sqrt(45)
    fit_off_x = S_patch @ np.array(rt_noisy_off["coeff_x"]).reshape(6, 3) @ t5["Z_OFF"].T
    fit_off_y = S_patch @ np.array(rt_noisy_off["coeff_y"]).reshape(6, 3) @ t5["Z_OFF"].T
    rmsd_off_x = float(np.sqrt(np.mean((Yx_noisy - fit_off_x)**2)))
    rmsd_off_y = float(np.sqrt(np.mean((Yy_noisy - fit_off_y)**2)))

    fit_on_x = S_patch @ np.array(rt_noisy_on["coeff_x"]).reshape(6, 3) @ t5["Z_B2"].T
    fit_on_y = S_patch @ np.array(rt_noisy_on["coeff_y"]).reshape(6, 3) @ t5["Z_B2"].T
    nuis_on_x = np.mean(Yx_noisy - fit_on_x, axis=1, keepdims=True)
    nuis_on_y = np.mean(Yy_noisy - fit_on_y, axis=1, keepdims=True)
    rmsd_on_x_nuis = float(np.sqrt(np.mean((Yx_noisy - fit_on_x - nuis_on_x)**2)))
    rmsd_on_y_nuis = float(np.sqrt(np.mean((Yy_noisy - fit_on_y - nuis_on_y)**2)))
    rmsd_on_x_nonuis = float(np.sqrt(np.mean((Yx_noisy - fit_on_x)**2)))
    rmsd_on_y_nonuis = float(np.sqrt(np.mean((Yy_noisy - fit_on_y)**2)))

    out["solver_and_gates"] = {
        "obs1_minus_3obs0_max_px": max(err_tr_x_noisy, err_tr_y_noisy),
        "A_aug_shape": list(A_aug.shape),
        "A_aug_rank": int(np.linalg.matrix_rank(A_aug)),
        "A_aug_cond_raw": float(np.linalg.cond(A_aug)),
        "A_aug_cond_colscaled": float(np.linalg.cond(A_aug / np.linalg.norm(A_aug, axis=0, keepdims=True))),
        "S_patch_rank": int(np.linalg.matrix_rank(S_patch)),
        "S_patch_cond_colscaled": float(np.linalg.cond(S_patch / np.linalg.norm(S_patch, axis=0, keepdims=True))),
        "MZ_B2_cond_colscaled": float(np.linalg.cond(t5["MZ_B2"] / np.linalg.norm(t5["MZ_B2"], axis=0, keepdims=True))),
        "Z_OFF_cond_colscaled": float(np.linalg.cond(t5["Z_OFF"] / np.linalg.norm(t5["Z_OFF"], axis=0, keepdims=True))),
        "kron_vs_aug_max_coeff_diff": float(max(np.max(np.abs(Cx_b2_kron - Cx_b2_aug)), np.max(np.abs(Cy_b2_kron - Cy_b2_aug)))),
        "aug_vs_native_runtime_max_coeff_diff": float(max(np.max(np.abs(Cx_b2_aug - np.array(rt_noisy_on["coeff_x"]))),
                                                          np.max(np.abs(Cy_b2_aug - np.array(rt_noisy_on["coeff_y"]))))),
        "largest_delta_px_noisy_OFF": largest_delta_check(np.array(rt_noisy_off["coeff_x"]), np.array(rt_noisy_off["coeff_y"])),
        "largest_delta_px_noisy_ON": largest_delta_check(np.array(rt_noisy_on["coeff_x"]), np.array(rt_noisy_on["coeff_y"])),
        "largest_delta_px_affine_OFF": largest_delta_check(np.array(rt_affine_off["coeff_x"]), np.array(rt_affine_off["coeff_y"])),
        "largest_delta_px_affine_ON": largest_delta_check(np.array(rt_affine_on["coeff_x"]), np.array(rt_affine_on["coeff_y"])),
        "fit_rmsd_px_noisy_OFF": [rmsd_off_x, rmsd_off_y],
        "fit_rmsd_px_noisy_ON_nuisance_adjusted": [rmsd_on_x_nuis, rmsd_on_y_nuis],
        "fit_rmsd_px_noisy_ON_unadjusted": [rmsd_on_x_nonuis, rmsd_on_y_nonuis],
        "nuisance_x_px": nuis_x_aug.tolist(),
        "nuisance_y_px": nuis_y_aug.tolist(),
    }

    # 3. Exact Truth & Causal Decomposition of noisy and affine
    # Truth field is truth_field[f, y, x, axis].
    # Can truth_field be represented as g_true(f) + h_true(f, y, x) where h_true(0, y, x) = 0?
    # Note truth_field[0] == 0 everywhere.
    # Let's define the spatial-mean truth trajectory over the full micrograph (or at patch centers) and evaluate exact truth at patch centers!
    # Even better: what is the true motion formula in generate_motion_diagnostics.py for "affine"?
    # Let's check if truth_field is exact polynomial in (u, v, f)!
    iy, ix = np.mgrid[0:ny, 0:nx]
    u_grid = (ix / nx - 0.5).ravel()
    v_grid = (iy / ny - 0.5).ravel()
    S_dense = np.column_stack([np.ones_like(u_grid), u_grid, u_grid**2, v_grid, v_grid**2, u_grid * v_grid]) # (ny*nx, 6)
    # Project truth_field[f] onto S_dense for each frame f=0..4:
    # Wait: S_0 = 1 (at u=0, v=0, i.e. micrograph center) vs spatial average.
    # Notice that for ANY global trajectory G(f), total field is G(f) + local(f, u, v).
    # If local(f, u, v) = sum_{s=0..5} c_s(f) S_s(u, v), then G(f) is pure S_0 = 1!
    # Specifically, in truth_field, let's check if truth_field is ALREADY in span(S_dense) at every frame f!
    truth_S_coeffs_x = np.zeros((6, 5), dtype=np.float64)
    truth_S_coeffs_y = np.zeros((6, 5), dtype=np.float64)
    max_spatial_fit_err = 0.0
    for f in range(5):
        tx = truth_field[f, :, :, 0].ravel()
        ty = truth_field[f, :, :, 1].ravel()
        cx_f = np.linalg.lstsq(S_dense, tx, rcond=None)[0]
        cy_f = np.linalg.lstsq(S_dense, ty, rcond=None)[0]
        truth_S_coeffs_x[:, f] = cx_f
        truth_S_coeffs_y[:, f] = cy_f
        max_spatial_fit_err = max(max_spatial_fit_err,
                                  float(np.max(np.abs(tx - S_dense @ cx_f))),
                                  float(np.max(np.abs(ty - S_dense @ cy_f))))

    # Check if truth_S_coeffs[:, f] is cubic in f!
    # Fit truth_S_coeffs[:, 1:] on [f, f^2, f^3] for f=1..4:
    Z_eval_14 = t5["Z_eval"][1:, :] # (4, 3)
    P_cubic_14 = Z_eval_14 @ np.linalg.pinv(Z_eval_14) # (4, 4)
    truth_noncubic_x = truth_S_coeffs_x[:, 1:] @ (np.eye(4) - P_cubic_14).T
    truth_noncubic_y = truth_S_coeffs_y[:, 1:] @ (np.eye(4) - P_cubic_14).T

    out["truth_structure"] = {
        "max_spatial_quadratic_residual_px": max_spatial_fit_err,
        "truth_S_coeffs_x": truth_S_coeffs_x.tolist(),
        "truth_S_coeffs_y": truth_S_coeffs_y.tolist(),
        "truth_noncubic_x_max_px": float(np.max(np.abs(truth_noncubic_x))),
        "truth_noncubic_y_max_px": float(np.max(np.abs(truth_noncubic_y))),
    }

    # Now look at what ideal pre-pin patch shift L_ideal(p, g) would be if patch alignment were noiseless
    # Given the actual global trajectory G_actual(f) (which shifts each frame by G_actual before patch alignment):
    # At patch center (u_p, v_p), true displacement at frame g is T_true(p, g) = sum_s S_s(p) truth_S_coeffs[s, g].
    # After global alignment shifts frame g by G_actual(g), the residual true shift at patch center p is:
    #   L_ideal(p, g) = T_true(p, g) - G_actual(g)   for g = 1..4 (since at g=0 both are 0).
    # Then the actual pre-pin patch shift observed by alignPatch is:
    #   L_obs(p, g) = L_ideal(p, g) + eta(p, g)
    # where eta(p, g) is the patch alignment error at patch p, frame g!
    G_noisy = np.array(rt_noisy_off["global"], dtype=np.float64)   # (5, 2)
    G_affine = np.array(rt_affine_off["global"], dtype=np.float64) # (5, 2)

    T_true_patch_x = S_patch @ truth_S_coeffs_x # (9, 5)
    T_true_patch_y = S_patch @ truth_S_coeffs_y # (9, 5)

    L_ideal_noisy_x = T_true_patch_x[:, 1:] - G_noisy[None, 1:, 0] # (9, 4)
    L_ideal_noisy_y = T_true_patch_y[:, 1:] - G_noisy[None, 1:, 1] # (9, 4)
    eta_noisy_x = Lx_noisy - L_ideal_noisy_x                       # (9, 4)
    eta_noisy_y = Ly_noisy - L_ideal_noisy_y                       # (9, 4)

    L_ideal_affine_x = T_true_patch_x[:, 1:] - G_affine[None, 1:, 0]
    L_ideal_affine_y = T_true_patch_y[:, 1:] - G_affine[None, 1:, 1]
    eta_affine_x = Lx_affine - L_ideal_affine_x
    eta_affine_y = Ly_affine - L_ideal_affine_y

    out["patch_tracking_errors"] = {
        "Lx_noisy": Lx_noisy.tolist(),
        "Ly_noisy": Ly_noisy.tolist(),
        "L_ideal_noisy_x": L_ideal_noisy_x.tolist(),
        "L_ideal_noisy_y": L_ideal_noisy_y.tolist(),
        "eta_noisy_x": eta_noisy_x.tolist(),
        "eta_noisy_y": eta_noisy_y.tolist(),
        "eta_affine_x": eta_affine_x.tolist(),
        "eta_affine_y": eta_affine_y.tolist(),
        "eta_noisy_rms_px": float(np.sqrt(np.mean(eta_noisy_x**2 + eta_noisy_y**2))),
        "eta_affine_rms_px": float(np.sqrt(np.mean(eta_affine_x**2 + eta_affine_y**2))),
    }

    # Now let's derive the EXACT total field error formula in mode space!
    # For any estimator E in {OFF, B2} with temporal operator K_E in R^{5 x 4} (mapping L in R^{9x4} to local trajectories):
    # The fitted spatial-mode trajectories at frames f=0..4 are:
    #   H_hat_E = S_pinv @ L_obs @ K_E^T   in R^{6 x 5}
    # Since L_obs = S_patch @ truth_S_coeffs[:, 1:] - 1_9 @ G_actual[1:]^T + eta,
    # and S_pinv @ S_patch = I_6, while S_pinv @ 1_9 = e_0 = [1, 0, 0, 0, 0, 0]^T (because S[:, 0] == 1_9!),
    # we get the EXACT mode-by-mode identity:
    #   H_hat_E = (truth_S_coeffs[:, 1:] - e_0 @ G_actual[1:]^T) @ K_E^T + (S_pinv @ eta) @ K_E^T !
    # And the TOTAL published field (global + local) in spatial-mode coordinates is:
    #   F_hat_E = e_0 @ G_actual^T + H_hat_E
    # Therefore, the EXACT field error Delta_F_E = F_hat_E - truth_S_coeffs in R^{6 x 5} decomposes into THREE EXACT ADDITIVE TERMS:
    #   Term 1 (True motion temporal distortion):
    #     E_true = truth_S_coeffs[:, 1:] @ K_E^T - truth_S_coeffs
    #   Term 2 (Unabsorbed global error on S_0 = 1):
    #     E_global = e_0 @ (G_actual - [0, G_actual[1:] @ K_E^T])
    #     Wait: if we split truth_S_coeffs[0, :] (true S_0 mode) and G_actual:
    #     Let dG = G_actual - truth_S_coeffs[0, :] (the global shift error relative to the center-pixel truth S_0).
    #     Then on mode s=0, the combined (True S_0 + Global) error is:
    #       truth_S_coeffs[0, 1:] @ (K_E^T - I) + dG - dG[1:] @ K_E^T = (truth_S_coeffs[0, 1:] - dG[1:]) @ (K_E^T - I) !
    #   Term 3 (Stochastic patch CCF error projection):
    #     E_patch = (S_pinv @ eta) @ K_E^T

    def evaluate_from_L(G_act, Lx, Ly, mode: str):
        K = t5["K_OFF"] if mode == "OFF" else t5["K_B2"]
        # Wait: C = S_pinv @ Y @ Z_pinv^T, so C @ Z_eval^T = S_pinv @ L @ K^T
        Z_pinv = Z_OFF_pinv if mode == "OFF" else MZ_B2_pinv
        Y_x = Lx @ t5["Tr"].T
        Y_y = Ly @ t5["Tr"].T
        cx = (S_pinv @ Y_x @ Z_pinv.T).ravel()
        cy = (S_pinv @ Y_y @ Z_pinv.T).ravel()
        field = eval_field_from_model(G_act, cx, cy)
        err = field - truth_field
        inner = err[:, y0:y1, x0:x1]
        border_mask = np.ones((ny, nx), dtype=bool)
        border_mask[sl] = False
        return {
            "roi_A": vector_metrics(inner * px_size),
            "roi_px": vector_metrics(inner),
            "border_px": vector_metrics(err[:, border_mask]),
            "global_mean_px": vector_metrics(inner.mean(axis=(1, 2))),
            "local_px": vector_metrics(inner - inner.mean(axis=(1, 2), keepdims=True)),
            "per_frame_roi_A": [vector_metrics(inner[f] * px_size) for f in range(5)],
            "err_field": err,
        }

    # Verify our evaluate_from_L reproduces native runtime metrics to machine precision
    res_noisy_off = evaluate_from_L(G_noisy, Lx_noisy, Ly_noisy, "OFF")
    res_noisy_on = evaluate_from_L(G_noisy, Lx_noisy, Ly_noisy, "B2")
    res_affine_off = evaluate_from_L(G_affine, Lx_affine, Ly_affine, "OFF")
    res_affine_on = evaluate_from_L(G_affine, Lx_affine, Ly_affine, "B2")

    # Counterfactual 1: Ideal noiseless patch shifts on top of ACTUAL noisy global G_noisy (i.e. eta = 0, testing unabsorbed non-cubic G_noisy error alone!)
    res_noisyG_idealL_off = evaluate_from_L(G_noisy, L_ideal_noisy_x, L_ideal_noisy_y, "OFF")
    res_noisyG_idealL_on = evaluate_from_L(G_noisy, L_ideal_noisy_x, L_ideal_noisy_y, "B2")

    # Counterfactual 2: Pure stochastic patch error eta alone (i.e. G = truth, L = eta, truth = 0)
    def evaluate_pure_eta(eta_x, eta_y, mode: str):
        Z_pinv = Z_OFF_pinv if mode == "OFF" else MZ_B2_pinv
        Y_x = eta_x @ t5["Tr"].T
        Y_y = eta_y @ t5["Tr"].T
        cx = (S_pinv @ Y_x @ Z_pinv.T).ravel()
        cy = (S_pinv @ Y_y @ Z_pinv.T).ravel()
        err = eval_field_from_model(np.zeros((5, 2)), cx, cy)
        inner = err[:, y0:y1, x0:x1]
        border_mask = np.ones((ny, nx), dtype=bool)
        border_mask[sl] = False
        return {
            "roi_A": vector_metrics(inner * px_size),
            "roi_px": vector_metrics(inner),
            "border_px": vector_metrics(err[:, border_mask]),
            "global_mean_px": vector_metrics(inner.mean(axis=(1, 2))),
            "local_px": vector_metrics(inner - inner.mean(axis=(1, 2), keepdims=True)),
            "per_frame_roi_A": [vector_metrics(inner[f] * px_size) for f in range(5)],
            "err_field": err,
        }

    res_pure_eta_noisy_off = evaluate_pure_eta(eta_noisy_x, eta_noisy_y, "OFF")
    res_pure_eta_noisy_on = evaluate_pure_eta(eta_noisy_x, eta_noisy_y, "B2")

    # Counterfactual 3: Identify the 3 catastrophic CCF false-peak outliers in L_noisy / eta_noisy:
    # Patch 4 (0-indexed, i.e. patch (2,2) center 62,47), g=2 (frame 3): obs = (12.07381, -7.72677)
    # Patch 5 (0-indexed, i.e. patch (2,3) center 104,47), g=4 (frame 5): obs = (-18.11667, 15.337478)
    # Patch 7 (0-indexed, i.e. patch (3,2) center 62,79), g=4 (frame 5): obs = (10.517857, -10.04464)
    outlier_entries = [(4, 1), (5, 3), (7, 3)]  # (patch_idx 0..8, col_idx in L 0..3 corresponding to g=1..4)
    eta_outliers_only_x = np.zeros_like(eta_noisy_x)
    eta_outliers_only_y = np.zeros_like(eta_noisy_y)
    for p_idx, l_idx in outlier_entries:
        eta_outliers_only_x[p_idx, l_idx] = eta_noisy_x[p_idx, l_idx]
        eta_outliers_only_y[p_idx, l_idx] = eta_noisy_y[p_idx, l_idx]

    eta_without_outliers_x = eta_noisy_x - eta_outliers_only_x
    eta_without_outliers_y = eta_noisy_y - eta_outliers_only_y

    res_outliers_only_off = evaluate_pure_eta(eta_outliers_only_x, eta_outliers_only_y, "OFF")
    res_outliers_only_on = evaluate_pure_eta(eta_outliers_only_x, eta_outliers_only_y, "B2")

    res_no_outliers_full_off = evaluate_from_L(G_noisy, L_ideal_noisy_x + eta_without_outliers_x, L_ideal_noisy_y + eta_without_outliers_y, "OFF")
    res_no_outliers_full_on = evaluate_from_L(G_noisy, L_ideal_noisy_x + eta_without_outliers_x, L_ideal_noisy_y + eta_without_outliers_y, "B2")

    def strip_err(d):
        return {k: v for k, v in d.items() if k != "err_field"}

    # Check exact inner-product cross terms in ROI mean-square error:
    # err_total = err_idealL + err_eta
    err_ideal_off = res_noisyG_idealL_off["err_field"][:, y0:y1, x0:x1] * px_size
    err_eta_off = res_pure_eta_noisy_off["err_field"][:, y0:y1, x0:x1] * px_size
    err_ideal_on = res_noisyG_idealL_on["err_field"][:, y0:y1, x0:x1] * px_size
    err_eta_on = res_pure_eta_noisy_on["err_field"][:, y0:y1, x0:x1] * px_size

    ms_ideal_off = float(np.mean(np.sum(err_ideal_off**2, axis=-1)))
    ms_eta_off = float(np.mean(np.sum(err_eta_off**2, axis=-1)))
    ms_cross_off = float(2.0 * np.mean(np.sum(err_ideal_off * err_eta_off, axis=-1)))
    ms_total_off = float(np.mean(np.sum((err_ideal_off + err_eta_off)**2, axis=-1)))

    ms_ideal_on = float(np.mean(np.sum(err_ideal_on**2, axis=-1)))
    ms_eta_on = float(np.mean(np.sum(err_eta_on**2, axis=-1)))
    ms_cross_on = float(2.0 * np.mean(np.sum(err_ideal_on * err_eta_on, axis=-1)))
    ms_total_on = float(np.mean(np.sum((err_ideal_on + err_eta_on)**2, axis=-1)))

    out["causal_decomposition"] = {
        "actual_noisy_OFF": strip_err(res_noisy_off),
        "actual_noisy_ON": strip_err(res_noisy_on),
        "actual_affine_OFF": strip_err(res_affine_off),
        "actual_affine_ON": strip_err(res_affine_on),
        "noisyG_with_noiseless_L_OFF": strip_err(res_noisyG_idealL_off),
        "noisyG_with_noiseless_L_ON": strip_err(res_noisyG_idealL_on),
        "pure_patch_noise_eta_OFF": strip_err(res_pure_eta_noisy_off),
        "pure_patch_noise_eta_ON": strip_err(res_pure_eta_noisy_on),
        "three_outliers_only_OFF": strip_err(res_outliers_only_off),
        "three_outliers_only_ON": strip_err(res_outliers_only_on),
        "noisy_with_3_outliers_removed_OFF": strip_err(res_no_outliers_full_off),
        "noisy_with_3_outliers_removed_ON": strip_err(res_no_outliers_full_on),
        "ms_decomposition_A2_OFF": {
            "ideal_L_plus_G_ms": ms_ideal_off,
            "ideal_L_plus_G_rms": float(np.sqrt(ms_ideal_off)),
            "pure_eta_ms": ms_eta_off,
            "pure_eta_rms": float(np.sqrt(ms_eta_off)),
            "cross_term_2ab": ms_cross_off,
            "total_ms": ms_total_off,
            "total_rms": float(np.sqrt(ms_total_off)),
        },
        "ms_decomposition_A2_ON": {
            "ideal_L_plus_G_ms": ms_ideal_on,
            "ideal_L_plus_G_rms": float(np.sqrt(ms_ideal_on)),
            "pure_eta_ms": ms_eta_on,
            "pure_eta_rms": float(np.sqrt(ms_eta_on)),
            "cross_term_2ab": ms_cross_on,
            "total_ms": ms_total_on,
            "total_rms": float(np.sqrt(ms_total_on)),
        },
    }

    # 4. Inspect where max error occurs in ROI and on Border for noisy OFF and ON
    err_off_roi = res_noisy_off["err_field"][:, y0:y1, x0:x1] * px_size
    err_on_roi = res_noisy_on["err_field"][:, y0:y1, x0:x1] * px_size
    v_off_roi = np.linalg.norm(err_off_roi, axis=-1)
    v_on_roi = np.linalg.norm(err_on_roi, axis=-1)
    idx_max_off_roi = np.unravel_index(np.argmax(v_off_roi), v_off_roi.shape)
    idx_max_on_roi = np.unravel_index(np.argmax(v_on_roi), v_on_roi.shape)

    v_off_full = np.linalg.norm(res_noisy_off["err_field"], axis=-1)
    v_on_full = np.linalg.norm(res_noisy_on["err_field"], axis=-1)
    idx_max_off_full = np.unravel_index(np.argmax(v_off_full), v_off_full.shape)
    idx_max_on_full = np.unravel_index(np.argmax(v_on_full), v_on_full.shape)

    out["spatiotemporal_max_locations"] = {
        "ROI_max_OFF": {
            "frame_0based": int(idx_max_off_roi[0]),
            "y": int(idx_max_off_roi[1] + y0),
            "x": int(idx_max_off_roi[2] + x0),
            "val_A": float(v_off_roi[idx_max_off_roi]),
            "val_px": float(v_off_roi[idx_max_off_roi] / px_size),
        },
        "ROI_max_ON": {
            "frame_0based": int(idx_max_on_roi[0]),
            "y": int(idx_max_on_roi[1] + y0),
            "x": int(idx_max_on_roi[2] + x0),
            "val_A": float(v_on_roi[idx_max_on_roi]),
            "val_px": float(v_on_roi[idx_max_on_roi] / px_size),
        },
        "full_grid_max_OFF": {
            "frame_0based": int(idx_max_off_full[0]),
            "y": int(idx_max_off_full[1]),
            "x": int(idx_max_off_full[2]),
            "val_px": float(v_off_full[idx_max_off_full]),
            "val_A": float(v_off_full[idx_max_off_full] * px_size),
        },
        "full_grid_max_ON": {
            "frame_0based": int(idx_max_on_full[0]),
            "y": int(idx_max_on_full[1]),
            "x": int(idx_max_on_full[2]),
            "val_px": float(v_on_full[idx_max_on_full]),
            "val_A": float(v_on_full[idx_max_on_full] * px_size),
        },
    }

    # 5. Spatial Leverage & Extrapolation Amplification from 3x3 patches to ROI & Full Grid
    S_roi = np.stack([
        np.ones((y1 - y0, x1 - x0)),
        (ix[y0:y1, x0:x1] / nx - 0.5),
        (ix[y0:y1, x0:x1] / nx - 0.5)**2,
        (iy[y0:y1, x0:x1] / ny - 0.5),
        (iy[y0:y1, x0:x1] / ny - 0.5)**2,
        (ix[y0:y1, x0:x1] / nx - 0.5) * (iy[y0:y1, x0:x1] / ny - 0.5),
    ], axis=-1).reshape(-1, 6) # (n_roi, 6)

    M_spatial_roi = S_roi @ S_pinv # (n_roi, 9)
    M_spatial_full = S_dense @ S_pinv # (ny*nx, 9)

    out["spatial_leverage"] = {
        "patch_hat_diag_P_S": np.diag(P_S).tolist(),
        "patch_rms_weight_in_ROI": np.sqrt(np.mean(M_spatial_roi**2, axis=0)).tolist(),
        "patch_max_weight_in_ROI": np.max(np.abs(M_spatial_roi), axis=0).tolist(),
        "patch_max_weight_in_full_grid": np.max(np.abs(M_spatial_full), axis=0).tolist(),
        "total_spatial_variance_factor_ROI": float(np.mean(np.sum(M_spatial_roi**2, axis=1))),
        "max_spatial_variance_factor_ROI": float(np.max(np.sum(M_spatial_roi**2, axis=1))),
        "max_spatial_variance_factor_full": float(np.max(np.sum(M_spatial_full**2, axis=1))),
    }

    out_path = ROOT / "challenge_results.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
