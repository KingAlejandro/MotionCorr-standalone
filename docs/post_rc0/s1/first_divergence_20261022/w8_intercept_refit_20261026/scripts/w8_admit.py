#!/usr/bin/env python3
"""W8 census input admission (parent preflight; operators unchanged).
Usage: w8_admit.py RUNS OUT.json -- exit 0 only if RUNS holds exactly the 100 expected movies
(10 conditions x seeds 0-9) with F/runtime.json, F/metrics.json and F/output/movie.star each."""
import hashlib, json, sys
from pathlib import Path
RUNS, OUT = map(Path, sys.argv[1:3])
CONDS = ['dose05', 'dose1', 'dose2', 'dose4', 'pedestal0', 'contrast025', 'contrast4', 'nonsquare', 'outmodel', 'pedestal32']
expected = sorted(f'{c}-s{s:02d}' for c in CONDS for s in range(10))
present = sorted(p.name for p in RUNS.iterdir() if (p/'F').is_dir())
files = ('F/runtime.json', 'F/metrics.json', 'F/output/movie.star')
missing = [f'{n}/{f}' for n in expected for f in files if not (RUNS/n/f).is_file()]
hashes = {f'{n}/{f}': hashlib.sha256((RUNS/n/f).read_bytes()).hexdigest() for n in expected for f in files if (RUNS/n/f).is_file()}
res = dict(n_expected=len(expected), n_present=len(present), names_equal=present == expected,
           per_condition={c: sum(n.startswith(c+'-s') for n in present) for c in CONDS}, missing=missing,
           input_manifest_sha256=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), files=hashes)
res['pass'] = res['names_equal'] and not missing and all(v == 10 for v in res['per_condition'].values())
OUT.write_text(json.dumps(res, indent=1)+'\n')
print(json.dumps({k: v for k, v in res.items() if k != 'files'}))
sys.exit(0 if res['pass'] else 2)
