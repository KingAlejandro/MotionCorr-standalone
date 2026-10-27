"""Raw half-plane phase-coherence joint objective J(s), analytic gradient/Hessian, L-BFGS-B driver.

Pure functions; reads no files. Shared verbatim by controls_v1.py and stage1_v1.py.
See CONTROL_PLAN.md for the definition and derivative signs.
"""
import os
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

NY, NX, HX, NF = 32, 42, 22, 5
AREA = NY * NX  # native C2R is unnormalised ("FwdOnly"), numpy irfft2 divides by this

# Frozen optimizer settings (provisional until independent math review).
LBFGSB_OPTIONS = dict(maxiter=300, maxfun=2000, gtol=1e-8, ftol=1e-13, maxls=30)
RANDOM_START_SEED = 238267
RANDOM_START_SIGMA_PX = 2.0
N_RANDOM_STARTS = 8

_y = np.arange(NY)
KY = np.where(_y > NY // 2, _y - NY, _y).astype(np.float64)  # y=16 -> +16, as in the native source
KX = np.arange(HX, dtype=np.float64)
OMEGA_X = (2.0 * np.pi * KX / NX)[None, :] * np.ones((NY, 1))   # [32,22]
OMEGA_Y = (2.0 * np.pi * KY / NY)[:, None] * np.ones((1, HX))   # [32,22]
MX = np.full(HX, 2.0)
MX[0] = 1.0
MX[HX - 1] = 1.0
PAIRS = [(j, f) for f in range(NF) for j in range(f)]  # j < f


def native_weight(scaled_B):
    """Native ccfWeightAt formula (x_norm = nfx = 22), evaluated from the formula, not from saved weights."""
    ly = KY[:, None]
    x = KX[None, :]
    return np.exp(-2.0 * (ly * ly / (NY * NY) + x * x / (HX * HX)) * scaled_B)


def initial_start_vectors():
    """The 8 frozen random starts, shape [8,4,2] = (start, frame 1..4, [x,y]); same draws for every patch."""
    rng = np.random.Generator(np.random.PCG64(RANDOM_START_SEED))
    return rng.normal(0.0, RANDOM_START_SIGMA_PX, size=(N_RANDOM_STARTS, NF - 1, 2))


class JointObjective:
    """J(s) = sum_{j<f} Re sum m_x W F_j conj(F_f) exp(+i phi_jf), s is (5,2)=[frame,(x,y)].

    sign=-1 and swap=True build the wrong-sign and swapped-axis MUTANTS (controls only).
    """

    def __init__(self, F, W, sign=+1, swap=False):
        F = np.asarray(F, dtype=np.complex128)
        W = np.asarray(W, dtype=np.float64)
        assert F.shape == (NF, NY, HX) and W.shape == (NY, HX)
        Wm = W * MX[None, :]
        Wm[0, 0] = 0.0  # zero DC
        self.Q = np.stack([Wm * F[j] * np.conj(F[f]) for j, f in PAIRS])  # [10,32,22]
        self.jscale = float(np.abs(self.Q).sum())
        self.sign = float(sign)
        self.ax, self.ay = (1, 0) if swap else (0, 1)  # which shift component pairs with kx / ky

    def _pair_terms(self, s):
        s = np.asarray(s, dtype=np.float64)
        d = np.stack([s[f] - s[j] for j, f in PAIRS])  # [10,2]
        phi = self.sign * (OMEGA_X[None] * d[:, self.ax, None, None] + OMEGA_Y[None] * d[:, self.ay, None, None])
        return self.Q * np.exp(1j * phi)

    def value(self, s):
        return float(self._pair_terms(s).real.sum())

    def value_grad(self, s):
        QE = self._pair_terms(s)
        J = float(QE.real.sum())
        im = QE.imag
        gp = np.zeros((len(PAIRS), 2))
        gp[:, self.ax] = -self.sign * (OMEGA_X[None] * im).sum(axis=(1, 2))
        gp[:, self.ay] = -self.sign * (OMEGA_Y[None] * im).sum(axis=(1, 2))
        g = np.zeros((NF, 2))
        for p, (j, f) in enumerate(PAIRS):
            g[f] += gp[p]
            g[j] -= gp[p]
        return J, g

    def hessian(self, s):
        """Full Hessian of J w.r.t. s.ravel() (10x10, frame-major, [x,y])."""
        QE = self._pair_terms(s)
        re = QE.real
        om = {self.ax: OMEGA_X, self.ay: OMEGA_Y}
        H = np.zeros((2 * NF, 2 * NF))
        for p, (j, f) in enumerate(PAIRS):
            hb = np.zeros((2, 2))
            for a in (0, 1):
                for b in (0, 1):
                    hb[a, b] = -(om[a] * om[b] * re[p]).sum()
            for (u, su) in ((f, 1.0), (j, -1.0)):
                for (v, sv) in ((f, 1.0), (j, -1.0)):
                    H[2 * u:2 * u + 2, 2 * v:2 * v + 2] += su * sv * hb
        return H


# ----------------------------- independent reference (no shared code with the analytic path) ----------------

_KY_REF = np.array([yy if yy <= 16 else yy - 32 for yy in range(32)], dtype=np.float64)
_KX_REF = np.fft.rfftfreq(42) * 42


def shifted_spectra_ref(F0, s):
    s = np.asarray(s, dtype=np.float64)
    ph = np.exp(-2j * np.pi * (_KX_REF[None, None, :] * s[:, 0, None, None] / 42.0
                               + _KY_REF[None, :, None] * s[:, 1, None, None] / 32.0))
    return np.asarray(F0, dtype=np.complex128) * ph


def reference_J(F0, W, s):
    """Native-grid aggregate form: J = 0.5 sum_f C2R[(sum_{l!=f} F_l(s)) conj(F_f(s)) W, DC zeroed](lag 0)."""
    Fs = shifted_spectra_ref(F0, s)
    tot = Fs.sum(axis=0)
    acc = 0.0
    for f in range(NF):
        S = (tot - Fs[f]) * np.conj(Fs[f]) * W
        S[0, 0] = 0.0
        acc += (np.fft.irfft2(S, s=(NY, NX)) * AREA)[0, 0]
    return float(acc / 2.0)


def pair_real_map(F0, W, j, f):
    S = F0[j] * np.conj(F0[f]) * W
    S = S.copy()
    S[0, 0] = 0.0
    return np.fft.irfft2(S, s=(NY, NX)) * AREA


def symmetric_nyquist_interpolant(m, x, y):
    """Trig interpolant of a real [32,42] map at fractional (x,y); Nyquist modes use cos (split +-N/2).
    Explicit full-plane slow sum, no FFT in the evaluation."""
    M = np.fft.fft2(m)
    acc = 0.0 + 0.0j
    for iy in range(NY):
        if iy == NY // 2:
            py = np.cos(np.pi * y)
        else:
            k = iy if iy < NY // 2 else iy - NY
            py = np.exp(2j * np.pi * k * y / NY)
        for ix in range(NX):
            if ix == NX // 2:
                px = np.cos(np.pi * x)
            else:
                k = ix if ix < NX // 2 else ix - NX
                px = np.exp(2j * np.pi * k * x / NX)
            acc += M[iy, ix] * py * px
    return float(acc.real / AREA)


# ----------------------------- optimizer driver ---------------------------------------------------------------

class TimeCap(Exception):
    pass


def optimise(obj, s_start, deadline=None):
    """Maximise J by minimising -J over s[1:] (s[0] fixed at exactly 0). Unbounded L-BFGS-B, frozen options."""
    s_start = np.asarray(s_start, dtype=np.float64).reshape(NF, 2)
    assert s_start[0, 0] == 0.0 and s_start[0, 1] == 0.0, "gauge: frame 0 must be exactly 0"
    x0 = s_start[1:].ravel().copy()
    last = {"x": x0.copy()}

    def fun(x):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeCap()
        last["x"] = x.copy()
        s = np.vstack([np.zeros((1, 2)), x.reshape(NF - 1, 2)])
        J, g = obj.value_grad(s)
        return -J, -g[1:].ravel()

    J0 = obj.value(s_start)
    t0 = time.monotonic()
    time_capped = False
    try:
        r = minimize(fun, x0, jac=True, method="L-BFGS-B", bounds=None, options=dict(LBFGSB_OPTIONS))
        x, nit, nfev, njev = r.x, int(r.nit), int(r.nfev), int(getattr(r, "njev", r.nfev))
        status, message, success = int(r.status), str(r.message), bool(r.success)
    except TimeCap:
        time_capped = True
        x, nit, nfev, njev = last["x"], -1, -1, -1
        status, message, success = -9, "TIME_CAP", False
    s_fin = np.vstack([np.zeros((1, 2)), np.asarray(x).reshape(NF - 1, 2)])
    J, g = obj.value_grad(s_fin)
    eig = np.linalg.eigvalsh(obj.hessian(s_fin)[2:, 2:])
    iter_cap = (status == 1) or ("TOTAL NO. OF" in message) or time_capped
    return dict(
        s_start=s_start.tolist(), s_final=s_fin.tolist(), J_start=J0, J_final=J,
        grad_inf=float(np.abs(g[1:]).max()), grad_2=float(np.linalg.norm(g[1:])),
        nit=nit, nfev=nfev, njev=njev, status=status, message=message, success=success,
        hit_cap=bool(iter_cap), time_capped=time_capped,
        hessian_eigs_J=eig.tolist(), hessian_eigmax_J=float(eig.max()),
        wall_s=time.monotonic() - t0,
    )


def torus_delta(a, b):
    """Elementwise shortest signed difference a-b on the 42 (x) x 32 (y) torus; arrays [...,2]=(x,y)."""
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    period = np.array([NX, NY], dtype=np.float64)
    return d - period * np.round(d / period)
