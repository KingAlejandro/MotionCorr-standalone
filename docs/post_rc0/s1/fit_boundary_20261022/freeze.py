#!/usr/bin/env python3
"""Freeze independent rational temporal expectations before any native run.

SPDX-License-Identifier: GPL-2.0-or-later
Only the small retained STAR records are read; no movie or solver is run.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def inverse(a):
    """Exact elimination, only for the independent 3x3 temporal normal matrix."""
    n = len(a)
    a = [list(row) + [F(i == j) for j in range(n)] for i, row in enumerate(a)]
    for i in range(n):
        assert a[i][i]
        pivot = a[i][i]
        a[i] = [x / pivot for x in a[i]]
        for j in range(n):
            if j != i:
                v = a[j][i]
                a[j] = [x - v*y for x, y in zip(a[j], a[i])]
    return [row[n:] for row in a]


def parse(path):
    result = {}; key = None
    for line in path.read_text().splitlines():
        row = line.split('#')[0].split()
        if not row:
            continue
        if row[0].startswith('data_'):
            key = row[0][5:]; result[key] = []
        elif key and row[0] != 'loop_' and not row[0].startswith('_'):
            result[key].append([F(x) for x in row])
    return result


def main():
    z = [F(f) + F(1, 2) for f in range(5)]
    gram = [[sum(t**(i+j+2) for t in z) for j in range(3)] for i in range(3)]
    inv = inverse(gram)
    projection = [[sum(inv[i][j] * t**(j+1) for j in range(3)) for t in z] for i in range(3)]
    records = []
    for case, backend in [('affine', 'cpu'), ('affine', 'cuda'), ('noisy', 'cpu'), ('noisy', 'cuda')]:
        path = ROOT / 'live' / f'{case}-{backend}.star'
        star = parse(path)
        obs = star['local_shift']
        coords = sorted(set((int(row[1]), int(row[2])) for row in obs))
        expected_missing = {('affine', 'cuda'): (20, 47), ('noisy', 'cuda'): (104, 15)}.get((case, backend))
        full = {(x, y) for x in (20, 62, 104) for y in (15, 47, 79)}
        assert set(coords) == full - ({expected_missing} if expected_missing else set())
        assert len(obs) == 5 * len(coords)
        assert all(sorted(int(row[0]) for row in obs if (int(row[1]), int(row[2])) == c) == [1,2,3,4,5] for c in coords)
        design = []
        for x, y in coords:
            x, y = F(x, 128)-F(1,2), F(y, 96)-F(1,2)
            for t in z:
                design.append([float(s*t**k) for s in (1,x,x*x,y,y*y,x*y) for k in (1,2,3)])
        design = np.asarray(design)
        g = [row[1:] for row in star['global_shift']]
        truth_g = [[-F(13,16)*f, F(17,32)*f] for f in range(5)]
        h = [[truth_g[f][a]-g[f][a]+(truth_g[1][a]-g[1][a])/2 for f in range(5)] for a in (0,1)]
        coeff = [[sum(p*v for p,v in zip(row,h[a])) for row in projection] for a in (0,1)]
        errors = [[sum(coeff[a][k]*F(f)**(k+1) for k in range(3))+g[f][a]-truth_g[f][a] for a in (0,1)] for f in range(5)]
        records.append(dict(case=case, backend=backend, member_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            coordinates=coords, rank=int(np.linalg.matrix_rank(design)),
                            condition=float(np.linalg.cond(design)),
                            singular_min=float(np.linalg.svd(design, compute_uv=False)[-1]),
                            globals=[[str(v) for v in row] for row in g],
                            constant_spatial_temporal_coefficients=[[str(v) for v in row] for row in coeff],
                            composed_field_rms_px=float(np.sqrt(float(sum(x*x+y*y for x,y in errors)/5))),
                            composed_field_max_px=float(np.sqrt(float(max(x*x+y*y for x,y in errors))))))
    result = dict(schema='fit-boundary-frozen/1', evidence_head='805d9de27898b4a10e6212e65098d5995a40fdb1',
                  numerical_source='d751ff28594902eca75d665ff116e662653481aa',
                  temporal_projection=[[str(v) for v in row] for row in projection],
                  exact_coefficients={'x3': '-48/125', 'x9': '24/125', 'y3': '-24/125', 'y9': '6/25', 'other': 0},
                  bounds={'coefficient_abs_px': 1e-7, 'field_vector_max_px': 2e-5, 'condition_admission': 6000},
                  records=records, numpy=np.__version__)
    (ROOT/'frozen.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
