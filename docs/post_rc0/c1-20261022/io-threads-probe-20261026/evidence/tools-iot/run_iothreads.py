#!/usr/bin/env python3
"""IO-thread-cap probe driver: the profiling kit's own per-process runner (tools/profiling/lib/runner.run_once: GPU sampler, lane/affinity/image checks, run flags)
called in a fixed predeclared order; nothing else is reimplemented. See IO_THREADS_PLAN.md. usage: run_iothreads.py WORK   (locks and pinning are the wrapper's job)"""
import json, os, sys, time
from pathlib import Path
KIT = '/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools/profiling'
sys.path.insert(0, KIT)
from lib import runner, identity   # noqa: E402
import numpy as np                 # noqa: E402
BIN = '/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr'
FIX = '/mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01'
UUID = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
CPUS = list(range(96, 102))
BASE = ['--use_own', '--j', '6', '--patch_x', '5', '--patch_y', '5', '--group_frames', '1', '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW',
        '--first_frame_sum', '1', '--last_frame_sum', '40', '--ingest', 'float', '--gpu', '0']
ORDER = ['6', '1', '1', '6', '6', '2', '2', '6', '6', '4', '4', '6']     # '6' = baseline: no --max_io_threads flag (n_io_threads = --j 6)
PROFILE_ORDER = ['1', '2', '4', '6']
work = Path(sys.argv[1]).resolve(); work.mkdir(parents=True)
staged = runner.stage_input(FIX, 'input.star', None, str(work))
env, _ = runner.payload_env(UUID, [])
sampler = runner.make_sampler(UUID)
recs = []
t_start = time.monotonic()


def go(tag, cap, kind, profile=False):
    out = str(work / 'runs' / tag / 'out'); wit = str(work / 'witness' / (tag + '.txt'))
    os.makedirs(os.path.dirname(wit), exist_ok=True)
    args = BASE + ['--ingest_witness', wit] + ([] if cap == '6' else ['--max_io_threads', cap])
    pj = str(work / 'runs' / tag / 'profile.jsonl') if profile else None
    extra = ['--profile_device_timing', '0'] if profile else []
    argv = runner.payload_argv(BIN, args, staged['star'], out, CPUS, profile=pj, profile_args=extra)
    quiet = runner.wait_quiet_lane(CPUS, 30)
    rec = runner.run_once(argv, staged['cwd'], env, str(work / 'runs' / (tag + '.log')), sampler, CPUS, BIN, out, 1)
    rec.update({'tag': tag, 'cap': cap, 'kind': kind, 'lane_before': quiet, 'profile_jsonl': pj, 't_rel_s': round(time.monotonic() - t_start, 2),
                'witness': Path(wit).read_text().splitlines() if Path(wit).exists() else None})
    recs.append(rec)
    (work / 'runs.jsonl').write_text(''.join(json.dumps(r, default=str) + '\n' for r in recs))
    print('%-6s cap=%s %-9s wall %.3f s cpu %.2f rss %.2f GiB %s' % (tag, cap, kind, rec['wall_s'], rec['cpu_s'], rec['peak_rss_bytes'] / 2**30,
          ('DISCARD ' + ';'.join(rec['flags']['discard'])) if rec['flags']['discard'] else ''), flush=True)


go('W', '6', 'warmup')
for i, cap in enumerate(ORDER, 1):
    go('T%02d-c%s' % (i, cap), cap, 'timed')
timed_end = time.monotonic() - t_start
for cap in PROFILE_ORDER:
    go('P-c%s' % cap, cap, 'profile', profile=True)
# product checks against the first baseline sample (T01)
base = [r for r in recs if r['tag'] == 'T01-c6'][0]['out_dir']
chk = {}
for r in recs:
    d = r['out_dir']
    files = sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d) for f in fs)
    mrc = os.path.join(d, 'movie.mrc'); raw = open(mrc, 'rb').read(); arr = np.frombuffer(raw[1024:], dtype='<f4')
    idt = identity.compare_trees(base, d) if d != base else {'identical': True, 'problems': [], 'compared': None}
    chk[r['tag']] = {'rc': r['rc'], 'n_files': len(files), 'files': files, 'mrc_finite': bool(np.isfinite(arr).all()), 'mrc_nonconstant': bool(arr.std() > 0),
                     'witness': r['witness'], 'identity_vs_T01': {k: v for k, v in idt.items() if k in ('identical', 'problems', 'compared', 'differences')}}
(work / 'checks.json').write_text(json.dumps({'timed_series_wall_s': timed_end, 'total_s': time.monotonic() - t_start, 'checks': chk}, indent=1, default=str))
print('series done: timed %.1f s, total %.1f s' % (timed_end, time.monotonic() - t_start))
