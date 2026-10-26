"""Synthetic analytic controls for the joint objective. Tolerances are those in CONTROL_PLAN.md (frozen first).

No payload, no truth, no files read. Writes controls_v2_result.json next to this script.
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import scipy  # noqa: E402

import jointobj_core_v1 as core  # noqa: E402
from jointobj_core_v1 import (JointObjective, NF, NY, NX, HX, reference_J, pair_real_map, native_weight,  # noqa: E402
                              symmetric_nyquist_interpolant, optimise, torus_delta, initial_start_vectors,
                              OMEGA_X, OMEGA_Y, MX, PAIRS)

T_START = time.monotonic()
RES = {}


def record(cid, ok, **kw):
    RES[cid] = dict(passed=bool(ok), **kw)
    print(f"{cid}: {'PASS' if ok else 'FAIL'}  " + json.dumps({k: v for k, v in kw.items() if not isinstance(v, (list, dict))}, default=float), flush=True)


def make_spectra(rng, nyquist_free=True):
    F = np.empty((NF, NY, HX), dtype=np.complex128)
    ly = core.KY[:, None]
    x = core.KX[None, :]
    for f in range(NF):
        img = rng.standard_normal((NY, NX))
        a, b = rng.uniform(2.0, 30.0, size=2)
        env = np.exp(-(a * ly * ly / (NY * NY) + b * x * x / (HX * HX)))
        Ff = np.fft.rfft2(img) * env
        if nyquist_free:
            Ff[NY // 2, :] = 0.0
            Ff[:, HX - 1] = 0.0
        F[f] = Ff
    return F


def rand_frac(rng, sigma=1.7):
    s = np.zeros((NF, 2))
    s[1:] = rng.normal(0.0, sigma, size=(NF - 1, 2))
    return s


def rand_int(rng):
    s = np.zeros((NF, 2))
    s[1:] = rng.integers(-7, 8, size=(NF - 1, 2))
    return s.astype(np.float64)


def reduced_J(obj):
    def fn(x):
        return obj.value(np.vstack([np.zeros((1, 2)), x.reshape(NF - 1, 2)]))
    return fn


def fd_grad(obj, s, h=1e-5):
    x0 = s[1:].ravel()
    fn = reduced_J(obj)
    g = np.zeros_like(x0)
    for i in range(x0.size):
        e = np.zeros_like(x0)
        e[i] = h
        g[i] = (fn(x0 + e) - fn(x0 - e)) / (2 * h)
    return g


def grad_vec(obj, s):
    return obj.value_grad(s)[1][1:].ravel()


def fd_hess(obj, s, h=1e-5):
    x0 = s[1:].ravel()
    n = x0.size
    H = np.zeros((n, n))
    for i in range(n):
        e = np.zeros(n)
        e[i] = h
        gp = grad_vec(obj, np.vstack([np.zeros((1, 2)), (x0 + e).reshape(NF - 1, 2)]))
        gm = grad_vec(obj, np.vstack([np.zeros((1, 2)), (x0 - e).reshape(NF - 1, 2)]))
        H[:, i] = (gp - gm) / (2 * h)
    return H


WSETS = {"Wnative": native_weight(150.0), "Wwide": native_weight(2.0)}

# ---------------------------------------------------------------- C0-C4
rng = np.random.default_rng(1)
Fv = make_spectra(rng, True)
worst = {}
for wn, W in WSETS.items():
    obj = JointObjective(Fv, W)
    # C0
    rel0 = abs(obj.value(np.zeros((NF, 2))) - reference_J(Fv, W, np.zeros((NF, 2)))) / obj.jscale
    worst[f"C0_{wn}"] = rel0
    # C1
    r = np.random.default_rng(11)
    worst[f"C1_{wn}"] = max(abs(obj.value(s) - reference_J(Fv, W, s)) / obj.jscale for s in (rand_int(r) for _ in range(20)))
    # C2
    r = np.random.default_rng(12)
    worst[f"C2_{wn}"] = max(abs(obj.value(s) - reference_J(Fv, W, s)) / obj.jscale for s in (rand_frac(r) for _ in range(20)))
    # C3
    r = np.random.default_rng(13)
    e3 = 0.0
    for _ in range(20):
        s = r.normal(0, 1.7, size=(NF, 2))
        c = r.normal(0, 3.0, size=2)
        e3 = max(e3, abs(obj.value(s) - obj.value(s + c[None, :])) / obj.jscale)
    worst[f"C3_{wn}"] = e3
    # C4: integer-lag pair terms equal the unshifted pair real map
    r = np.random.default_rng(14)
    e4 = 0.0
    maps = {p: pair_real_map(Fv, W, *p) for p in PAIRS}
    for _ in range(20):
        s = rand_int(r)
        tot_map = 0.0
        for (j, f) in PAIRS:
            dx, dy = (s[f] - s[j])
            tot_map += maps[(j, f)][int(dy) % NY, int(dx) % NX]
        e4 = max(e4, abs(obj.value(s) - tot_map) / obj.jscale)
        e4 = max(e4, abs(reference_J(Fv, W, s) - tot_map) / obj.jscale)
    worst[f"C4_{wn}"] = e4
for key, tol in (("C0", 1e-12), ("C1", 1e-12), ("C2", 1e-12), ("C3", 1e-12), ("C4", 1e-12)):
    vals = {wn: worst[f"{key}_{wn}"] for wn in WSETS}
    record(key, max(vals.values()) <= tol, tol=tol, **{f"rel_{wn}": v for wn, v in vals.items()})

# C3b: the optimiser path cannot move frame 0
oc = JointObjective(Fv, WSETS["Wnative"])
res = optimise(oc, np.vstack([np.zeros((1, 2)), np.full((NF - 1, 2), 0.5)]))
record("C3b", (np.array(res["s_final"])[0] == 0.0).all() and len(np.array(res["s_final"])[1:].ravel()) == 8)

# ---------------------------------------------------------------- C5, C6
e5 = {}
e6 = {}
asym = 0.0
for wn, W in WSETS.items():
    obj = JointObjective(Fv, W)
    r = np.random.default_rng(15)
    for _ in range(10):
        s = rand_frac(r)
        e5[wn] = max(e5.get(wn, 0.0), np.abs(grad_vec(obj, s) - fd_grad(obj, s)).max() / obj.jscale)
        Ha = obj.hessian(s)
        asym = max(asym, np.abs(Ha - Ha.T).max() / obj.jscale)
        e6[wn] = max(e6.get(wn, 0.0), np.abs(Ha[2:, 2:] - fd_hess(obj, s)).max() / obj.jscale)
record("C5", max(e5.values()) <= 1e-7, tol=1e-7, **{f"err_{k}": v for k, v in e5.items()})
record("C6", max(e6.values()) <= 1e-7 and asym <= 1e-12, tol=1e-7, asym=asym, **{f"err_{k}": v for k, v in e6.items()})

# ---------------------------------------------------------------- C7, C8 coherent synthetic
rngc = np.random.default_rng(7)
G = make_spectra(rngc, True)[0]
SSTAR = {
    "zeros": np.zeros((NF, 2)),
    "integers": np.array([[0, 0], [3, -2], [-4, 5], [6, 1], [-1, -3]], dtype=np.float64),
    "fractional": np.array([[0, 0], [1.7, -0.9], [-2.3, 2.6], [3.4, 0.35], [-0.8, -3.15]], dtype=np.float64),
}


def coherent_spectra(sstar, G=G, noise=None):
    F = np.stack([G * np.exp(1j * (OMEGA_X * sstar[f, 0] + OMEGA_Y * sstar[f, 1])) for f in range(NF)])
    if noise is not None:
        F = F + noise
    return F


W = WSETS["Wnative"]
Wm = W * MX[None, :]
Wm[0, 0] = 0.0
jmax_formula = len(PAIRS) * float((Wm * np.abs(G) ** 2).sum())
c7_ok = True
c7 = {}
for name, ss in SSTAR.items():
    F = coherent_spectra(ss)
    obj = JointObjective(F, W)
    jv = obj.value(ss)
    relj = abs(jv - jmax_formula) / jmax_formula
    eigmax = np.linalg.eigvalsh(obj.hessian(ss)[2:, 2:]).max() / obj.jscale
    gmax = np.abs(grad_vec(obj, ss)).max() / obj.jscale
    c7[name] = dict(rel_Jmax=relj, hess_eigmax_over_jscale=eigmax, grad_inf_over_jscale=gmax)
    c7_ok &= relj <= 1e-12 and eigmax <= 1e-9
record("C7", c7_ok, detail=c7)

starts9 = [np.zeros((NF, 2))] + [np.vstack([np.zeros((1, 2)), v]) for v in initial_start_vectors()]
c8_ok = True
c8 = {}
for name, ss in SSTAR.items():
    F = coherent_spectra(ss)
    obj = JointObjective(F, W)
    outs = [optimise(obj, st) for st in starts9]
    best = max(outs, key=lambda o: o["J_final"])
    terr = float(np.abs(torus_delta(np.array(best["s_final"]), ss)).max())
    ok = best["J_final"] >= jmax_formula * (1 - 1e-10) and terr <= 1e-5
    c8_ok &= ok
    c8[name] = dict(best_rel_gap=(jmax_formula - best["J_final"]) / jmax_formula, best_torus_err_px=terr,
                    per_start=[dict(rel_gap=(jmax_formula - o["J_final"]) / jmax_formula, nit=o["nit"], nfev=o["nfev"], status=o["status"],
                                    hit_cap=o["hit_cap"], torus_err_px=float(np.abs(torus_delta(np.array(o["s_final"]), ss)).max()))
                               for o in outs])
record("C8", c8_ok, detail=c8)

# ---------------------------------------------------------------- C9 mutants
c9 = {}
for wn, Wx in WSETS.items():
    obj = JointObjective(Fv, Wx)
    mut = {"sign": JointObjective(Fv, Wx, sign=-1), "swap": JointObjective(Fv, Wx, swap=True)}
    r = np.random.default_rng(19)
    states = [rand_frac(r) for _ in range(10)]
    for k, m in mut.items():
        c9[f"obj_{k}_{wn}_min_rel"] = min(abs(m.value(s) - reference_J(Fv, Wx, s)) / obj.jscale for s in states)
        c9[f"grad_{k}_{wn}_max_err"] = max(np.abs(grad_vec(m, s) - fd_grad(obj, s)).max() / obj.jscale for s in states)
    c9[f"grad_neg_{wn}_max_err"] = max(np.abs(-grad_vec(obj, s) - fd_grad(obj, s)).max() / obj.jscale for s in states)
c9_ok = all(v >= 1e-6 for v in c9.values())
record("C9", c9_ok, detail=c9, tol_min=1e-6)

# ---------------------------------------------------------------- C10 Nyquist exposure
r = np.random.default_rng(23)
Wwide = WSETS["Wwide"]
Fny = make_spectra(r, nyquist_free=False)
Fnf = make_spectra(r, nyquist_free=True)
objn = JointObjective(Fny, Wwide)
objf = JointObjective(Fnf, Wwide)
mapsn = {p: pair_real_map(Fny, Wwide, *p) for p in PAIRS}
mapsf = {p: pair_real_map(Fnf, Wwide, *p) for p in PAIRS}


def interp_total(maps, s):
    return sum(symmetric_nyquist_interpolant(maps[(j, f)], *(s[f] - s[j])) for (j, f) in PAIRS)


rr = np.random.default_rng(24)
ea = 0.0
for _ in range(5):
    s = rand_int(rr)
    jr = objn.value(s)
    ea = max(ea, abs(jr - interp_total(mapsn, s)) / objn.jscale)
    dxdy = [(int((s[f] - s[j])[1]) % NY, int((s[f] - s[j])[0]) % NX) for (j, f) in PAIRS]
    ea = max(ea, abs(jr - sum(mapsn[p][a, b] for p, (a, b) in zip(PAIRS, dxdy))) / objn.jscale)
rr = np.random.default_rng(25)
Dn = []
Dfree = []
Dlin = []
mask = np.zeros((NY, HX), dtype=bool)
mask[NY // 2, :] = True
mask[:, HX - 1] = True
for _ in range(10):
    s = rand_frac(rr)
    Dn.append((objn.value(s) - interp_total(mapsn, s)) / objn.jscale)
    Dfree.append((objf.value(s) - interp_total(mapsf, s)) / objf.jscale)
    # linearity: D from the product masked to the Nyquist row/column
    ob_m = JointObjective(Fny, Wwide)
    ob_m.Q = ob_m.Q * mask[None]
    maps_m = {}
    for (j, f) in PAIRS:
        S = Fny[j] * np.conj(Fny[f]) * Wwide
        S = S.copy()
        S[0, 0] = 0.0
        maps_m[(j, f)] = np.fft.irfft2(S * mask, s=(NY, NX)) * core.AREA
    Dm = (ob_m.value(s) - interp_total(maps_m, s)) / objn.jscale
    Dlin.append(abs(Dn[-1] - Dm))
c10 = dict(integer_lag_rel_max=ea, frac_D_over_Jscale_max_abs=float(np.abs(Dn).max()),
           frac_D_over_Jscale=[float(v) for v in Dn],
           nyquist_free_D_rel_max=float(np.abs(Dfree).max()), linearity_rel_max=float(max(Dlin)))
c10_ok = ea <= 1e-12 and c10["frac_D_over_Jscale_max_abs"] >= 1e-6 and c10["nyquist_free_D_rel_max"] <= 1e-12 and c10["linearity_rel_max"] <= 1e-12
record("C10", c10_ok, detail=c10)

# ---------------------------------------------------------------- C11 noisy optimizer sanity
rn = np.random.default_rng(31)
noise = make_spectra(rn, True)  # independent rich noise, same scale as the signal
Fn = coherent_spectra(SSTAR["fractional"], noise=noise)
objn11 = JointObjective(Fn, WSETS["Wnative"])
outs = [optimise(objn11, st) for st in starts9]
c11_ok = all(o["J_final"] >= o["J_start"] for o in outs)
record("C11", c11_ok, per_start=[dict(J_start=o["J_start"], J_final=o["J_final"], nit=o["nit"], nfev=o["nfev"], status=o["status"],
                                      hit_cap=o["hit_cap"], eigmax=o["hessian_eigmax_J"]) for o in outs])

elapsed = time.monotonic() - T_START
record("C12", elapsed <= 120.0, elapsed_s=elapsed, cap_s=120.0)

out = dict(script="controls_v2.py", python=sys.version.split()[0], numpy=np.__version__, scipy=scipy.__version__,
           all_passed=all(v["passed"] for v in RES.values()), results=RES)
with open(os.path.join(HERE, "controls_v2_result.json"), "w") as fh:
    json.dump(out, fh, indent=1, default=float)
print("ALL_PASSED" if out["all_passed"] else "SOME_FAILED", f"{elapsed:.1f}s")
sys.exit(0 if out["all_passed"] else 1)
