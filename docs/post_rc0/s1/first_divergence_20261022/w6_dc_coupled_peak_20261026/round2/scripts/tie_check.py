#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Post-hoc (written after mech.json was seen; not frozen): is the P5 iteration-1 difference a replay defect?

Checks, on the zero-start iteration-1 double maps:
- vel0 rows: whether the flipped frames' top two CCF maxima are tied in exact arithmetic
  (the map is symmetric about the leave-one-out centroid) and differ only at rounding level.
- pedestal fixture: the expected rounding scale of the parabolic peak, eps*|m0|/|d|.
No estimator result is changed.
"""
import ast
import json
from pathlib import Path
import sys

W2 = Path(__file__).resolve().parents[1]
W6 = W2.parent
W5 = W6.parent / 'w5_intervention_20261025'
sys.path.insert(0, str(W5 / 'round2/scripts'))
import lib
from lib import np, C, Estimator
lib.verify()
tree = ast.parse((W6/'scripts/w6.py').read_text())
node = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'W6Estimator']
env = dict(Estimator=Estimator, np=np)
exec(compile(ast.Module(body=node, type_ignores=[]), 'w6.py[W6Estimator]', 'exec'), env)
W6Estimator = env['W6Estimator']
EPS = np.finfo(float).eps


def maps(F, weight, dc):
    e = W6Estimator(weight=weight, dc=dc)
    total = F.sum(0)
    out = []
    for f in range(len(F)):
        spec = (total-F[f])*np.conj(F[f])*e.W
        if dc:
            spec[0, 0] = 0
        out.append(np.fft.ifft2(spec).real)
    return e, out


def top2(e, m):
    s = e.indices
    win = m[np.ix_(s % 96, s % 128)]
    order = np.argsort(-win.ravel(), kind='stable')
    i1 = order[0]
    p1 = (int(s[i1 % len(s)]), int(s[i1 // len(s)]))
    # Second-highest local maximum away from the first's 3x3.
    nb = np.stack([np.roll(np.roll(m, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
    ismax = (m[None] >= nb).all(0)[np.ix_(s % 96, s % 128)].ravel()
    for i in order[1:]:
        p = (int(s[i % len(s)]), int(s[i // len(s)]))
        if ismax[i] and max(abs(p[0]-p1[0]), abs(p[1]-p1[1])) > 1:
            return p1, float(win.ravel()[i1]), p, float(win.ravel()[i])


out = {}
E = Estimator()
_, target, _ = C.fixture('integer')
Ft = np.fft.fft2(target.astype(float))/(128*96)
for row, frames in (('vel0-N9-prod', (0, 8)), ('vel0-N13-prod', (6, 12)), ('vel0-N13-iso', (6,))):
    _, N, weight = row.split('-')
    N = int(N[1:])
    t = np.arange(N)[:, None]*np.array((-1., 2.))
    F = np.array([E.shift(Ft, -x) for x in t])
    res = {}
    for dc in (False, True):
        e, ms = maps(F, weight, dc)
        for f in frames:
            m = ms[f]
            a = t[f]-(t.sum(0)-t[f])/(N-1)  # LOO centroid offset; integer or half-integer here
            c2 = np.round(2*a).astype(int)
            # Symmetry about a: m(d) versus m(2a - d) on the whole periodic map.
            refl = m[(c2[1]-np.arange(96)[:, None]) % 96, (c2[0]-np.arange(128)[None, :]) % 128]
            p1, v1, p2, v2 = top2(e, m)
            res[f'frame{f}-{"DC" if dc else "pedestal"}'] = dict(
                centroid_offset=a.tolist(), argmax=p1, value=v1, second=p2, second_value=v2,
                gap=v1-v2, gap_ulps=(v1-v2)/np.spacing(v1), pair_symmetric_about_centroid=bool(p1[0]+p2[0] == c2[0] and p1[1]+p2[1] == c2[1]),
                max_asymmetry=float(np.abs(m-refl).max()), asymmetry_ulps=float(np.abs(m-refl).max()/np.spacing(np.abs(m).max())))
    out[row] = res

movie, _, _ = C.fixture('pedestal')
Fp = np.fft.fft2(movie.astype(float))/(128*96)
e, ms = maps(Fp, 'prod', False)
scale = []
for f, m in enumerate(ms):
    s = e.indices
    i = int(np.argmax(m[np.ix_(s % 96, s % 128)]))
    px, py = int(s[i % len(s)]), int(s[i // len(s)])
    v = m[py % 96, px % 128]
    d = min(abs(m[py % 96, (px+1) % 128]+m[py % 96, (px-1) % 128]-2*v), abs(m[(py+1) % 96, px % 128]+m[(py-1) % 96, px % 128]-2*v))
    scale.append(dict(frame=f, peak_value=float(v), min_second_difference=float(d), rounding_scale_px=float(EPS*abs(v)/d)))
out['pedestal-fixture-iteration1'] = scale
p = W2/'results/tie_check.json'
assert not p.exists()
p.write_text(json.dumps(out, indent=1)+'\n')
print(json.dumps(out, indent=1))
