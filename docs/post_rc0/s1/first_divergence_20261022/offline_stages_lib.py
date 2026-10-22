# SPDX-License-Identifier: GPL-2.0-or-later
"""Functions shared with offline_stages.py. ledger_inputs.py asserts that every
block below occurs verbatim in offline_stages.py, so the two cannot drift."""
import numpy as np
from scipy.optimize import minimize

NX, NY, NF, NFX, SEARCH, B, TOL, PIX = 128, 96, 5, 65, 47, 150.0, 0.5, 0.885
MANIFEST_SHA = '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
P275 = '6ae486785334fca635cfc9ad9e86026d656f3943'

def weight():
    ly = np.fft.fftfreq(NY) * NY
    x = np.arange(NFX)
    # Production normalisation: ly/nfy and x/nfx with nfx = nx/2+1 (inherited).
    return np.exp(-2*B*((ly[:, None]/NY)**2 + (x[None, :]/NFX)**2))

W = weight()

def ccf_map(F, f, fixed):
    ref = F[0] if fixed else F.sum(axis=0) - F[f]
    return np.fft.irfft2(ref*np.conj(F[f])*W, s=(NY, NX))*(NX*NY)  # unnormalised inverse

def winner(m):
    best, pos = -np.inf, (0, 0)
    for y in range(-SEARCH, SEARCH+1):        # CPU row-major strict-maximum order
        for x in range(-SEARCH, SEARCH+1):
            v = m[y % NY, x % NX]
            if v > best: best, pos = v, (x, y)
    return pos, best

def parabola(m):
    (px, py), mx = winner(m)
    mx = float(mx); out = []
    for (vp, vn, p) in ((m[py % NY, (px+1) % NX], m[py % NY, (px-1) % NX], px),
                        (m[(py+1) % NY, px % NX], m[(py-1) % NY, px % NX], py)):
        vp, vn = float(vp), float(vn); d = vp + vn - 2*mx
        out.append(p - 0.5*(vp-vn)/d if abs(d) > 1e-15 else float(p))
    return np.array(out), (px, py)

def continuous_argmax(S, start):
    """Maximise the band-limited CCF given by half-spectrum S in continuous coordinates."""
    ky = np.fft.fftfreq(NY)[:, None]; kx = (np.arange(NFX)/NX)[None, :]
    mult = np.full(NFX, 2.0); mult[0] = 1; mult[-1] = 1  # Hermitian multiplicity
    def f(p):
        ph = np.exp(2j*np.pi*(kx*p[0] + ky*p[1]))
        v = S*ph*mult
        return -float(np.real(v.sum())), -np.array([float(np.real((2j*np.pi*kx*v).sum())), float(np.real((2j*np.pi*ky*v).sum()))])
    r = minimize(f, np.array(start, float), jac=True, method='BFGS', options=dict(gtol=1e-10))
    return r.x

def shift(F, cur):
    ly = np.fft.fftfreq(NY)*NY; x = np.arange(NFX)
    return F*np.exp(2j*np.pi*(x[None, :]*(-cur[0]/NX) + ly[:, None]*(-cur[1]/NY)))

def replay(F0, fixed, quantize, max_iter=5, tol=TOL, estimator='parabola', truth=None):
    F = F0.astype(np.complex128).copy(); acc = np.zeros((NF, 2)); its = []
    for it in range(1, max_iter+1):
        cand = np.zeros((NF, 2))
        for f in range(NF):
            m = ccf_map(F, f, fixed)
            if estimator == 'parabola':
                cand[f] = parabola(m.astype(np.float32) if quantize else m)[0]
            else:  # exact continuous maximum of the same weighted band-limited objective
                S = (F[0] if fixed else F.sum(0)-F[f])*np.conj(F[f])*W
                cand[f] = continuous_argmax(S, winner(m)[0])
        cand -= cand[0]
        acc += cand
        for f in range(1, NF): F[f] = shift(F[f], cand[f])
        rmsd = float(np.sqrt((cand**2).sum()/NF))
        its.append(dict(iteration=it, rmsd=rmsd, truth_rms_px=err(acc, truth)['rms_px']))
        if rmsd < tol: break
    return acc, its, rmsd < tol

def err(traj, truth):
    v = np.linalg.norm(traj-truth, axis=1)
    return dict(rms_px=float(np.sqrt(np.mean(v*v))), max_px=float(v.max()), rms_angstrom=float(np.sqrt(np.mean(v*v))*PIX))

