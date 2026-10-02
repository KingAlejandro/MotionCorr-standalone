#!/usr/bin/env python3
"""Summarise the complete-application arms: per-arm wall, paired deltas, exactness."""
import json, statistics as st, sys
from pathlib import Path

root = Path(sys.argv[1])
runs = json.loads((root / 'runs.json').read_text())
arms = sorted({r['arm'] for r in runs})
by = {a: {r['round']: r for r in runs if r['arm'] == a} for a in arms}

print(f"{'arm':8s}{'n':>4s}{'median s':>11s}{'min':>9s}{'max':>9s}{'rc!=0':>7s}{'witness logs':>14s}{'foreign':>9s}")
for a in arms:
    v = [r['wall_s'] for r in by[a].values()]
    bad = sum(1 for r in by[a].values() if r['rc'] != 0)
    wit = sorted({r['mode_witness_logs'] for r in by[a].values()})
    frn = sorted({r['foreign_mode_logs'] for r in by[a].values()})
    print(f"{a:8s}{len(v):4d}{st.median(v):11.3f}{min(v):9.3f}{max(v):9.3f}{bad:7d}{str(wit):>14s}{str(frn):>9s}")

base = 'prod'
for a in arms:
    if a == base:
        continue
    d = [by[a][r]['wall_s'] - by[base][r]['wall_s'] for r in by[a] if r in by[base]]
    if d:
        print(f"paired {a} - {base}: median {st.median(d):+.3f} s  "
              f"[{min(d):+.3f},{max(d):+.3f}]  n={len(d)}  faster={sum(1 for x in d if x<0)}")

cmp_path = root / 'compare.json'
if cmp_path.exists():
    cmps = json.loads(cmp_path.read_text())
    for a in sorted({c['arm'] for c in cmps}):
        s = [c['status'] for c in cmps if c['arm'] == a]
        print(f"exact vs prod, {a}: {s.count('PASS')}/{len(s)} PASS  statuses={sorted(set(s))}")
        for c in cmps:
            if c['arm'] == a and c['status'] != 'PASS':
                print(f"   round {c['round']} rc={c['rc']} {c['stderr'][:200]}")
