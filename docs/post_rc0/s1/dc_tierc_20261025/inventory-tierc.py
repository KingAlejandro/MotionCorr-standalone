#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only inventory of the frozen #262 Tier C queue on the campaign host.

usage: inventory-tierc.py ROOT OUT.json
Classifies all 816 Tier C queue jobs (exit0 / orphan / unrun / other), pins the
files the unchanged evaluator reads (RUN.json, runtime.json, witness.txt and the
movie MRC/STAR/log) to the sizes and SHA-256 values recorded in each RUN.json,
and partitions the exit-0 records into whole-config batches. It hashes only
RUN.json and queue.json; large payloads are bound by the RUN pins and are
re-hashed by the stager after transfer. Writes nothing under ROOT.
"""
import hashlib, json, sys
from pathlib import Path

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
BATCH_LIMIT = 10 * 2**30
EXPECTED_SOURCE = '3eee0a4b4e367f9b57f950c440c89679a5ec9c93'


def sha(p):
    h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()


queue = json.loads((ROOT / 'queue.json').read_text())
assert (ROOT / 'SOURCE_SHA').read_text().strip() == EXPECTED_SOURCE
jobs = [j for j in queue if j['tier'] == 'C']
records, other, problems = [], [], []
for j in jobs:
    d = ROOT / 'runs' / j['id']
    base = dict(id=j['id'], backend=j['backend'], arm=j['arm'], group=j['group'], config=j['id'].rsplit('-', 2)[0])
    if not d.exists():
        other.append(dict(base, state='NEVER_RUN')); continue
    if (d / 'ADMISSION_FAILED').exists():
        other.append(dict(base, state='ADMISSION_FAILED')); continue
    if not (d / 'RUN.json').exists():
        other.append(dict(base, state='INTERRUPTED_ORPHAN_NO_RUN_JSON',
                          listing=sorted([str(p.relative_to(d)), p.stat().st_size] for p in d.rglob('*') if p.is_file())))
        continue
    r = json.loads((d / 'RUN.json').read_text())
    if r['exit'] != 0:
        other.append(dict(base, state='EXIT_NONZERO', exit=r['exit'])); continue
    if (r['id'], r['tier'], r['backend'], r['arm'], r['source_sha']) != (j['id'], 'C', j['backend'], j['arm'], EXPECTED_SOURCE):
        problems.append(f"RUN identity mismatch {j['id']}")
    pins = r['outputs']
    mrcs = sorted(k for k in pins if k.endswith('.mrc') and not k.endswith(('_PS.mrc', '_noDW.mrc')))
    stars = sorted(k for k in pins if k.endswith('.star') and k != 'corrected_micrographs.star')
    logs = sorted(k for k in pins if k.endswith('.log') and k not in ('stdout.log', 'stderr.log', 'time-v.log'))
    if len(mrcs) != 1 or len(stars) != 1 or len(logs) != 1:
        problems.append(f"product set not 1/1/1 for {j['id']}: {mrcs} {stars} {logs}")
        continue
    # Files the evaluator would see on disk must equal the pinned product set, so that
    # staging a subset cannot change which products find_product()/logs pick.
    on_disk = sorted(str(p.relative_to(d)) for p in d.rglob('*') if p.is_file())
    disk_mrc = [k for k in on_disk if k.endswith('.mrc') and not k.endswith(('_PS.mrc', '_noDW.mrc'))]
    disk_star = [k for k in on_disk if k.endswith('.star') and not k.endswith('corrected_micrographs.star')]
    disk_log = [k for k in on_disk if k.endswith('.log') and Path(k).name not in ('stdout.log', 'stderr.log', 'time-v.log')]
    if (disk_mrc, disk_star, disk_log) != (mrcs, stars, logs):
        problems.append(f"on-disk product set differs from RUN pins for {j['id']}")
    files = [dict(rel='RUN.json', bytes=(d / 'RUN.json').stat().st_size, sha256=sha(d / 'RUN.json'), pin='computed')]
    for rel in ['runtime.json', 'witness.txt', mrcs[0], stars[0], logs[0]]:
        p = d / rel
        pin = pins[rel]
        if p.stat().st_size != pin['bytes']:
            problems.append(f"size differs from RUN pin: {j['id']}/{rel}")
        files.append(dict(rel=rel, bytes=pin['bytes'], sha256=pin['sha256'], pin='RUN.json'))
    records.append(dict(base, state='EXIT0', start_utc=r['start_utc'], end_utc=r['end_utc'], wall_s=r['wall_s_unqualified'],
                        host=r['host'], gpu_witness_uuids=r['gpu_witness_uuids'], files=files,
                        stage_bytes=sum(f['bytes'] for f in files)))

by_config = {}
for rec in records:
    by_config.setdefault(rec['config'], []).append(rec)
batches, cur, cur_bytes = [], [], 0
for cfg in sorted(by_config):
    sz = sum(r['stage_bytes'] for r in by_config[cfg])
    if cur and cur_bytes + sz > BATCH_LIMIT:
        batches.append(cur); cur, cur_bytes = [], 0
    cur.append(cfg); cur_bytes += sz
if cur: batches.append(cur)

counts = {}
for r in records + other:
    k = f"{r['backend']}/{r['state']}"; counts[k] = counts.get(k, 0) + 1
out = dict(root=str(ROOT), source_sha=EXPECTED_SOURCE, queue_sha256=sha(ROOT / 'queue.json'), tierC_jobs=len(jobs),
           counts=counts, problems=problems, batches=[dict(index=i, configs=b, records=sum(len(by_config[c]) for c in b),
                                                          bytes=sum(r['stage_bytes'] for c in b for r in by_config[c])) for i, b in enumerate(batches)],
           total_stage_bytes=sum(r['stage_bytes'] for r in records), records=records, other=other)
OUT.write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(dict(counts=counts, problems=problems[:10], n_problems=len(problems), batches=out['batches'], total_stage_bytes=out['total_stage_bytes'])))
