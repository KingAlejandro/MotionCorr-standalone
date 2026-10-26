#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W6 round 2: per-iteration logs for the vel1-N20 harmful case and the P5 gaps. Diagnostic only.

Uses the unmodified round-2 W5 lib and the W6Estimator class taken verbatim from W6 scripts/w6.py.
Logging wraps peak()/update() without changing any returned value; final states are checked
against the frozen W6 results bit for bit.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time

W2 = Path(__file__).resolve().parents[1]
W6 = W2.parent
W5 = W6.parent / 'w5_intervention_20261025'
sha = lambda b: hashlib.sha256(b).hexdigest()
PINS = {
    W6/'scripts/w6.py': '2037cb5359ef518ffd83490ae413b40ccf504aa21715f1af1dde51ec7fe2ffac',
    W6/'results/w6.json': 'd9e2c0be78c6eeb368f8d520f6b4fc3ea195a3275573046bcd7b9c5cda311b02',
    W5/'round2/INPUTS.json': '8fe6c1f467284786384ab3f600c4175a6f8cd8bc697b214d362bb6042e3be48f',
    W5/'round2/scripts/lib.py': 'e47e05a2e151dec2b5b3fa5600712dbae256ba3bf9a1c7b38bb8d9851b675afe',
}
for p, pin in PINS.items():
    assert sha(p.read_bytes()) == pin, p
assert sys.argv[1:] == ['--run-frozen-w6-round2']

sys.path.insert(0, str(W5 / 'round2/scripts'))
import lib
from lib import np, C, Estimator, serial
lib.verify()
lib.R = W2  # STAR artifacts from field_result go under round2/results/star
tree = ast.parse((W6/'scripts/w6.py').read_text())
node = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'W6Estimator']
env = dict(Estimator=Estimator, np=np)
exec(compile(ast.Module(body=node, type_ignores=[]), 'w6.py[W6Estimator]', 'exec'), env)
W6Estimator = env['W6Estimator']
ARMS = {'S-P': (False, False), 'S-D': (False, True), 'H-P': (True, False), 'H-D': (True, True)}
DOMAINS = {'double': False, 'map32': True}
w6 = json.loads((W6/'results/w6.json').read_text())
started = time.time()


def local_maxima(m, s, top):
    """Top local maxima (8-neighbour, periodic) inside the search window: [x, y, value]."""
    nb = np.stack([np.roll(np.roll(m, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
    win = np.ix_(s % m.shape[0], s % m.shape[1])
    is_max, vals = (m[None] >= nb).all(0)[win], m[win]
    iy, ix = np.nonzero(is_max)
    order = np.argsort(-vals[iy, ix], kind='stable')[:top]
    return [[int(s[ix[o]]), int(s[iy[o]]), float(vals[iy[o], ix[o]])] for o in order]


class Logged(W6Estimator):
    def __init__(self, *a, keep_maps=0, **k):
        super().__init__(*a, **k)
        self.log, self.maps, self.keep_maps = [], [], keep_maps

    def update(self, F):
        self.log.append([])
        self.maps.append([])
        return super().update(F)

    def peak(self, m):
        res = super().peak(m)
        s = self.indices
        i = int(np.argmax(m[np.ix_(s % self.ny, s % self.nx)]))
        px, py = int(s[i % len(s)]), int(s[i // len(s)])
        self.log[-1].append(dict(peak=res.tolist(), argmax=[px, py], top=local_maxima(m, s, 3)))
        if len(self.maps) <= self.keep_maps:
            self.maps[-1].append(np.array(m))
        return res


def logged_run(F, it, tol, dom, arm, weight, t, start=None, keep_maps=0):
    coupled, dc = ARMS[arm]
    e = Logged(weight=weight, map32=DOMAINS[dom], coupled=coupled, dc=dc, keep_maps=keep_maps)
    rr = e.run(F, it, tol, start=start, truth=t, keep_states=True)
    states = rr.pop('states')
    N = len(t)
    iters = []
    for k, rows in enumerate(e.log):  # the last entry is run()'s extra endpoint update
        s = states[k]
        r = t - s
        ideal = np.array([r[f]-(r.sum(0)-r[f])/(N-1) for f in range(N)])
        peaks = np.array([x['peak'] for x in rows])
        arg = np.array([x['argmax'] for x in rows])
        dev = np.abs(arg-np.round(ideal)).max(1)
        u = peaks-peaks[0]
        iters.append(dict(iteration=k+1 if k < rr['iterations'] else 'endpoint',
                          raw_update_rms_px=lib.rms(u), max_frame_update_px=float(np.linalg.norm(u, axis=1).max()),
                          error_before_rms_px=lib.rms(s-t),
                          error_after_rms_px=lib.rms(states[k+1]-t) if k+1 < len(states) else None,
                          ideal=ideal.tolist(), argmax=arg.tolist(), argmax_minus_round_ideal_cheb=dev.tolist(),
                          frames_argmax_off_by_ge2=int((dev >= 2).sum()), peaks=peaks.tolist(),
                          zero_update_frames=[f for f in range(1, N) if not u[f].any()],
                          top_maxima=[x['top'] for x in rows]))
    return e, rr, states, iters


E = Estimator()
_, target, _ = C.fixture('integer')
Ft = np.fft.fft2(target.astype(float))/(128*96)


def ramp(iv, N):
    vel = ((-1., 2.), (-.8125, .53125))[iv]
    t = np.arange(N)[:, None]*np.array(vel)
    return np.array([E.shift(Ft, -x) for x in t]), t


out = dict(checks={}, harmful={}, starts={}, acf={}, map32_divergence={}, p5={})
identity = 0
F, t = ramp(1, 20)
truth = np.broadcast_to(t[:, None, None], (20, 96, 128, 2))
runs = {}
for weight in ('iso', 'prod'):
    for dom in DOMAINS:
        for arm in ARMS:
            for stop, (it, tol) in (('5it', (5, .5)), ('50it', (50, 1e-9))):
                e, rr, states, iters = logged_run(F, it, tol, dom, arm, weight, t, keep_maps=5 if stop == '5it' and dom == 'map32' else 0)
                ref = np.array(w6['probes'][f'vel1-N20-{weight}-{dom}-{arm}-{stop}']['global_trajectory'])
                assert np.array_equal(ref, rr['state']), (weight, dom, arm, stop)
                identity += 1
                runs[(weight, dom, arm, stop)] = (e, rr, states)
                endpoint_err = (rr['state']-t).tolist()
                out['harmful'][f'vel1-N20-{weight}-{dom}-{arm}-{stop}'] = dict(
                    iterations=rr['iterations'], final_error_rms_px=lib.rms(rr['state']-t),
                    endpoint_update_rms_px=rr['endpoint_update_rms_px'], endpoint_frame_error_px=endpoint_err,
                    guard=e.guard, per_iteration=iters)
out['checks']['logged_runs_equal_w6_trajectories'] = identity

# (i) starts at truth and at 50% of truth.
for weight in ('iso', 'prod'):
    for dom in DOMAINS:
        for arm in ARMS:
            for frac in (1., .5):
                for stop, (it, tol) in (('5it', (5, .5)), ('50it', (50, 1e-9))):
                    coupled, dc = ARMS[arm]
                    e = W6Estimator(weight=weight, map32=DOMAINS[dom], coupled=coupled, dc=dc)
                    rr = e.run(F, it, tol, start=frac*t, truth=t)
                    key = f'vel1-N20-{weight}-{dom}-{arm}-start{frac:g}-{stop}'
                    sc = lib.field_result('w6r2-'+key, rr['state'], None, truth)
                    out['starts'][key] = dict(final_error_rms_px=lib.rms(rr['state']-t), iterations=rr['iterations'],
                                              history=rr['history'], runtime=sc['runtime'], STAR=sc['STAR'], guard=e.guard)

# Alias candidates: local maxima of the W-weighted target autocorrelation (DC removed so heights are relative to the AC peak).
for weight in ('iso', 'prod'):
    e = Estimator(weight=weight)
    spec = Ft*np.conj(Ft)*e.W
    spec[0, 0] = 0
    acf = np.fft.ifft2(spec).real
    mx = local_maxima(acf, e.indices, 12)
    out['acf'][weight] = [[x, y, v/acf[0, 0]] for x, y, v in mx]

# map32 escape: first divergence of map32 S-P against S-D and H-D (and H-P) on vel1-N20-iso.
for stop in ('5it', '50it'):
    base_e, base_rr, base_states = runs[('iso', 'map32', 'S-P', stop)]
    for arm in ('S-D', 'H-P', 'H-D'):
        e, rr, states = runs[('iso', 'map32', arm, stop)]
        first_arg = first_sub = None
        for k in range(min(len(base_e.log), len(e.log))):
            for f in range(20):
                a, b = base_e.log[k][f], e.log[k][f]
                if first_sub is None and np.abs(np.array(a['peak'])-b['peak']).max() > 1e-6:
                    first_sub = (k+1, f)
                if first_arg is None and a['argmax'] != b['argmax']:
                    first_arg = (k+1, f)
        rec = dict(first_subpixel_divergence=first_sub, first_argmax_divergence=first_arg)
        if first_arg is not None:
            k, f = first_arg
            rec['state_difference_before_px'] = float(np.abs(base_states[k-1]-states[k-1]).max())
            rec['zero_update_frames_SP_before'] = [
                (kk+1, ff) for kk in range(k-1) for ff in range(1, 20)
                if base_e.log[kk][ff]['peak'] == base_e.log[kk][0]['peak']]
            for name, ee in (('S-P', base_e), (arm, e)):
                x = ee.log[k-1][f]
                d = dict(argmax=x['argmax'], peak=x['peak'], top_maxima=x['top'])
                if k <= len(ee.maps) and ee.maps[k-1]:
                    m = ee.maps[k-1][f]
                    px, py = x['argmax']
                    d['nb3'] = [[float(m[(py+a) % 96, (px+b) % 128]) for b in (-1, 0, 1)] for a in (-1, 0, 1)]
                    v0 = np.float32(x['top'][0][2])
                    d['ulp_at_peak'] = float(np.spacing(v0))
                    d['top2_gap_ulps'] = float((x['top'][0][2]-x['top'][1][2])/np.spacing(v0))
                rec[name] = d
            # The same frame/iteration in double (same state at iteration 1 only).
            if k == 1:
                de = runs[('iso', 'double', 'S-P', stop)][0]
                rec['double_SP_same_frame'] = dict(argmax=de.log[0][f]['argmax'], top_maxima=de.log[0][f]['top'])
        out['map32_divergence'][f'{stop}-SP-vs-{arm}'] = rec

# P5: double rounding-level differences, per iteration.
movie, _, _ = C.fixture('pedestal')
Fp = np.fft.fft2(movie.astype(float))/(128*96)
p5_rows = [('vel0-N13-prod-5it', 'S-P', 'S-D'), ('vel0-N9-prod-5it', 'S-P', 'S-D'),
           ('vel0-N13-iso-5it', 'H-P', 'H-D'), ('pedestal-50it', 'S-P', 'S-D')]
for row, a1, a2 in p5_rows:
    res = {}
    for arm in (a1, a2):
        if row.startswith('pedestal'):
            # Truth here only feeds the logged error columns; the P5 comparison is arm against arm.
            e, rr, states, iters = logged_run(Fp, 50, 1e-9, 'double', arm, 'prod', np.array(C.fixture('pedestal')[2][:, 48, 64]))
            ref = w6['cases']['pedestal']['rows'][f'double-{arm}-50it']['global_trajectory']
        else:
            vel, N, weight, stop = row.split('-')
            Fr, tr = ramp(int(vel[3]), int(N[1:]))
            e, rr, states, iters = logged_run(Fr, 5, .5, 'double', arm, weight, tr)
            ref = w6['probes'][f'{vel}-{N}-{weight}-double-{arm}-{stop}']['global_trajectory']
        assert np.array_equal(np.array(ref), rr['state']), (row, arm)
        res[arm] = (e, states)
    (e1, s1), (e2, s2) = res[a1], res[a2]
    per = []
    for k in range(min(len(e1.log), len(e2.log))):
        p1 = np.array([x['peak'] for x in e1.log[k]])
        p2 = np.array([x['peak'] for x in e2.log[k]])
        per.append(dict(iteration=k+1, peak_diff_max_px=float(np.abs(p1-p2).max()),
                        state_diff_before_max_px=float(np.abs(s1[min(k, len(s1)-1)]-s2[min(k, len(s2)-1)]).max()),
                        argmax_differs_frames=[f for f in range(len(p1)) if e1.log[k][f]['argmax'] != e2.log[k][f]['argmax']]))
    out['p5'][f'{row}:{a1}-vs-{a2}'] = dict(final_state_diff_max_px=float(np.abs(s1[-1]-s2[-1]).max()), per_iteration=per)
    print('p5', row, [(x['iteration'], x['peak_diff_max_px'], x['argmax_differs_frames']) for x in per][:8], flush=True)

out.update(kind='W6 round 2 diagnostic logs; offline NumPy, native/CUDA UNRUN', elapsed_s=time.time()-started,
           python=sys.version, numpy=np.__version__,
           script_hashes={p.name: sha(p.read_bytes()) for p in sorted((W2/'scripts').glob('*.py'))},
           pins={str(p.relative_to(W6.parent)): v for p, v in PINS.items()})
p = W2/'results/mech.json'
assert not p.exists()
p.write_text(json.dumps(out, indent=1, allow_nan=False)+'\n')
print('checks', out['checks'], 'divergence', json.dumps(out['map32_divergence'])[:3000], flush=True)
