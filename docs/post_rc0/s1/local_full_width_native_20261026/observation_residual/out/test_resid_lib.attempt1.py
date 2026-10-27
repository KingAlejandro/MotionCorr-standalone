"""Hand-array checks of resid_lib and of the pinned w8_fit.field coefficient layout. No project data."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import resid_lib as R
sys.path.insert(0, sys.argv[1])           # directory holding the pinned w8_fit.py
import w8_fit as W

H = np.array([[[0, 0], [2, 4], [3, 6], [5, 8], [9, 10]]], float)
TrH = np.array([[[1, 2], [3, 6], [4, 8], [6, 10], [10, 12]]], float)
assert np.array_equal(R.tr_expected(H), TrH)

# A: constant nuisance offset on every frame -> e_Tr constant, physical residual zero
r = R.residuals(TrH + np.array([0.1, -0.2]), H)
assert np.allclose(r['e_tr'], [0.1, -0.2]) and np.allclose(r['eta'], 0) and np.allclose(r['s'], H)

# B: distinct perturbations at g=0 and g=3
d = np.zeros_like(H); d[0, 0] = [0.25, 0.25]; d[0, 3] = [0.5, 0.0]
r = R.residuals(TrH + d, H)
assert np.allclose(r['e_tr'], d)
assert np.allclose(r['eta'][0], [[0, 0], [-.25, -.25], [-.25, -.25], [.25, -.25], [-.25, -.25]])
assert np.abs(R.closure(r)).max() < 1e-15

# C: summaries
s = R.summarise(np.array([[3, 4], [0, 0]], float))
assert abs(s['rms'] - 3.5355339059327378) < 1e-15 and s['max'] == 5 and s['mean_x'] == 1.5 and s['mean_y'] == 2 and s['n'] == 2

# D: frozen STOP conditions
for bad in (H + np.array([0.0, 1e-9]) * np.array([[[1, 0]] * 5]), ):
    try: R.tr_expected(bad); raise SystemExit('FAIL: nonzero g0 accepted')
    except R.StopDefinition: pass
for bad in (np.full((1, 5, 2), np.nan), np.zeros((1, 4, 2)), np.zeros((5, 2)), np.zeros((0, 5, 2))):
    try: R.check_patch_array(bad, 5, 'x'); raise SystemExit('FAIL: bad array accepted')
    except R.StopDefinition: pass

# E: a wrong half-factor would not reproduce the hand image (negative control for tr_expected)
assert not np.array_equal(H + 0.25 * H[:, 1:2, :], TrH)

# F: pinned published-field layout: coeff index 3*s + (k-1), evaluated at z = g (frame index)
cx = np.zeros(18); cy = np.zeros(18); cx[0] = .5; cx[1] = .25; cy[2] = -1.
F = W.field(np.array([cx, cy]), np.array([0.3]), np.array([-0.2]), 5)[:, 0, :]   # (frame, 2)
g = np.arange(5.)
assert np.allclose(F[:, 0], .5 * g + .25 * g * g) and np.allclose(F[:, 1], -g ** 3)
print('hand-array checks: all passed')
