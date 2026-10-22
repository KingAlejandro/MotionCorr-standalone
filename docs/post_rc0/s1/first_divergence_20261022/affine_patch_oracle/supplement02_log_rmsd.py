#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""POST-HOC check: patch (2,1) RMSD per iteration printed in the retained native
logs (hash-bound through file-index.json) versus the RMSD recomputed from the
captured candidates in attempt02.json. Descriptive; no gate.

usage: supplement02_log_rmsd.py RAW FILE_INDEX ATTEMPT_JSON OUT.json
"""
import hashlib, json, pathlib, re, sys
RAW, INDEX, AJSON, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
index = json.loads(INDEX.read_bytes())['files']
A = json.loads(AJSON.read_text()); res = {}
for backend in ('cpu', 'cuda'):
    rel = f'runs/{backend}-affine-on/out/affine.log'
    raw = (RAW / rel).read_bytes(); assert hashlib.sha256(raw).hexdigest() == index[rel]['sha256']
    text = raw.decode(); block = text.split('Patch (2, 1)', 1)[1].split('\nPatch (', 1)[0].split('[CUDA Patch Alignment Profile]')[0]
    logged = [float(m.group(1)) for m in re.finditer(r'Iteration \d+: RMSD = ([-+.\deE]+) px', block)]
    mine = A['acceptance'][backend]['rmsd']
    res[backend] = dict(log_sha256=index[rel]['sha256'], logged_rmsd=logged, recomputed_rmsd=mine,
                        iterations_equal=len(logged) == len(mine),
                        max_abs_diff=max(abs(a - b) for a, b in zip(logged, mine)) if len(logged) == len(mine) else None,
                        note='CPU log prints 6 significant digits, CUDA 2 decimals')
OUT.write_text(json.dumps(res, indent=1, allow_nan=False) + '\n'); print(json.dumps(res, indent=1))
