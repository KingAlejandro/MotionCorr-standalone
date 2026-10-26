#!/usr/bin/env python3
"""Compute affine MS decomposition and verify all artifact SHA-256 hashes."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np

ROOT = Path("/tmp/mc-b2-challenge-gemini4argon-20261026")
import sys
sys.path.insert(0, str(ROOT))
from run_challenge_analysis import temporal_operators, spatial_row, eval_field_from_model, vector_metrics
from motion_field import read_motion_star

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    t5 = temporal_operators(5)
    truth_field = np.load(ROOT / "v2fixtures" / "affine_field.npy", allow_pickle=False)
    roi = (12, 84, 12, 116)
    y0, y1, x0, x1 = roi
    px_size = 0.885
    nx, ny = 128, 96
    patch_coords = [(20.0, 15.0), (62.0, 15.0), (104.0, 15.0),
                    (20.0, 47.0), (62.0, 47.0), (104.0, 47.0),
                    (20.0, 79.0), (62.0, 79.0), (104.0, 79.0)]
    S_patch = np.array([spatial_row(x / nx - 0.5, y / ny - 0.5) for x, y in patch_coords], dtype=np.float64)
    S_pinv = np.linalg.pinv(S_patch)
    Z_OFF_pinv = np.linalg.pinv(t5["Z_OFF"])
    MZ_B2_pinv = np.linalg.pinv(t5["MZ_B2"])

    rt_aff_off = json.loads((ROOT / "affine_OFF" / "runtime.json").read_text())
    rt_aff_on = json.loads((ROOT / "affine_ON" / "runtime.json").read_text())
    star_aff_off = read_motion_star(ROOT / "affine_OFF" / "affine.star")
    G_aff = np.array(rt_aff_off["global"], dtype=np.float64)

    Yx = np.zeros((9, 5), dtype=np.float64)
    Yy = np.zeros((9, 5), dtype=np.float64)
    for idx, row in enumerate(star_aff_off.local_shifts):
        Yx[idx // 5, idx % 5] = row["rlnMicrographShiftX"]
        Yy[idx // 5, idx % 5] = row["rlnMicrographShiftY"]
    Lx = Yx[:, 1:] - Yx[:, [0]]
    Ly = Yy[:, 1:] - Yy[:, [0]]

    # Ideal L at patch centers
    T_true_x = np.array([truth_field[:, int(y), int(x), 0] for x, y in patch_coords])
    T_true_y = np.array([truth_field[:, int(y), int(x), 1] for x, y in patch_coords])
    L_ideal_x = T_true_x[:, 1:] - G_aff[None, 1:, 0]
    L_ideal_y = T_true_y[:, 1:] - G_aff[None, 1:, 1]
    eta_x = Lx - L_ideal_x
    eta_y = Ly - L_ideal_y

    out = {}
    for label, Z_pinv in [("OFF", Z_OFF_pinv), ("ON", MZ_B2_pinv)]:
        cx_id = (S_pinv @ (L_ideal_x @ t5["Tr"].T) @ Z_pinv.T).ravel()
        cy_id = (S_pinv @ (L_ideal_y @ t5["Tr"].T) @ Z_pinv.T).ravel()
        err_id = (eval_field_from_model(G_aff, cx_id, cy_id) - truth_field)[:, y0:y1, x0:x1] * px_size

        cx_eta = (S_pinv @ (eta_x @ t5["Tr"].T) @ Z_pinv.T).ravel()
        cy_eta = (S_pinv @ (eta_y @ t5["Tr"].T) @ Z_pinv.T).ravel()
        err_eta = eval_field_from_model(np.zeros((5, 2)), cx_eta, cy_eta)[:, y0:y1, x0:x1] * px_size

        err_tot = err_id + err_eta
        ms_id = float(np.mean(np.sum(err_id**2, axis=-1)))
        ms_eta = float(np.mean(np.sum(err_eta**2, axis=-1)))
        ms_cross = float(2.0 * np.mean(np.sum(err_id * err_eta, axis=-1)))
        ms_tot = float(np.mean(np.sum(err_tot**2, axis=-1)))
        out[label] = {
            "ideal_L_plus_G_A": vector_metrics(err_id),
            "pure_eta_A": vector_metrics(err_eta),
            "total_A": vector_metrics(err_tot),
            "ms_id": ms_id,
            "ms_eta": ms_eta,
            "ms_cross": ms_cross,
            "ms_tot": ms_tot,
        }

    # Also compute W8 5x5 4096^2 spatial + temporal noise transfer at N=5 vs N=40 for direct comparison
    centers_4096 = [409.0, 1228.0, 2047.0, 2866.0, 3685.0]
    coords_4096 = [(x, y) for y in centers_4096 for x in centers_4096]
    S_25 = np.array([spatial_row(x / 4096.0 - 0.5, y / 4096.0 - 0.5) for x, y in coords_4096], dtype=np.float64)
    S_25_pinv = np.linalg.pinv(S_25)
    # Sample ROI [256, 3840) on 64x64 grid for exact polynomial integral
    gy, gx = np.mgrid[256:3840:16, 256:3840:16]
    u4, v4 = gx / 4096.0 - 0.5, gy / 4096.0 - 0.5
    S_roi4 = np.stack([np.ones_like(u4), u4, u4**2, v4, v4**2, u4*v4], axis=-1).reshape(-1, 6)
    M_sp_25_roi = S_roi4 @ S_25_pinv
    sp25_rms = float(np.sqrt(np.mean(np.sum(M_sp_25_roi**2, axis=1))))
    sp25_max = float(np.max(np.linalg.norm(M_sp_25_roi, axis=1)))

    out["spatial_5x5_4096_ROI"] = {
        "rms_spatial_factor": sp25_rms,
        "max_spatial_factor": sp25_max,
    }

    (ROOT / "affine_and_spatial_check.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
