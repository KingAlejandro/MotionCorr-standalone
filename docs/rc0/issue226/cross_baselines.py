#!/usr/bin/env python3
"""Compare each candidate's unconstrained products against c8844894."""
import argparse
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('mode', choices=['d2', 'd3'])
a = p.parse_args()
w = Path('/mnt/clathrin/alex-motioncorr-226')
rows = ([('e10216', 'L', 'auto', '8.5'), ('e10441', 'L', 'auto', '37.5'),
         ('e10474f4', 'L', 'auto', '19')] if a.mode == 'd2' else
        [('e10441', cfg, ingest, '22') for cfg in ['G', 'L'] for ingest in ['auto', 'float']])
arm = 'runs-d2-bb348554' if a.mode == 'd2' else 'runs-d3'
records = []
for family, config, ingest, point in rows:
    key = f'{family}-{config}-{ingest}'
    output = w / 'logs' / f'cross-{a.mode}-{key}.json'
    cmd = ['/home/alex/.mc-venv/bin/python3', '-I',
           str(w / 'base/docs/issue85_laneC/compare_output_trees.py'),
           str(w / 'runs-base' / (key + '@none') / 'out'),
           str(w / arm / (key + '@none') / 'out'),
           '--manifest', str(w / arm / (key + '@' + point) / 'manifest.json'),
           '--input-star', str(w / 'inputs' / family / 'movies.star'),
           '--products-only', '--json-out', str(output)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    records.append({'case': key, 'command': cmd, 'exit': r.returncode,
                    'stdout': r.stdout, 'stderr': r.stderr})
(w / 'logs' / f'cross-{a.mode}.json').write_text(json.dumps(records, indent=2) + '\n')
print([(r['case'], r['exit']) for r in records])
raise SystemExit(any(r['exit'] != 0 for r in records))
