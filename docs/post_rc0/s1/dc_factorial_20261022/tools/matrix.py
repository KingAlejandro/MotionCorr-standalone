#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Write the complete #262 evidence matrix: one row per frozen queue job.

usage: matrix.py ROOT OUT.csv
Status: EXIT0, EXIT_NONZERO, ADMISSION_FAILED, IN_PROGRESS_OR_ORPHAN, UNRUN.
Process exit is not a scientific result; truth/compatibility verdicts live in
the evaluation files referenced by `evaluation`.
"""
import csv, json, sys
from pathlib import Path

root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
q = json.loads((root / 'queue.json').read_text())
source = (root / 'SOURCE_SHA').read_text().strip()
fields = ['order', 'id', 'tier', 'backend', 'arm', 'build', 'group', 'status', 'exit', 'source_sha', 'binary_sha256',
          'gpu_witness_uuids', 'cpu', 'dc_witness', 'start_utc', 'wall_s_unqualified', 'inputs_sha256', 'evaluation']
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
    for i, j in enumerate(q):
        d = root / 'runs' / j['id']
        row = dict(order=i, id=j['id'], tier=j['tier'], backend=j['backend'], arm=j['arm'], build=j['build'],
                   group=j['group'], source_sha=source)
        if not d.exists(): row['status'] = 'UNRUN'
        elif (d / 'ADMISSION_FAILED').exists(): row['status'] = 'ADMISSION_FAILED'
        elif not (d / 'RUN.json').exists(): row['status'] = 'IN_PROGRESS_OR_ORPHAN'
        else:
            r = json.loads((d / 'RUN.json').read_text())
            assert r['source_sha'] == source
            row.update(status='EXIT0' if r['exit'] == 0 else 'EXIT_NONZERO', exit=r['exit'], binary_sha256=r['binary_sha256'],
                       gpu_witness_uuids=' '.join(r['gpu_witness_uuids']), cpu=r['cpu'], dc_witness=r['dc_witness'] or '',
                       start_utc=r['start_utc'], wall_s_unqualified=r['wall_s_unqualified'],
                       inputs_sha256=' '.join(f'{Path(p).name}={s}' for p, s in sorted(r['inputs'].items())))
            row['evaluation'] = {'A': f'eval/A-{j["backend"]}-{j["arm"]}.json', 'B': f'eval/B/{j["id"]}.json',
                                 'C': 'eval/C-rows.json'}[j['tier']]
        w.writerow(row)
counts = {}
with open(out) as f:
    for r in csv.DictReader(f): counts[(r['tier'], r['backend'], r['status'])] = counts.get((r['tier'], r['backend'], r['status']), 0) + 1
for k in sorted(counts): print(*k, counts[k])
