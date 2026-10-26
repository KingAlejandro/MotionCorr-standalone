#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent mathematical/statistical verification and challenge of W5 Round 2 E1."""
import json
from pathlib import Path
import sys
import numpy as np

WT = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c3dca0d')
W5 = WT / 'docs/post_rc0/s1/first_divergence_20261022/w5_intervention_20261025'
R2 = W5 / 'round2'
OUT_DIR = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/E1-damping-challenge')

sys.path.insert(0, str(R2 / 'scripts'))
import lib as L
import common as C


def load_saved():
    char = json.loads((R2 / 'results/e1-characterization.json').read_text())
    inter = json.loads((R2 / 'results/e1-intervention.json').read_text())
    return char, inter


def analytical_peak_operator(target, nx=128, ny=96, weight='prod'):
    """Derive exact discrete-stencil and continuous-Hessian linear response A at truth."""
    e = L.Estimator(nx=nx, ny=ny, weight=weight)
    Ft = np.fft.fft2(target.astype(float)) / (nx * ny)
    S = (np.abs(Ft) ** 2) * e.W
    kx = e.kx[None, :] / nx
    ky = e.ky[:, None] / ny

    # Exact discrete stencil on C(dx, dy) = mean_k S(k) cos(2*pi*(kx*(dx+Delta_x) + ky*(dy+Delta_y)))
    Dxx = float(np.mean(S * (2.0 * np.cos(2.0 * np.pi * kx) - 2.0)))
    Dyy = float(np.mean(S * (2.0 * np.cos(2.0 * np.pi * ky) - 2.0)))
    Dxy = float(-np.mean(S * np.sin(2.0 * np.pi * kx) * np.sin(2.0 * np.pi * ky)))

    Gxx = float(np.mean(S * (-2.0 * np.pi * kx) * np.sin(2.0 * np.pi * kx)))
    Gxy = float(np.mean(S * (-2.0 * np.pi * ky) * np.sin(2.0 * np.pi * kx)))
    Gyx = float(np.mean(S * (-2.0 * np.pi * kx) * np.sin(2.0 * np.pi * ky)))
    Gyy = float(np.mean(S * (-2.0 * np.pi * ky) * np.sin(2.0 * np.pi * ky)))

    G = np.array([[Gxx, Gxy], [Gyx, Gyy]])
    D_diag = np.diag([Dxx, Dyy])
    H_2d_stencil = np.array([[Dxx, Dxy], [Dxy, Dyy]])

    # Separable 1D parabola response matrix A: u_raw = A @ Delta
    A_sep = -np.linalg.inv(D_diag) @ G
    # Full 2D quadratic stencil response matrix A_2d: u_raw = A_2d @ Delta
    A_2d = -np.linalg.inv(H_2d_stencil) @ G

    # Continuous-derivative Hessian H_cont
    Hxx_c = float(np.mean(S * (-((2.0 * np.pi * kx) ** 2))))
    Hyy_c = float(np.mean(S * (-((2.0 * np.pi * ky) ** 2))))
    Hxy_c = float(np.mean(S * (-(2.0 * np.pi * kx) * (2.0 * np.pi * ky))))
    A_cont = -np.array([[1.0, Hxy_c / Hxx_c], [Hxy_c / Hyy_c, 1.0]])

    d_bar = 0.5 * (Gxx / Dxx + Gyy / Dyy)
    rho_xy = float(np.sqrt((Gxy / Dxx) * (Gyx / Dyy)))
    mu_sep = np.sort(np.linalg.eigvals(A_sep).real)
    mu_2d = np.sort(np.linalg.eigvals(A_2d).real)
    mu_cont = np.sort(np.linalg.eigvals(A_cont).real)

    return dict(
        weight=weight,
        Dxx=Dxx, Dyy=Dyy, Dxy=Dxy,
        G=G.tolist(),
        d_bar=float(d_bar),
        rho_xy=rho_xy,
        A_sep=A_sep.tolist(),
        mu_sep=mu_sep.tolist(),
        A_2d=A_2d.tolist(),
        mu_2d=mu_2d.tolist(),
        A_cont=A_cont.tolist(),
        mu_cont=mu_cont.tolist(),
    )


def stability_table(op_info, Ns=(3, 5, 9, 13, 20)):
    A = np.array(op_info['A_sep'])
    mu_minus, mu_plus = op_info['mu_sep']
    rows = []
    for N in Ns:
        loo_factor = N / (N - 1.0)
        eta_minus = loo_factor * mu_minus
        eta_plus = loo_factor * mu_plus
        g_max = -2.0 / eta_minus
        g_loo = (N - 1.0) / N
        g_opt = g_loo / op_info['d_bar']
        g_zero_fast = -1.0 / eta_minus
        rows.append(dict(
            N=N,
            loo_factor=loo_factor,
            eta_minus=float(eta_minus),
            eta_plus=float(eta_plus),
            g_max=float(g_max),
            g_loo=float(g_loo),
            g_opt=float(g_opt),
            g_zero_fast=float(g_zero_fast),
            eig_g1=[float(1.0 + eta_minus), float(1.0 + eta_plus)],
            rho_g1=float(max(abs(1.0 + eta_minus), abs(1.0 + eta_plus))),
            eig_g05=[float(1.0 + 0.5 * eta_minus), float(1.0 + 0.5 * eta_plus)],
            rho_g05=float(max(abs(1.0 + 0.5 * eta_minus), abs(1.0 + 0.5 * eta_plus))),
            eig_g_loo=[float(1.0 + g_loo * eta_minus), float(1.0 + g_loo * eta_plus)],
            rho_g_loo=float(max(abs(1.0 + g_loo * eta_minus), abs(1.0 + g_loo * eta_plus))),
        ))
    return rows


def verify_characterization_jacobians(char, target):
    """Independently recompute the finite-difference Jacobians and compare with saved JSON."""
    out = {}
    E_double = L.Estimator(map32=False)
    E_map32 = L.Estimator(map32=True)
    Ft = np.fft.fft2(target.astype(float)) / (128 * 96)

    cases = {}
    for j, v in enumerate(((-1., 2.), (-.8125, .53125))):
        t = np.arange(5)[:, None] * np.array(v)
        F = np.array([E_double.shift(Ft, -a) for a in t])
        cases['phase-vel' + str(j)] = (F, t)
    for k in ('integer', 'fractional'):
        movie, _, truth = C.fixture(k)
        cases['fixture-' + k] = (np.fft.fft2(movie.astype(float)) / (128 * 96), truth[:, 0, 0])

    eps = 1e-3
    for name, (F, t) in cases.items():
        def M_double(s):
            fs = np.array([E_double.shift(f, x) for f, x in zip(F, s)])
            return s + E_double.update(fs)

        def M_map32(s):
            fs = np.array([E_map32.shift(f, x) for f, x in zip(F, s)])
            return s + E_map32.update(fs)

        J_d = np.zeros((8, 8))
        J_m32 = np.zeros((8, 8))
        for i in range(8):
            d = np.zeros_like(t)
            d[1 + i // 2, i % 2] = eps
            J_d[:, i] = ((M_double(t + d) - M_double(t - d)) / (2 * eps))[1:].ravel()
            J_m32[:, i] = ((M_map32(t + d) - M_map32(t - d)) / (2 * eps))[1:].ravel()

        saved_J = np.array(char['cases'][name]['jacobian'])
        ev_d = np.linalg.eigvals(J_d)
        ev_m32 = np.linalg.eigvals(J_m32)
        out[name] = dict(
            max_abs_diff_vs_saved_J=float(np.abs(J_d - saved_J).max()),
            truth_one_step_rms_px_double=float(L.rms(M_double(t) - t)),
            truth_one_step_rms_px_map32=float(L.rms(M_map32(t) - t)),
            eigenvalues_double=[[float(x.real), float(x.imag)] for x in ev_d],
            eigenvalues_map32=[[float(x.real), float(x.imag)] for x in ev_m32],
            J_map32_is_identity=bool(np.allclose(J_m32, np.eye(8))),
        )
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    char, inter = load_saved()
    _, target, _ = C.fixture('integer')

    op_prod = analytical_peak_operator(target, weight='prod')
    op_iso = analytical_peak_operator(target, weight='iso')
    tab_prod = stability_table(op_prod)
    tab_iso = stability_table(op_iso)
    jac_check = verify_characterization_jacobians(char, target)

    # Check float32 ULP quantization at truth on target
    E32 = L.Estimator(map32=True)
    Ft = np.fft.fft2(target.astype(float)) / (128 * 96)
    m64 = np.fft.ifft2(4.0 * Ft * np.conj(Ft) * E32.W).real * (128 * 96)
    m32 = m64.astype(np.float32)
    ulp = float(np.spacing(m32[0, 0]))
    d2x_32 = float(m32[0, 1]) + float(m32[0, -1]) - 2.0 * float(m32[0, 0])
    d2y_32 = float(m32[1, 0]) + float(m32[-1, 0]) - 2.0 * float(m32[0, 0])

    summary = dict(
        analytical_operators=dict(prod=op_prod, iso=op_iso),
        stability_tables=dict(prod=tab_prod, iso=tab_iso),
        jacobian_reproduction=jac_check,
        float32_quantization=dict(
            m00_float32=float(m32[0, 0]),
            ulp_at_peak=ulp,
            d2x_float64=float(m64[0, 1] + m64[0, -1] - 2.0 * m64[0, 0]),
            d2y_float64=float(m64[1, 0] + m64[1, -0] - 2.0 * m64[0, 0]),
            d2x_float32=d2x_32,
            d2y_float32=d2y_32,
            d2x_in_ulps=d2x_32 / ulp,
            d2y_in_ulps=d2y_32 / ulp,
            subpixel_step_quantization_px=0.5 * ulp / abs(d2x_32),
        ),
    )
    out_path = OUT_DIR / 'verification_results.json'
    out_path.write_text(json.dumps(summary, indent=2) + '\n')
    print('Saved verification results to', out_path)


if __name__ == '__main__':
    main()
