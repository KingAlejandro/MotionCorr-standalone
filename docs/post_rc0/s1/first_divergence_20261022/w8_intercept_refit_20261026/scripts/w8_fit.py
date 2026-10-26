"""W8 refit operators (see ../PLAN.md). NumPy only: never sees truth, generator or evaluator.

Coefficient layout matches MotionCorr / the evaluator: index 3*s + (k-1), spatial
s = (1, u, u^2, v, v^2, uv), temporal k = 1..3, published field evaluated at z = f.
"""
import numpy as np

ARMS = ('native', 'A', 'B1', 'B2', 'C')


def spatial(u, v):
    return np.stack([np.ones_like(u), u, u*u, v, v*v, u*v])


def temporal(nf, arm):
    g = np.arange(nf, dtype=float)
    if arm in ('native', 'A', 'C'):
        t = g + 0.5
        return np.stack([t, t*t, t**3])
    if arm == 'B1':
        return np.stack([g + 0.5, g*g + 0.5, g**3 + 0.5])
    if arm == 'B2':
        return np.stack([g, g*g, g**3])
    raise ValueError(arm)


def design(u, v, nf, arm):
    """Rows (patch, frame); 18 physical columns, then one intercept per patch (not for 'native')."""
    S, T = spatial(u, v), temporal(nf, arm)
    X = (S[:, None, :, None]*T[None, :, None, :]).reshape(18, len(u)*nf).T
    if arm == 'native':
        return X
    return np.hstack([X, np.kron(np.eye(len(u)), np.ones((nf, 1)))])


def fit(obs, u, v, arm):
    """obs (patch, frame, 2) -> published coefficients (2, 18) and nuisance intercepts (2, patch)."""
    n_p, nf, _ = obs.shape
    A = design(u, v, nf, arm)
    sol, _, rank, sv = np.linalg.lstsq(A, obs.reshape(-1, 2), rcond=None)
    a = sol[:18].T.reshape(2, 6, 3)
    if arm == 'C':      # publish h(f) = q(f + 0.5) - q(0.5)
        a = np.stack([a[..., 0] + a[..., 1] + 0.75*a[..., 2], a[..., 1] + 1.5*a[..., 2], a[..., 2]], axis=-1)
    return dict(coeff=a.reshape(2, 18), intercept=sol[18:].T if arm != 'native' else None,
                rank=int(rank), n_cols=A.shape[1], sv=sv)


def conditioning(u, v, nf, arm):
    A = design(u, v, nf, arm)
    raw = np.linalg.svd(A, compute_uv=False)
    sc = np.linalg.svd(A/np.linalg.norm(A, axis=0), compute_uv=False)
    tol = raw.max()*max(A.shape)*np.finfo(float).eps
    return dict(rank=int((raw > tol).sum()), n_cols=A.shape[1], raw_min=float(raw.min()), raw_max=float(raw.max()),
                raw_cond=float(raw.max()/raw.min()), scaled_min=float(sc.min()), scaled_max=float(sc.max()),
                scaled_cond=float(sc.max()/sc.min()),
                spatial_rank=int(np.linalg.matrix_rank(spatial(u, v).T)), distinct_times_per_patch=nf)


def field(coeff, u, v, nf):
    """Published polynomial at lattice (u, v) and z = f: (frame, point, 2)."""
    z = np.arange(nf, dtype=float)
    return np.einsum('agt,tf,gp->fpa', np.asarray(coeff).reshape(2, 6, 3), np.stack([z, z*z, z**3]), spatial(u, v))
