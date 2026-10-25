#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Post-calculation geometry of the SAVED oracle result; no estimator rerun."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
raw=(ROOT/'results/challenge.json').read_bytes()
d=json.loads(raw)
rows=[]
for lab,p in d['patches'].items():
    iy,ix=map(int,lab.strip('()').split(','))
    x0,y0=(ix-1)*42,(iy-1)*32
    cx,cy=x0+20,y0+15
    for f in range(1,5):
        e=[p['oracle_reference_trajectory'][f][a]-p['known'][f][a] for a in (0,1)]
        # Known material field slope J = -f/4 A_unit. Exact generator convention.
        a,b,c,z=[-f/4*v for v in (.012,-.008,.006,-.010)]
        det=a*z-b*c
        dx,dy=(z*e[0]-b*e[1])/det,(-c*e[0]+a*e[1])/det
        q=[cx+dx,cy+dy]
        corners=[[a*(x-cx)+b*(y-cy),c*(x-cx)+z*(y-cy)]
                 for x in (x0,x0+41) for y in (y0,y0+31)]
        outside=[e[k]<min(v[k] for v in corners) or e[k]>max(v[k] for v in corners) for k in (0,1)]
        rows.append(dict(patch=lab,frame=f,equivalent_scalar_weight_position=q,
            outside_patch=not(x0<=q[0]<=x0+41 and y0<=q[1]<=y0+31),
            outside_component_range=outside, oracle_minus_centre_px=e))
out=dict(kind='saved-result geometry; computed after factorial, no tuning or estimator execution',
    challenge_sha256=hashlib.sha256(raw).hexdigest(),
    outside_patch_count=sum(r['outside_patch'] for r in rows),
    outside_at_least_one_component_range_count=sum(any(r['outside_component_range']) for r in rows),
    rows=rows,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    interpretation='Outside the patch rules out a single nonnegative scalar content-weighted average of the affine material field. Tensor/signed gradient weighting, finite-window CCF bias, and Eulerian/material sampling mismatch remain possible; no physical effective position is inferred.')
p=ROOT/'results/observation-geometry.json'
assert not p.exists()
p.write_text(json.dumps(out,indent=1)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='rows'}))
