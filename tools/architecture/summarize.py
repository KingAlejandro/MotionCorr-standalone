#!/usr/bin/env python3
"""Summarize the fixed issue #142 campaign; refuse missing/duplicate observations."""
import json
from pathlib import Path
import statistics as stats
import sys

root = Path(sys.argv[1])
shapes = [(256,256,24),(256,256,160),(512,511,25),(1024,768,24),
          (3710,3838,24),(4096,4096,24),(4096,4096,80)]
arms = ['production','mirror_b1','stage_b1','stage_b2','stage_b4']
summary = {'fft': [], 'job_granularity': []}
for x,y,f in shapes:
    rows = [json.loads(line) for line in (root/f'fft-{x}-{y}-{f}.jsonl').read_text().splitlines()]
    expected = {(a,n) for a in arms for n in range(7)}
    assert len(rows)==35 and {(r['arm'],r['round']) for r in rows}==expected
    assert all((r['nx'],r['ny'],r['frames'])==(x,y,f) for r in rows)
    controls = {r['round']:r for r in rows if r['arm']=='production'}
    for arm in arms:
        obs = [r for r in rows if r['arm']==arm]
        times = [r['forward_ms']+r['inverse_ms'] for r in obs]
        savings = [controls[r['round']]['forward_ms']+controls[r['round']]['inverse_ms']-t
                   for r,t in zip(obs,times)]
        exact = sum(r['real_different']==0 and r['fourier_different']==0 for r in obs)
        if arm in arms[:3]:
            assert exact==7, 'batch-one control does not match production'
        summary['fft'].append(dict(shape=[x,y,f], arm=arm, repeats=7, exact_repeats=exact,
            median_ms=stats.median(times), range_ms=[min(times),max(times)],
            paired_saving_ms=stats.median(savings), faster_pairs=sum(v>0 for v in savings),
            median_setup_ms=stats.median(r['setup_ms'] for r in obs),
            owned_bytes=obs[0].get('owned_bytes'), work_bytes=obs[0].get('work_bytes'),
            real_max_abs=max(r['real_max_abs'] for r in obs),
            fourier_max_abs=max(r['fourier_max_abs'] for r in obs)))
rows = [json.loads(line) for line in (root/'job-granularity-gpu/observations.jsonl').read_text().splitlines()]
expected = {(n,g) for n in range(-1,5) for g in (1,2,6)}
assert len(rows)==18 and {(r['round'],r['movies_per_process']) for r in rows}==expected
reference = rows[0]['products']
assert len(reference)==18 and all(r['products']==reference for r in rows)
for group in (1,2,6):
    times = [r['seconds'] for r in rows if r['round']>=0 and r['movies_per_process']==group]
    summary['job_granularity'].append(dict(movies_per_process=group, repeats=len(times),
        median_seconds=stats.median(times), range_seconds=[min(times),max(times)]))
print(json.dumps(summary,indent=2))
