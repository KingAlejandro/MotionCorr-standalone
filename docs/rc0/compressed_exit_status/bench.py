#!/usr/bin/env python3
"""#214 end-to-end drain-cost comparison. Caller holds the cpu64 bench lock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--fixed', type=Path, required=True)
p.add_argument('--input', type=Path, required=True)
p.add_argument('--work', type=Path, required=True)
p.add_argument('--reps', type=int, default=7)
a = p.parse_args()
sys.path.insert(0, str(a.source.resolve() / 'tools/profiling'))
sys.path.insert(0, str(a.source.resolve() / 'tests'))
from lib import identity
from test_truncated_mrc_movie import STAR_HEAD

work = a.work.resolve()
work.mkdir(parents=True)
bins = {'baseline': a.baseline.resolve(), 'fixed': a.fixed.resolve()}
records = []

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()

for block in range(-1, a.reps):
    order = ('baseline', 'fixed') if block % 2 else ('fixed', 'baseline')
    outputs = {}
    for arm in order:
        root = work / f'{block}-{arm}'
        root.mkdir()
        (root / 'movie.mrc.xz').symlink_to(a.input.resolve())
        (root / 'movies.star').write_text(STAR_HEAD + 'movie.mrc.xz 1\n')
        out = root / 'out'
        cmd = [str(bins[arm]), '--i', 'movies.star', '--o', str(out) + '/',
               '--use_own', '--j', '8', '--skip_logfile', '--patch_x', '1',
               '--patch_y', '1', '--seed', '1']
        start = time.perf_counter()
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=1200)
        elapsed = time.perf_counter() - start
        (root / 'run.log').write_text(result.stdout + result.stderr)
        record = dict(block=block, warmup=block < 0, arm=arm, command=cmd,
                      rc=result.returncode, seconds=elapsed)
        records.append(record)
        if result.returncode:
            raise RuntimeError(f'{record}: {result.stderr}')
        outputs[arm] = out
    cmp = identity.compare_trees(str(outputs['baseline']), str(outputs['fixed']))
    if not cmp['identical']:
        raise RuntimeError(str(cmp))
    records[-1]['identity'] = cmp
    print(json.dumps(records[-2:]), flush=True)
    (work / 'records.json').write_text(json.dumps(records, indent=2))

samples = {arm: [r['seconds'] for r in records if r['arm'] == arm and not r['warmup']] for arm in bins}
def spread(values):
    q = statistics.quantiles(values, n=4, method='inclusive')
    return dict(median=statistics.median(values), min=min(values), max=max(values),
                q1=q[0], q3=q[2], iqr=q[2]-q[0])
delta = [f-b for f, b in zip(samples['fixed'], samples['baseline'])]
summary = dict(host=platform.node(), platform=platform.platform(),
               affinity=sorted(os.sched_getaffinity(0)), repetitions=a.reps,
               input=str(a.input.resolve()), input_sha256=digest(a.input),
               binaries={arm: dict(path=str(path), sha256=digest(path)) for arm, path in bins.items()},
               samples=samples, summary={arm: spread(v) for arm, v in samples.items()},
               paired_delta_seconds=delta, paired_delta=spread(delta),
               records=records,
               limitation='End-to-end process wall; includes decoding, alignment and writing. Shared host, warm cache. Not isolated finish() latency or a stable performance gate.')
(work / 'summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary['summary']), flush=True)
print(json.dumps(summary['paired_delta']), flush=True)
