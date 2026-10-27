"""Pure functions for the observation-residual diagnostic (see PLAN.md). No file I/O, no fitting, no truth loading."""
import numpy as np

class StopDefinition(Exception):
    """A frozen precondition failed; the run must stop without changing any gauge or definition."""

def check_patch_array(a, nf, name):
    a = np.asarray(a, dtype=float)
    if a.ndim != 3 or a.shape[1] != nf or a.shape[2] != 2 or a.shape[0] < 1:
        raise StopDefinition(f'{name}: unsupported shape {a.shape}, need (patch, {nf}, 2)')
    if not np.isfinite(a).all():
        raise StopDefinition(f'{name}: nonfinite value')
    return a

def tr_expected(H):
    """Expected stored-observation image of a physical trajectory H (H[:,0] == 0): H[g] + 0.5*H[1]."""
    H = np.asarray(H, dtype=float)
    if np.any(H[:, 0, :] != 0.0):
        raise StopDefinition('H at g=0 is not exactly zero; Tr mapping not defined for this gauge')
    return H + 0.5 * H[:, 1:2, :]

def residuals(y, H):
    """All frozen per-patch/frame quantities. y, H: (patch, frame, 2)."""
    y = np.asarray(y, dtype=float); H = np.asarray(H, dtype=float)
    TrH = tr_expected(H)
    e_tr = y - TrH
    s = y - y[:, 0:1, :]
    eta = s - H
    return dict(y=y, H=H, TrH=TrH, e_tr=e_tr, s=s, eta=eta)

def closure(r):
    """Raw algebra closure: eta - (e_Tr - e_Tr[:,0]) (roundoff only)."""
    return r['eta'] - (r['e_tr'] - r['e_tr'][:, 0:1, :])

def norm(v):
    return np.sqrt((np.asarray(v, dtype=float) ** 2).sum(axis=-1))

def summarise(v):
    """v: (..., 2) set of vectors. RMS of vector norm, max norm, signed component means, component RMS, count."""
    v = np.asarray(v, dtype=float).reshape(-1, 2)
    n = norm(v)
    return dict(n=int(len(v)), rms=float(np.sqrt((n ** 2).mean())), max=float(n.max()),
                mean_x=float(v[:, 0].mean()), mean_y=float(v[:, 1].mean()),
                rms_x=float(np.sqrt((v[:, 0] ** 2).mean())), rms_y=float(np.sqrt((v[:, 1] ** 2).mean())))
