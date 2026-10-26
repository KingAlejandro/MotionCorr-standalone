#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W6: DCg+H2g (global CCF DC bin zeroed, coupled 2x2 peak, gain 1) on the W5 round-2 controls.

Reuses the unmodified round-2 lib (Estimator, patch_fit, field_result). Only the GLOBAL estimator
is subclassed; patch peaks, weights, stop rule, fit, ROI, limits and scoring are untouched.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

W6 = Path(__file__).resolve().parents[1]
W5 = W6.parent / 'w5_intervention_20261025'
sha = lambda b: hashlib.sha256(b).hexdigest()
# Framework files not re-verified by lib.verify(); hashes from round2/SHA256SUMS and git 8815f923.
PINS = {
    'round2/INPUTS.json': '8fe6c1f467284786384ab3f600c4175a6f8cd8bc697b214d362bb6042e3be48f',
    'round2/scripts/lib.py': 'e47e05a2e151dec2b5b3fa5600712dbae256ba3bf9a1c7b38bb8d9851b675afe',
    'round2/results/e1-intervention.json': '35964b2391ad819d2590105673ce43f6c9f8fb00500023091635181a2dc36d0f',
    'round2/results/e1-characterization.json': '3cc079461befd79eaa213817e55ab93a5fe15ca8ff1d0a36c15df86e5318672e',
}
for rel, pin in PINS.items():
    assert sha((W5 / rel).read_bytes()) == pin, rel
assert sys.argv[1:] == ['--run-frozen-w6']

sys.path.insert(0, str(W5 / 'round2/scripts'))
import lib
from lib import np, C, Estimator, patch_fit, serial, PIX
lib.verify()
# field_result writes its STAR artifacts under lib.R/results/star; point it at W6 so W5 stays read-only.
lib.R = W6
field_result = lib.field_result


class W6Estimator(Estimator):
    def __init__(self, *a, coupled=False, dc=False, **k):
        super().__init__(*a, **k)
        self.coupled, self.dc = coupled, dc
        self.guard = dict(peaks=0, not_negative_definite=0, offset_gt_1px=0)

    def peak(self, m):
        out = super().peak(m)
        if not self.coupled:
            return out
        # Mirrors native MotioncorrRunner::coupledPeakOffset; v[dy+1][dx+1] around the same argmax.
        s = self.indices
        i = int(np.argmax(m[np.ix_(s % self.ny, s % self.nx)]))
        px, py = int(s[i % len(s)]), int(s[i // len(s)])
        v = [[float(m[(py+a) % self.ny, (px+b) % self.nx]) for b in (-1, 0, 1)] for a in (-1, 0, 1)]
        gx, gy = .5*(v[1][2]-v[1][0]), .5*(v[2][1]-v[0][1])
        hxx, hyy = v[1][2]+v[1][0]-2.*v[1][1], v[2][1]+v[0][1]-2.*v[1][1]
        hxy = .25*(v[2][2]-v[2][0]-v[0][2]+v[0][0])
        det = hxx*hyy-hxy*hxy
        self.guard['peaks'] += 1
        if not (hxx < 0 and det > 0):
            self.guard['not_negative_definite'] += 1
            return out
        ox, oy = -(hyy*gx-hxy*gy)/det, -(hxx*gy-hxy*gx)/det
        if not (abs(ox) <= 1. and abs(oy) <= 1.):
            self.guard['offset_gt_1px'] += 1
            return out
        return np.array([px+ox, py+oy])

    def update(self, F):
        if not self.dc:
            return super().update(F)
        # lib.Estimator.update with the single native DCg change: zero the CCF (0,0) bin before the inverse.
        total = F.sum(0)
        out = []
        for f in range(len(F)):
            spec = (total-F[f])*np.conj(F[f])*self.W
            spec[0, 0] = 0
            m = np.fft.ifft2(spec).real
            if self.map32:
                m = (m*(self.nx*self.ny)).astype(np.float32)
            out.append(self.peak(m))
        out = np.array(out)
        return out-out[0]


ARMS = {'S-P': (False, False), 'S-D': (False, True), 'H-P': (True, False), 'H-D': (True, True)}
STOPS = {'5it': (5, .5), '50it': (50, 1e-9)}
DOMAINS = {'double': False, 'map32': True}
old = json.loads((W5 / 'round2/results/e1-intervention.json').read_text())
char = json.loads((W5 / 'round2/results/e1-characterization.json').read_text())
checks = {}
started = time.time()

# Control 1: stored float32 patch maps and candidates (round-2 control), through lib and through W6 flags-off.
worst = worst6 = 0.
for iy in range(1, 4):
    for ix in range(1, 4):
        p = C.IN / f'matched/captures/patch-{iy}-{ix}'
        e, e6 = Estimator(42, 32), W6Estimator(42, 32)
        for cp in p.glob('c2-i*-candidate.bin'):
            it = cp.name.split('-')[1]
            cand = np.frombuffer(cp.read_bytes(), '<f8').reshape(5, 2)
            for f in range(5):
                m = np.frombuffer((p/f'c2-{it}-map-f{f}.bin').read_bytes(), '<f4').reshape(32, 42)
                worst = max(worst, float(np.abs(e.peak(m)-cand[f]).max()))
                worst6 = max(worst6, float(np.abs(e6.peak(m)-cand[f]).max()))
checks['stored_float32_peak_replay_max_px'] = worst
checks['stored_float32_peak_replay_w6_flags_off_max_px'] = worst6
assert worst <= 1e-6 and worst6 <= 1e-6

identity = dict(max_abs_px=0., runs=0)


def run_global(F, it, tol, domain, arm, weight='prod', truth=None):
    coupled, dc = ARMS[arm]
    e = W6Estimator(weight=weight, map32=DOMAINS[domain], coupled=coupled, dc=dc)
    rr = e.run(F, it, tol, truth=truth)
    if arm == 'S-P':
        # Control 2: W6 with both flags off must equal the unmodified lib Estimator bit for bit.
        ref = Estimator(weight=weight, map32=DOMAINS[domain]).run(F, it, tol, truth=truth)
        gap = float(np.abs(ref['state']-rr['state']).max())
        identity['max_abs_px'] = max(identity['max_abs_px'], gap)
        identity['runs'] += 1
        assert gap == 0.
    return rr, e.guard


# Fixtures through the round-2 offline pipeline.
cases = {}
fixture_repro = 0.
for case in ('zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated'):
    movie, target, truth = C.fixture(case)
    recipe = C.generator.recipe(case)
    local = case in ('affine', 'pedestal', 'noisy')
    rec = dict(role=recipe['role'], identifiable=recipe['signal'] not in ('flat', 'repeated'), rows={})
    F = np.fft.fft2(movie.astype(float))/(128*96)
    for domain in DOMAINS:
        for stop, (it, tol) in STOPS.items():
            for arm in ARMS:
                gr, guard = run_global(F, it, tol, domain, arm)
                g = gr['state']
                variants = [('framework', it, tol)]
                if local and stop == '50it':
                    variants.append(('patch-native', 50, .5))
                aligned = None
                if local:
                    sh = Estimator()
                    aligned = np.array([np.fft.ifft2(sh.shift(F[f], g[f])).real*(128*96) for f in range(5)])
                for variant, pit, ptol in variants:
                    cc, localinfo = (patch_fit(aligned, pit, ptol, gain=1., map32=DOMAINS[domain])
                                     if local else (None, {}))
                    key = f'{domain}-{arm}-{stop}' + ('' if variant == 'framework' else '-patch-native')
                    rr = field_result('w6-'+case+'-'+key, g, cc, truth, movie, target, recipe)
                    rr.update(domain=domain, arm=arm, stop=stop, patch_variant=variant,
                              global_run=serial(gr), guard=guard, local=localinfo,
                              acceptance=rr['runtime']['verdict'] if rec['identifiable'] else 'UNIDENTIFIABLE')
                    if arm == 'S-P' and variant == 'framework':
                        # Validation: reproduce the round-2 gain-1 arm (trajectory, coefficients, scores).
                        ref = old['cases'][case]['arms'][f'{domain}-gain1-{stop}']
                        gap = float(np.abs(np.array(ref['global_trajectory'])-g).max())
                        if ref['coefficients'] is not None or cc is not None:
                            gap = max(gap, float(np.abs(np.array(ref['coefficients'])-cc).max()))
                        for s in ('runtime', 'STAR'):
                            gap = max(gap, max(abs(ref[s][k]-rr[s][k]) for k in ('rms', 'p95', 'max')))
                            assert ref[s]['verdict'] == rr[s]['verdict']
                        fixture_repro = max(fixture_repro, gap)
                        assert gap <= 1e-5, (case, key, gap)
                    rec['rows'][key] = rr
    cases[case] = rec
    print(case, {k: (v['runtime']['rms'], v['STAR']['rms']) for k, v in rec['rows'].items()}, flush=True)
checks['fixture_baseline_reproduction_max'] = fixture_repro

# Phase-ramp controls, both domains.
E = Estimator()
_, target, _ = C.fixture('integer')
Ft = np.fft.fft2(target.astype(float))/(128*96)
probes = {}
probe_repro = 0.
ramps = {}
for iv, vel in enumerate(((-1., 2.), (-.8125, .53125))):
    for N in (5, 9, 13, 20):
        t = np.arange(N)[:, None]*np.array(vel)
        F = np.array([E.shift(Ft, -x) for x in t])
        ramps[(iv, N)] = (F, t)
        truth = np.broadcast_to(t[:, None, None], (N, 96, 128, 2))
        for weight in ('prod', 'iso'):
            for domain in DOMAINS:
                for stop, (it, tol) in STOPS.items():
                    for arm in ARMS:
                        key = f'vel{iv}-N{N}-{weight}-{domain}-{arm}-{stop}'
                        rr, guard = run_global(F, it, tol, domain, arm, weight=weight, truth=t)
                        if arm == 'S-P' and domain == 'double':
                            ref = np.array(old['probes'][f'vel{iv}-N{N}-{weight}-gain1-{stop}']['global_trajectory'])
                            gap = float(np.abs(ref-rr['state']).max())
                            probe_repro = max(probe_repro, gap)
                            assert gap <= 1e-5, (key, gap)
                        out = field_result('w6-'+key, rr['state'], None, truth)
                        out.update(domain=domain, arm=arm, stop=stop, weight=weight, run=serial(rr), guard=guard,
                                   trajectory_error_px=C.metrics(rr['state']-t))
                        probes[key] = out
checks['phase_baseline_reproduction_max_px'] = probe_repro
checks['w6_flags_off_vs_lib_identity'] = identity
harm_base = old['harmful_counterexample']['5']['baseline_rms_px']
checks['harmful_baseline_rms_px'] = probes['vel1-N20-iso-double-S-P-5it']['trajectory_error_px']['rms']
assert abs(checks['harmful_baseline_rms_px']-harm_base) <= 1e-6


# Jacobians of the simultaneous anchored map at truth (same construction as round-2 e1_characterize).
def jacobian(F, t, domain, arm, weight):
    coupled, dc = ARMS[arm]
    e = W6Estimator(weight=weight, map32=DOMAINS[domain], coupled=coupled, dc=dc)

    def M(s):
        return s+e.update(np.array([e.shift(f, x) for f, x in zip(F, s)]))
    eps = 1e-3
    n = 2*(len(t)-1)
    J = np.zeros((n, n))
    for i in range(n):
        d = np.zeros_like(t)
        d[1+i//2, i % 2] = eps
        J[:, i] = ((M(t+d)-M(t-d))/(2*eps))[1:].ravel()
    ev = np.linalg.eigvals(J)
    return dict(jacobian=J.tolist(), eigenvalues=sorted([[float(x.real), float(x.imag)] for x in ev]),
                spectral_radius=float(np.abs(ev).max()), guard=e.guard)


jac = {}
for iv in (0, 1):
    F, t = ramps[(iv, 5)]
    for domain in DOMAINS:
        for arm in ARMS:
            jac[f'vel{iv}-N5-prod-{domain}-{arm}'] = jacobian(F, t, domain, arm, 'prod')
    ref = np.array(char['cases'][f'phase-vel{iv}']['jacobian'])
    gap = float(np.abs(ref-np.array(jac[f'vel{iv}-N5-prod-double-S-P']['jacobian'])).max())
    checks[f'jacobian_vel{iv}_double_SP_vs_round2_max'] = gap
    assert gap <= 1e-6
F, t = ramps[(0, 5)]
for arm in ARMS:
    jac[f'vel0-N5-iso-double-{arm}'] = jacobian(F, t, 'double', arm, 'iso')
for N in (9, 13, 20):
    F, t = ramps[(0, N)]
    for weight in ('prod', 'iso'):
        for arm in ('S-P', 'H-P'):
            jac[f'vel0-N{N}-{weight}-double-{arm}'] = jacobian(F, t, 'double', arm, weight)
print('jacobian', {k: (v['spectral_radius'], v['eigenvalues'][0][0], v['eigenvalues'][-1][0]) for k, v in jac.items()},
      flush=True)

out = dict(kind='W6 offline DCg+H2g, global only, gain 1; NumPy replay, native/CUDA UNRUN',
           checks=checks, cases=cases, probes=probes, jacobians=jac, elapsed_s=time.time()-started,
           python=sys.version, numpy=np.__version__,
           script_hashes={p.name: sha(p.read_bytes()) for p in sorted((W6/'scripts').glob('*.py'))},
           framework_pins=PINS, input_manifest_sha256=sha((W5/'round2/INPUTS.json').read_bytes()))
p = W6/'results/w6.json'
assert not p.exists(), str(p)
p.write_text(json.dumps(out, indent=1, allow_nan=False)+'\n')
print('checks', json.dumps(checks), flush=True)
