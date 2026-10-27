#!/usr/bin/env python3
"""Verify and challenge operator gains (raw obs vs Tr-constrained L vs pre-pin eps) and N40 geometry."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

ROOT = Path("/tmp/mc-b2-challenge-gemini4argon-20261026")
import sys
sys.path.insert(0, str(ROOT))
from run_challenge_analysis import temporal_operators, spatial_row

def analyze_gains(N: int, nx: int, ny: int, patch_coords, roi):
    tn = temporal_operators(N)
    S_patch = np.array([spatial_row(x / nx - 0.5, y / ny - 0.5) for x, y in patch_coords], dtype=np.float64)
    S_pinv = np.linalg.pinv(S_patch)

    iy, ix = np.mgrid[0:ny, 0:nx]
    u = ix / nx - 0.5
    v = iy / ny - 0.5
    S_full = np.stack([np.ones_like(u), u, u*u, v, v*v, u*v], axis=-1).reshape(-1, 6)
    y0, y1, x0, x1 = roi
    S_roi = np.stack([np.ones((y1-y0, x1-x0)), u[y0:y1, x0:x1], u[y0:y1, x0:x1]**2,
                      v[y0:y1, x0:x1], v[y0:y1, x0:x1]**2, u[y0:y1, x0:x1]*v[y0:y1, x0:x1]], axis=-1).reshape(-1, 6)

    M_sp_full = S_full @ S_pinv
    M_sp_roi = S_roi @ S_pinv
    sp_row_l2_full = np.linalg.norm(M_sp_full, axis=1) # (ny*nx,)
    sp_row_l2_roi = np.linalg.norm(M_sp_roi, axis=1)   # (n_roi,)

    # Note: because the full operator is a Kronecker product M_spatial \otimes M_temporal,
    # the row-L2 norm at pixel p and frame f is simply:
    #   ||row(p, f)||_2 = ||M_spatial[p, :]||_2 * ||M_temporal[f, :]||_2 !
    res = {}
    for arm, H_obs, K_L, G_eps in [
        ("OFF", tn["H_OFF_obs"], tn["K_OFF"], tn["G_OFF_eps"]),
        ("B2",  tn["H_B2_obs"],  tn["K_B2"],  tn["G_B2_eps"]),
    ]:
        t_l2_obs = np.linalg.norm(H_obs, axis=1)   # (N,) - assumes iid raw obs y (violates y1=3y0)
        t_l2_L   = np.linalg.norm(K_L, axis=1)     # (N,) - assumes iid pre-pin L_1..L_{N-1}
        t_l2_eps = np.linalg.norm(G_eps, axis=1)   # (N,) - assumes iid pre-pin frame errors eps_0..eps_{N-1}
        t_linf_L = np.max(np.abs(K_L), axis=1)     # (N,) - max single-frame impulse response in L

        res[arm] = {
            "temporal_row_L2_raw_obs_per_frame": t_l2_obs.tolist(),
            "temporal_row_L2_prepin_L_per_frame": t_l2_L.tolist(),
            "temporal_row_L2_prepin_eps_per_frame": t_l2_eps.tolist(),
            "temporal_max_abs_prepin_L_per_frame": t_linf_L.tolist(),
            # Max row-L2 on Full Border:
            "max_border_row_L2_raw_obs": float(sp_row_l2_full.max() * t_l2_obs.max()),
            "max_border_row_L2_prepin_L": float(sp_row_l2_full.max() * t_l2_L.max()),
            "max_border_row_L2_prepin_eps": float(sp_row_l2_full.max() * t_l2_eps.max()),
            # Max row-L2 in ROI:
            "max_ROI_row_L2_raw_obs": float(sp_row_l2_roi.max() * t_l2_obs.max()),
            "max_ROI_row_L2_prepin_L": float(sp_row_l2_roi.max() * t_l2_L.max()),
            "max_ROI_row_L2_prepin_eps": float(sp_row_l2_roi.max() * t_l2_eps.max()),
            # RMS row-L2 in ROI (root mean square over all f=0..N-1 and ROI pixels):
            "rms_ROI_row_L2_raw_obs": float(np.sqrt(np.mean(sp_row_l2_roi**2) * np.mean(t_l2_obs**2))),
            "rms_ROI_row_L2_prepin_L": float(np.sqrt(np.mean(sp_row_l2_roi**2) * np.mean(t_l2_L**2))),
            "rms_ROI_row_L2_prepin_eps": float(np.sqrt(np.mean(sp_row_l2_roi**2) * np.mean(t_l2_eps**2))),
        }
    return res

def main():
    # N=5 K267 3x3 geometry
    coords_k267 = [(20.0, 15.0), (62.0, 15.0), (104.0, 15.0),
                   (20.0, 47.0), (62.0, 47.0), (104.0, 47.0),
                   (20.0, 79.0), (62.0, 79.0), (104.0, 79.0)]
    roi_k267 = (12, 84, 12, 116)

    # Also check N=40 with the SAME 3x3 K267 geometry, and with the 5x5 W8 4096^2 geometry!
    # In 4096^2 with 5x5 patches: patch size is 4096//5 = 819, centers at 409, 1228, 2047, 2866, 3685
    centers_4096 = [i * (4096 // 5) + (4096 // 5) // 2 - 1 for i in range(5)]
    coords_4096 = [(float(x), float(y)) for y in centers_4096 for x in centers_4096]
    roi_4096 = (256, 3840, 256, 3840)

    out = {
        "K267_3x3_N5": analyze_gains(5, 128, 96, coords_k267, roi_k267),
        "K267_3x3_N40": analyze_gains(40, 128, 96, coords_k267, roi_k267),
    }

    # Also compute exact H_B2_obs at N=5 to show why raw_obs L2 is inflated by ignoring Tr
    t5 = temporal_operators(5)
    out["H_B2_obs_N5"] = t5["H_B2_obs"].tolist()
    out["H_OFF_obs_N5"] = t5["H_OFF_obs"].tolist()

    # Check author's tiny_challenge.json decomposition vs ours
    tc = json.loads(Path("/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9ee0a2b/docs/post_rc0/s1/native_b2_20261026/tiny_challenge.json").read_text())
    out["author_tiny_challenge_noisy_summary"] = {
        arm: {
            "operator_max_row_L1": tc["cases"]["noisy"]["arms"][arm]["operator_max_row_L1"],
            "operator_max_row_L2": tc["cases"]["noisy"]["arms"][arm]["operator_max_row_L2"],
            "perfect_obs_ROI_A": tc["cases"]["noisy"]["arms"][arm]["perfect_observation_projection_error"]["ROI"]["angstrom"],
            "discrepancy_ROI_A": tc["cases"]["noisy"]["arms"][arm]["propagated_observation_discrepancy"]["ROI"]["angstrom"],
            "unabsorbed_global_ROI_A": tc["cases"]["noisy"]["arms"][arm]["unabsorbed_global_error"]["ROI"]["angstrom"],
            "true_global_perfect_obs_ROI_A": tc["cases"]["noisy"]["arms"][arm]["true_global_perfect_observation_error"]["ROI"]["angstrom"],
        }
        for arm in ("OFF", "ON")
    }

    (ROOT / "operator_gain_challenge.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
