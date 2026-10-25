#!/usr/bin/env python3
"""Synthetic controls for analyze_dc_fourarm.py: known deltas, a limit crossing, a convergence flip and swapped-arm direction."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_dc_fourarm as A

S = A.load_summarize()


def rec(cond, seed, backend, arm, rms, p95=0.1, mx=0.2, conv=True, transfer=0.9):
    return dict(id=f'B-{cond}-s{seed:02d}-{backend}-{arm}', exit=0, arm=arm, backend=backend, status='EVALUATED',
                truth=dict(field=dict(angstrom=dict(rms=rms, p95=p95, max=mx)), convergence=dict(global_converged=conv), local_enabled=True,
                           sampling_status='VALID', field_distance_status='PASS' if rms <= .2 and p95 <= .4 and mx <= .8 else 'FAIL'),
                image=dict(interior=dict(transfer_inband=transfer, bands=[dict(transfer=transfer)])))


# limit crossing: none meets every limit (0.15 A), 'both' crosses the RMS limit on seed 3 only
recs = {}
for s_ in range(10):
    for arm_, v in [('none', 0.15), ('global', 0.15), ('local', 0.15 + (0.01 if s_ % 2 else -0.01)), ('both', 0.25 if s_ == 3 else 0.15)]:
        r = rec('pedestal32', s_, 'cpu', arm_, v); recs[r['id']] = r
out = A.tier_b_analysis(S, recs, np.random.default_rng(1))
cell = {c['arm']: c for c in out['cells'] if c['backend'] == 'cpu'}
assert (cell['local']['wins'], cell['local']['losses']) == (5, 5) and cell['local']['sign_p'] == 1.0, cell['local']
assert cell['global']['ties'] == 10
mat = out['material']
assert len(mat) == 1 and mat[0]['arm'] == 'both' and mat[0]['seed'] == 3 and mat[0]['reasons'] == ['limit_cross:rms'], mat

# direct known-direction control on a clean dataset
recs = {}
for s in range(10):
    for arm, v in [('none', 0.30), ('global', 0.20), ('local', 0.30), ('both', 0.30)]:
        r = rec('pedestal32', s, 'cpu', arm, v + 0.001 * s); recs[r['id']] = r
o = A.tier_b_analysis(S, recs, np.random.default_rng(1))
g = [c for c in o['cells'] if c['arm'] == 'global' and c['backend'] == 'cpu'][0]
assert (g['wins'], g['losses']) == (10, 0) and abs(g['sign_p'] - 2 / 1024) < 1e-12 and g['boot95_median_delta'][1] < 0, g
assert abs(g['median_delta_rms_A'] + 0.10) < 1e-12
# negative control: swapping none and global must flip the verdict
for s in range(10):
    a, b = recs[f'B-pedestal32-s{s:02d}-cpu-none'], recs[f'B-pedestal32-s{s:02d}-cpu-global']
    a['truth']['field']['angstrom'], b['truth']['field']['angstrom'] = b['truth']['field']['angstrom'], a['truth']['field']['angstrom']
o2 = A.tier_b_analysis(S, recs, np.random.default_rng(1))
g2 = [c for c in o2['cells'] if c['arm'] == 'global' and c['backend'] == 'cpu'][0]
assert (g2['wins'], g2['losses']) == (0, 10) and g2['label_raw'] == 'harms' and g2['boot95_median_delta'][0] > 0, g2
# Holm: [0.01, 0.04, 0.03] -> [0.03, 0.06, 0.06]
assert [round(x, 10) for x in A.holm([0.01, 0.04, 0.03])] == [0.03, 0.06, 0.06]

# Tier C: one movie, two grids, convergence flip on cuda-global, agreement worse for global
def arm(conv, rr=None, g=None):
    d = dict(exit=0, convergence=dict(global_converged=conv))
    if rr is not None: d['vs_none'] = dict(relative_rmse=rr, global_rms_px=g, global_max_px=g)
    return d
rows = []
for m in ['e1-00', 'e1-01', 'e2-00', 'e2-01']:
    for grid in ['p3', 'p5']:
        arms = {}
        for b in ['cpu', 'cuda']:
            arms[f'{b}-none'] = arm(True)
            for a in A.VARIANTS: arms[f'{b}-{a}'] = arm(True, 0.01, 0.1)
        arms['cuda-global'] = arm(False, 0.01, 0.1) if (m, grid) == ('e1-00', 'p3') else arms['cuda-global']
        for a in A.ARMS: arms[f'backend-{a}'] = dict(compare_exit=1, relative_rmse=0.02 if a != 'global' else 0.05)
        rows.append(dict(config=f'C-{m}-{grid}', movie=m, grid=grid, arms=arms))
inv = dict(records=[dict(backend='cpu', arm='none', state='EXIT0')], other=[dict(backend='cuda', arm='none', state='NEVER_RUN')])
c = A.tier_c_analysis(rows, inv, np.random.default_rng(1))
ag = {t['arm']: t for t in c['agreement_tests']}
assert (ag['global']['closer'], ag['global']['further']) == (0, 4) and (ag['local']['closer'], ag['local']['further'], ag['local']['ties']) == (0, 0, 4), ag
conv = {(v['backend'], v['arm']): v for v in c['convergence']}
assert conv[('cuda', 'global')]['new'] == 1 and conv[('cpu', 'global')]['new'] == 0 and len(c['harm']) == 1, conv
assert c["graded"] == dict(cpu=32, cuda=32), c["graded"]
print('analyze controls OK')
