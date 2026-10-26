#!/usr/bin/env python3
"""W8 controls K1-K11 (../PLAN.md). Usage: w8_controls.py SRC RUNS OUT.json
SRC = git archive of 4fa272f6 (unchanged evaluator/generator; used for K11 only); RUNS = H7a results/runs."""
import json
import re
import sys
from pathlib import Path
import numpy as np

SRC, RUNS, OUT = map(Path, sys.argv[1:4])
sys.path.insert(0, str(Path(__file__).resolve().parent))
import w8_fit as W                                    # noqa: E402
sys.path[:0] = [str(SRC/'tools'), str(SRC/'test-data')]
import check_realistic_motion as ev                   # noqa: E402
import generate_realistic_motion as gen               # noqa: E402

TOL = 1e-8
NF = 40
rng = np.random.default_rng(20261026)


def centres(movie):
    text = (RUNS/movie/'F/output/movie.log').read_text()
    c = np.array([(int(a), int(b)) for a, b in re.findall(r'Center = \((\d+), (\d+)\)', text)], float)
    assert len(c) == 25
    return c


def tr(h):
    return h - h[:, :1] + 0.5*(h[:, 1:2] - h[:, :1])


def lattice(nx, ny):
    x, y = np.meshgrid(np.linspace(32, nx-33, 129), np.linspace(32, ny-33, 129))
    return x.ravel()/nx-.5, y.ravel()/ny-.5


def rand_coeff(ks, scale=2.):
    c = np.zeros((2, 6, 3))
    for k in ks:
        c[..., k-1] = rng.standard_normal((2, 6))*scale/39.**k
    return c.reshape(2, 18)


res = dict(tolerance_px=TOL, geometries={}, arms={a: dict(failed=[]) for a in ('A', 'B1', 'B2', 'C')})
for geo, movie, nx, ny in [('4096x4096', 'dose1-s00', 4096, 4096), ('5760x4092', 'nonsquare-s00', 5760, 4092)]:
    pc = centres(movie); pu, pv = pc[:, 0]/nx-.5, pc[:, 1]/ny-.5
    lu, lv = lattice(nx, ny)
    G = res['geometries'][geo] = dict(arms={})
    cases = {'K3_linear': rand_coeff([1]), 'K4_quadratic': rand_coeff([2]), 'K5_cubic': rand_coeff([3]), 'K6_full': rand_coeff([1, 2, 3])}
    for arm in ('A', 'B1', 'B2', 'C'):
        R = G['arms'][arm] = dict(K1=W.conditioning(pu, pv, NF, arm))
        k1 = R['K1']; ok1 = k1['rank'] == k1['n_cols'] and k1['spatial_rank'] == 6 and k1['distinct_times_per_patch'] >= 4
        R['K1']['pass'] = ok1
        for name, c in cases.items():
            obs = tr(W.field(c, pu, pv, NF).transpose(1, 0, 2))            # (patch, frame, 2)
            f = W.fit(obs, pu, pv, arm)
            err = W.field(f['coeff'], lu, lv, NF) - W.field(c, lu, lv, NF)
            R[name] = dict(max_err_px=float(np.abs(err).max()), gauge_f0_max_px=float(np.abs(W.field(f['coeff'], lu, lv, NF)[0]).max()),
                           pass_=bool(np.abs(err).max() <= TOL))
            if arm == 'A' and name in ('K4_quadratic', 'K5_cubic'):
                # Reviewer algebra: published q(f) = b(f^2 - f) for b f^2, c(f^3 - 1.5 f^2 + 0.75 f) for c f^3.
                cc = c.reshape(2, 6, 3).copy(); pred = np.zeros_like(cc)
                if name == 'K4_quadratic': pred[..., 1] = cc[..., 1]; pred[..., 0] = -cc[..., 1]
                else: pred[..., 2] = cc[..., 2]; pred[..., 1] = -1.5*cc[..., 2]; pred[..., 0] = 0.75*cc[..., 2]
                R[name]['matches_reviewer_algebra_max_px'] = float(np.abs(W.field(f['coeff'], lu, lv, NF) - W.field(pred.reshape(2, 18), lu, lv, NF)).max())
        R['K2_gauge_pass'] = all(R[n]['gauge_f0_max_px'] == 0.0 for n in cases)
        obs = tr(W.field(cases['K6_full'], pu, pv, NF).transpose(1, 0, 2))
        f0 = W.fit(obs, pu, pv, arm); f1 = W.fit(obs + rng.standard_normal((25, 1, 2)), pu, pv, arm)
        d = float(np.abs(W.field(f0['coeff'], lu, lv, NF) - W.field(f1['coeff'], lu, lv, NF)).max())
        R['K7_offset_invariance'] = dict(max_change_px=d, pass_=d <= TOL)
        for name in ['K1', 'K2', 'K3_linear', 'K4_quadratic', 'K5_cubic', 'K6_full', 'K7_offset_invariance']:
            ok = {'K1': ok1, 'K2': R['K2_gauge_pass']}.get(name, R.get(name, {}).get('pass_'))
            if not ok: res['arms'][arm]['failed'].append(f'{geo}:{name}')
    # K8 equivalence of B1, B2, C on K6 and on a noisy input.
    obs = tr(W.field(cases['K6_full'], pu, pv, NF).transpose(1, 0, 2))
    noisy = obs + 0.3*rng.standard_normal(obs.shape)
    K8 = {}
    for nm, o in [('K6', obs), ('noisy', noisy)]:
        F = {a: W.fit(o, pu, pv, a) for a in ('B1', 'B2', 'C')}
        K8[nm] = {f'{a}-B2': float(np.abs(W.field(F[a]['coeff'], lu, lv, NF) - W.field(F['B2']['coeff'], lu, lv, NF)).max()) for a in ('B1', 'C')}
    G['K8_equivalence_max_px'] = K8
    for a in ('B1', 'C'):
        if max(K8[n][f'{a}-B2'] for n in K8) > TOL: res['arms'][a]['failed'].append(f'{geo}:K8')

# K9 W7 counterexample: deterministic step, no frame-0 error.
a = 0.37; eps = np.where(np.arange(NF) >= 20, a, 0.)[None, :, None]
delta = tr(eps); eloc = delta[:, 1:] - delta[:, :1]; m = eloc.mean(1)
res['K9'] = dict(delta_equals_eps=bool(np.array_equal(delta, eps)), delta1_eq_3delta0=bool(delta[0, 1, 0] == 3*delta[0, 0, 0]),
                 anchor_ratio=float(np.abs(m).max()/np.sqrt(np.mean((eloc-m[:, None])**2))), expected=float(np.sqrt(20/19)))
# K10 LS-floor counterexample (evaluator's vector_metrics definition on scalars).
y = np.array([0., 0., 3.])
met = lambda e: dict(rms=float(np.sqrt(np.mean(e*e))), p95=float(np.percentile(abs(e), 95)), max=float(abs(e).max()))
res['K10'] = dict(ls_constant=float(y.mean()), at_ls=met(y-y.mean()), at_1p5=met(y-1.5))
# K11 perfect census inputs: G = g, observations Tr[Tc - g], unchanged evaluator.
res['K11'] = {}
for label, cond, movie in [('inmodel_4096', 'dose1', 'dose1-s00'), ('inmodel_nonsquare', 'nonsquare', 'nonsquare-s00'), ('outmodel', 'outmodel', 'outmodel-s00')]:
    r = gen.recipe(cond, 0); pc = centres(movie)
    t = np.arange(NF)/(NF-1)
    g = -np.stack([8*(-np.expm1(-t/.1))+4*t, -5*(-np.expm1(-t/.15))-2*t], axis=-1)    # evaluator's declared drift
    Tc = np.stack([-gen.displacement(r, f, pc[:, 0], pc[:, 1]) for f in range(NF)], 1)
    obs = tr(Tc - g[None])
    res['K11'][label] = {}
    for arm in ('native', 'A', 'B1', 'B2', 'C'):
        f = W.fit(obs, pc[:, 0]/r['nx']-.5, pc[:, 1]/r['ny']-.5, arm)
        model = {'global': g.tolist(), 'coeff_x': f['coeff'][0].tolist(), 'coeff_y': f['coeff'][1].tolist(), 'local_enabled': True}
        e = ev.evaluate(r, model)['field']
        res['K11'][label][arm] = dict(px_max=e['px']['max'], A=e['angstrom'])

res['census_eligible'] = [a for a in ('A', 'B1', 'B2', 'C') if not res['arms'][a]['failed']]
OUT.write_text(json.dumps(res, indent=1, allow_nan=False)+'\n')
print(json.dumps(dict(failed={a: v['failed'] for a, v in res['arms'].items()}, eligible=res['census_eligible'],
                      K9=res['K9'], K10=res['K10'], K11={k: {a: v[a]['px_max'] for a in v} for k, v in res['K11'].items()}), indent=1))
