#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Known-shift oracle for the peak estimator on the actual weighted objective.

The stored integer-case target (hash-bound) is shifted by exact Fourier phase
ramps (the multiband target is periodic; landmark tails at the border are
< 1e-5). Its production-weighted CCF against the unshifted target is evaluated
in double. For each known offset, the separable 3-point parabola used by both
backends is compared with the exact continuous maximum. The local Hessian at
the exact peak gives the separable-fit cross-term prediction
x_hat - mu_x ~= (Hxy/Hxx) (mu_y - posy), and symmetrically for y.
Weight variants: the production weight (inherited x/nfx with nfx = nx/2+1, so
x frequencies are damped about (128/65)^2 = 3.9x harder than y), an isotropic
x/nx diagnostic weight, and no weight. Only the first is the production objective.

usage: parabola_bias.py RAW FILE_INDEX REPO OUT.json
"""
import hashlib, importlib.util, json, pathlib, subprocess, sys
import numpy as np

RAW, INDEX, REPO, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stages_lib', here/'offline_stages_lib.py')
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
def sha(b): return hashlib.sha256(b).hexdigest()
committed = json.loads(subprocess.check_output(['git', 'show', lib.P275+':docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json'], cwd=REPO))
assert sha(INDEX.read_bytes()) == committed['array_product_index_sha256']
index = json.loads(INDEX.read_text())['files']
rel = 'fixtures/integer_target.npy'
assert sha((RAW/rel).read_bytes()) == index[rel]['sha256']
target = np.load(RAW/rel).astype(np.float64)
Ft = np.fft.rfft2(target)/(lib.NX*lib.NY)
ky = np.fft.fftfreq(lib.NY)[:, None]; kx = (np.arange(lib.NFX)/lib.NX)[None, :]
mult = np.full(lib.NFX, 2.0); mult[0] = 1; mult[-1] = 1

def hessian(S, p):
    ph = S*mult*np.exp(2j*np.pi*(kx*p[0] + ky*p[1]))
    d = lambda a, b: float(np.real(((2j*np.pi)**2*a*b*ph).sum()))
    return np.array([[d(kx, kx), d(kx, ky)], [d(ky, kx), d(ky, ky)]])

def variant(w):
    rows = []
    for mx in np.arange(-1.0, 1.0001, 0.25):
        for my in np.arange(-1.0, 1.0001, 0.25):
            mu = np.array([mx, my])
            # Frame content displaced by -mu, so the correct candidate is mu (production sign).
            Ff = lib.shift(Ft[None], -mu)[0]
            S = Ft*np.conj(Ff)*w
            m = np.fft.irfft2(S, s=(lib.NY, lib.NX))*(lib.NX*lib.NY)
            p, pos = lib.parabola(m)
            c = lib.continuous_argmax(S, pos)
            H = hessian(S, c)
            pred = np.array([mx + H[0, 1]/H[0, 0]*(my-pos[1]), my + H[1, 0]/H[1, 1]*(mx-pos[0])])
            rows.append(dict(true_xy=mu.tolist(), winner=list(pos), parabola_xy=p.tolist(), continuous_xy=c.tolist(),
                             parabola_error_px=float(np.linalg.norm(p-mu)), continuous_error_px=float(np.linalg.norm(c-mu)),
                             cross_term_prediction_xy=pred.tolist(), hessian=H.tolist()))
    H0 = np.array(rows[len(rows)//2]['hessian'])
    ev = np.linalg.eigvalsh(-H0)
    summary = dict(offsets=len(rows), parabola_error_max_px=max(r['parabola_error_px'] for r in rows),
                   parabola_error_rms_px=float(np.sqrt(np.mean([r['parabola_error_px']**2 for r in rows]))),
                   continuous_error_max_px=max(r['continuous_error_px'] for r in rows),
                   integer_offset_parabola_error_max_px=max(r['parabola_error_px'] for r in rows if float(r['true_xy'][0]).is_integer() and float(r['true_xy'][1]).is_integer()),
                   peak_hessian_at_zero=H0.tolist(), hxy_over_hxx=float(H0[0, 1]/H0[0, 0]), hxy_over_hyy=float(H0[1, 0]/H0[1, 1]),
                   curvature_eigenvalue_ratio=float(ev.max()/ev.min()),
                   cross_term_prediction_max_deviation_px=max(float(np.linalg.norm(np.array(r['cross_term_prediction_xy'])-np.array(r['parabola_xy']))) for r in rows))
    return summary, rows

ly_ = np.fft.fftfreq(lib.NY)*lib.NY; x_ = np.arange(lib.NFX)
weights = dict(production=lib.W,
               isotropic_x_over_nx_diagnostic=np.exp(-2*lib.B*((ly_[:, None]/lib.NY)**2 + (x_[None, :]/lib.NX)**2)),
               unweighted_diagnostic=np.ones_like(lib.W))
results = {k: variant(w) for k, w in weights.items()}
summary = {k: v[0] for k, v in results.items()}
rows = {k: v[1] for k, v in results.items()}
OUT.write_text(json.dumps(dict(kind='offline known-shift estimator oracle; no MotionCorr execution', summary=summary, rows=rows,
    bound={rel: index[rel]['sha256']}, script_sha256=sha(pathlib.Path(__file__).read_bytes()),
    lib_sha256=sha((here/'offline_stages_lib.py').read_bytes())), indent=1)+'\n')
print(json.dumps(summary, indent=1))
