#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Retain one row per older-SHA/movie/grid/venue, with its required CPU control."""
import argparse
import csv
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('evidence', type=Path)
a = p.parse_args()
rows = []
for path in sorted(a.evidence.rglob('analysis/*-cuda.json')):
    x = json.loads(path.read_text())
    if '-F-cuda' in x['test']:
        continue
    cpu = json.loads(path.with_name(x['reference'] + '.json').read_text())
    run = json.loads((path.parent.parent / 'runs' / x['test'] / 'run.json').read_text())
    rows.append(dict(venue=x.get('venue', '4GPUs'), source=run['source'], movie=x['movie'],
                     grid=int(x['test'].split('-p')[1][0]), cpu_control_identical=cpu['identical'],
                     exact_comparator_exit_status=cpu['exact_comparator_exit_status'],
                     backend_status=x['backend_status'], relative_rmse=x['relative_rmse'],
                     large_s1_screen=x['relative_rmse'] >= .1,
                     cpu_converged=x[x['reference']]['accepted_patches'],
                     cuda_converged=x[x['test']]['accepted_patches'],
                     cpu_only=json.dumps(x['cpu_only_patches']), cuda_only=json.dumps(x['test_only_patches']),
                     evidence=str(path.relative_to(a.evidence))))
with (a.evidence.parent / 'longevity.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
print(len(rows), 'older comparisons;', sum(r['cpu_control_identical'] for r in rows), 'identical CPU controls')
