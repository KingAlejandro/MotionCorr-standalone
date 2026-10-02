#!/usr/bin/env python3
"""Re-run only the exact product comparison over already-written application trees."""
import argparse, json, subprocess, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--input-dir', type=Path, required=True)
p.add_argument('--rounds', type=int, required=True)
a = p.parse_args()

manifest = a.source / 'docs/issue85_laneC/tutorial_24_movie_manifest.json'
tool = a.source / 'docs/issue85_laneC/compare_output_trees.py'
out = []
for r in range(1, a.rounds + 1):
    base = a.root / f'prod-{r}' / 'output'
    for arm in ('async', 'graph'):
        js = a.root / f'cmp-{arm}-{r}.json'
        cp = subprocess.run([sys.executable, str(tool), str(base),
                             str(a.root / f'{arm}-{r}' / 'output'),
                             '--manifest', str(manifest),
                             '--input-star', str(a.input_dir / 'movies.star'),
                             '--allow-added-log-line', 'DW submission mode:',
                             '--json-out', str(js)], capture_output=True, text=True)
        status = json.loads(js.read_text()).get('status', '?') if js.exists() else '?'
        out.append({'round': r, 'arm': arm, 'rc': cp.returncode, 'status': status,
                    'stderr': cp.stderr.strip()[-300:]})
        print(json.dumps(out[-1]), flush=True)
(a.root / 'compare.json').write_text(json.dumps(out, indent=2))
print('RECOMPARE_DONE', sum(1 for o in out if o['status'] == 'PASS'), '/', len(out))
