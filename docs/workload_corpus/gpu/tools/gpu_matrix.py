#!/usr/bin/env python3
"""GPU characterisation driver for the workload corpus (issue #186), 4GPUs / GPU0.

Built on the profiling kit's library (tools/profiling/lib: runner.run_once, NVML sampler,
HostLock, settle). One run = one motioncorr process with wait4 rusage, NVML VRAM sampling,
a lane/foreign-process check and an --ingest_witness file naming the path each movie took.

Schedule (resumable; an arm already recorded ok and unflagged is skipped):
  warmup  one discarded run per (family, cfg) cell; also the lock-time estimate
  rounds  rep 0..reps-1; per family one lock block holding every cell of that round, shuffled
          (unprofiled in every round, --profile in the first --prof-reps rounds, plus one
          --profile_device_timing 0 run of cfg L in round 0)
  replay  config L (and G with --replay-g), --profile, one movie listed 6 times (labelled replay)
Locks (/tmp/motioncorr-bench.lock then /tmp/motioncorr-gpu0-correctness.lock) are taken per
block and released between blocks. A flagged run (foreign GPU process, foreign CPU on the lane,
affinity or image mismatch) is repeated, up to --attempts; every attempt is recorded.
A failing run is recorded with its log tail and is never retried with other options.

Usage: gpu_matrix.py --phase warmup|rounds|replay --families F.json --corpus DIR --replay DIR
         --binary B --results DIR --kit KITDIR --uuid GPU-... --cpus 96-103 [--only a,b] ...
"""
import argparse
import gzip
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path


def import_kit(kit):
    sys.path.insert(0, kit)
    from lib import provenance as prov, runner  # noqa: E402
    return prov, runner


def payload_args(fam, cfg, variant, witness):
    a = ['--use_own', '--j', '8', '--gpu', '0', '--dose_weighting', '--dose_per_frame', repr(fam['dose']),
         '--bfactor', '150', '--seed', '1', '--expected_frames', str(fam['frames'])]
    if cfg == 'L':
        a += ['--patch_x', '5', '--patch_y', '5']
    if fam.get('gain'):
        a += ['--gainref', fam['gain_link']]
    if fam['container'].startswith('EER'):
        a += ['--eer_grouping', str(fam['eer_grouping']), '--eer_upsampling', '1']
    if variant != 'auto':
        a += ['--ingest', variant]
    a += ['--ingest_witness', witness]
    return a


def inventory(root):
    files = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            files.append((os.path.relpath(p, root), os.path.getsize(p)))
    files.sort()
    return files


def arm_key(r):
    return (r['family'], r['variant'], r['cfg'], r['kind'], r['rep'])


class Driver:
    def __init__(self, a):
        self.a = a
        self.prov, self.runner = import_kit(a.kit)
        self.fams = json.loads(Path(a.families).read_text())['families']
        self.cpus = self.prov.cpu_list(a.cpus)
        self.sampler = self.runner.make_sampler(a.uuid)
        self.results = Path(a.results)
        (self.results / 'logs').mkdir(parents=True, exist_ok=True)
        (self.results / 'profiles').mkdir(exist_ok=True)
        (self.results / 'witness').mkdir(exist_ok=True)
        (self.results / 'movielogs').mkdir(exist_ok=True)
        self.runs = self.results / 'runs.jsonl'
        self.out_root = Path(a.out_root)
        self.out_root.mkdir(parents=True, exist_ok=True)
        self.done, self.failed_cells = set(), set()
        if self.runs.exists():
            for line in self.runs.read_text().splitlines():
                r = json.loads(line)
                if r.get('ok') and not r.get('discard'):
                    self.done.add(arm_key(r))
                if r.get('kind') == 'warmup' and not r.get('ok'):
                    self.failed_cells.add((r['family'], r['variant'], r['cfg']))
        self.env, self.env_changes = self.runner.payload_env(a.uuid, [])
        for k in ('OMP_PROC_BIND', 'OMP_PLACES'):
            self.env.pop(k, None)
        self.env['OMP_NUM_THREADS'] = '8'
        self.free_floor_gib = a.min_free_gib

    # ---------------------------------------------------------------- one arm
    def run_arm(self, fam, variant, cfg, kind, rep, block):
        a = self.a
        cell = (fam['id'], variant, cfg)
        key = (fam['id'], variant, cfg, kind, rep)
        if key in self.done:
            return
        if cell in self.failed_cells and kind != 'warmup':
            print('SKIP (failed in warm-up): %s' % (key,), flush=True)
            return
        replay = kind == 'replay'
        cwd = str((Path(a.replay) if replay else Path(a.corpus)) / fam['id'])
        n_movies = 6 if replay else len(fam['movies'])
        profiled = kind in ('prof', 'prof0', 'replay')
        for attempt in range(1, a.attempts + 1):
            free = shutil.disk_usage('/dev/shm').free / 2 ** 30
            if free < self.free_floor_gib:
                sys.exit('stop: /dev/shm free %.1f GiB < %.1f' % (free, self.free_floor_gib))
            tag = '%s-%s-%s-%s-r%d-a%d' % (fam['id'], variant, cfg, kind, rep, attempt)
            out = str(self.out_root / tag)
            witness = str(self.results / 'witness' / (tag + '.txt'))
            jsonl = str(self.results / 'profiles' / (tag + '.jsonl')) if profiled else None
            for f in (witness, jsonl):
                if f and os.path.exists(f):
                    os.unlink(f)
            extra = ['--profile_device_timing', '0'] if kind == 'prof0' else []
            argv = self.runner.payload_argv(a.binary, payload_args(fam, cfg, variant, witness), 'movies.star', out,
                                            self.cpus, profile=jsonl, profile_args=extra)
            log = str(self.results / 'logs' / (tag + '.log'))
            quiet = self.runner.wait_quiet_lane(self.cpus, a.lane_wait)
            rec = {'family': fam['id'], 'variant': variant, 'cfg': cfg, 'kind': kind, 'rep': rep,
                   'attempt': attempt, 'tag': tag, 'n_movies': n_movies, 'block': block,
                   'lane_before': quiet, 'start_epoch': time.time(), 'ok': False}
            try:
                r = self.runner.run_once(argv, cwd, self.env, log, self.sampler, self.cpus, a.binary, out, n_movies)
                rec.update(r)
                rec['ok'] = True
            except Exception as e:  # rc != 0 or product shortfall
                rec['error'] = str(e)
                rec['log_tail'] = Path(log).read_text(errors='replace').splitlines()[-25:] if os.path.exists(log) else []
            inv = inventory(out) if os.path.isdir(out) else []
            rec['product_files'] = len(inv)
            rec['product_bytes'] = sum(s for _, s in inv)
            if attempt == 1 or not rec['ok']:
                rec['product_inventory'] = inv
            # per-movie logs carry the traced VRAM lines and the decode/ingest witnesses; keep them
            # (compressed) before the product tree is deleted
            with gzip.open(str(self.results / 'movielogs' / (tag + '.log.gz')), 'wt') as fo:
                for name, _ in inv:
                    if name.endswith('.log'):
                        fo.write('##### %s\n' % name)
                        fo.write(Path(out, name).read_text(errors='replace'))
            shutil.rmtree(out, ignore_errors=True)
            wit = {}
            if os.path.exists(witness):
                for line in Path(witness).read_text().splitlines():
                    p = line.rsplit(' ', 1)[-1]
                    wit[p] = wit.get(p, 0) + 1
            rec['ingest_witness'] = wit
            if os.path.exists(log):
                with open(log, 'rb') as fi, gzip.open(log + '.gz', 'wb') as fo:
                    shutil.copyfileobj(fi, fo)
                os.unlink(log)
            discard = (rec.get('flags') or {}).get('discard') or []
            rec['discard'] = discard
            with self.runs.open('a') as f:
                f.write(json.dumps(rec, default=str) + '\n')
            vram = rec.get('vram') or {}
            print('%s rc=%s wall=%.1fs rss=%.2fGiB vram_proc=%s MiB witness=%s%s' % (
                tag, 'ok' if rec['ok'] else 'FAIL', rec.get('wall_s', 0), rec.get('peak_rss_bytes', 0) / 2 ** 30,
                int((vram.get('peak_process_bytes') or 0) / 2 ** 20), wit,
                ('  FLAGGED: ' + '; '.join(discard)) if discard else ''), flush=True)
            if not rec['ok']:
                print('  ' + rec.get('error', ''), flush=True)
                if kind == 'warmup':
                    self.failed_cells.add(cell)
                return
            if not discard:
                self.done.add(key)
                return

    # ---------------------------------------------------------------- one lock block
    def block(self, name, arms):
        todo = [x for x in arms if (x[0]['id'], x[1], x[2], x[3], x[4]) not in self.done]
        if not todo:
            return
        t0 = time.monotonic()
        with self.prov.HostLock(self.a.bench_lock, timeout_s=3600 * 8) as l1, \
                self.prov.HostLock(self.a.gpu_lock, timeout_s=3600 * 8) as l2:
            settle = self.runner.settle(self.sampler, 300)
            held = time.monotonic()
            print('== block %s: locks waited %.0f+%.0f s, settle %s' % (name, l1.waited_s, l2.waited_s, settle), flush=True)
            for fam, variant, cfg, kind, rep in todo:
                self.run_arm(fam, variant, cfg, kind, rep, name)
            with (self.results / 'blocks.jsonl').open('a') as f:
                f.write(json.dumps({'block': name, 'lock_wait_s': [l1.waited_s, l2.waited_s], 'settle': settle,
                                    'held_s': round(time.monotonic() - held, 1), 'arms': len(todo)}) + '\n')
        print('== block %s done, held %.0f s' % (name, time.monotonic() - held), flush=True)

    # ---------------------------------------------------------------- phases
    def families(self):
        only = [x for x in self.a.only.split(',') if x]
        return [f for f in self.fams if not only or f['id'] in only]

    def variants(self, fam):
        return ['auto', 'nvcomp'] if fam['id'] == 'tutorial' else ['auto']

    def phase_warmup(self):
        for fam in self.families():
            self.block('warmup-%s' % fam['id'],
                       [(fam, 'auto', cfg, 'warmup', 0) for cfg in ('L', 'G')])

    def phase_rounds(self):
        fams = self.families()
        for rep in range(self.a.reps):
            order = fams[rep % len(fams):] + fams[:rep % len(fams)] if len(fams) > 1 else fams
            for fam in order:
                arms = [(fam, v, cfg, 'unprof', rep) for v in self.variants(fam) for cfg in ('G', 'L')]
                if rep < self.a.prof_reps:
                    arms += [(fam, v, cfg, 'prof', rep) for v in self.variants(fam)[:1] for cfg in ('G', 'L')]
                if rep == 0:
                    arms += [(fam, 'auto', 'L', 'prof0', 0)]
                random.Random('%s-%d' % (fam['id'], rep)).shuffle(arms)
                self.block('round%d-%s' % (rep, fam['id']), arms)

    def phase_replay(self):
        fams = self.families()
        cfgs = ('L', 'G') if self.a.replay_g else ('L',)
        for rep in range(self.a.replay_reps):
            for fam in fams:
                arms = [(fam, 'auto', cfg, 'replay', rep) for cfg in cfgs]
                self.block('replay%d-%s' % (rep, fam['id']), arms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', required=True, choices=('warmup', 'rounds', 'replay'))
    ap.add_argument('--families', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--replay', required=True)
    ap.add_argument('--binary', required=True)
    ap.add_argument('--results', required=True)
    ap.add_argument('--kit', required=True, help='directory holding lib/ (tools/profiling of main)')
    ap.add_argument('--uuid', required=True)
    ap.add_argument('--cpus', default='96-103')
    ap.add_argument('--out-root', default='/dev/shm/mc-corpus-186/out')
    ap.add_argument('--only', default='')
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--prof-reps', type=int, default=2)
    ap.add_argument('--replay-reps', type=int, default=2)
    ap.add_argument('--replay-g', action='store_true')
    ap.add_argument('--attempts', type=int, default=3)
    ap.add_argument('--lane-wait', type=float, default=300)
    ap.add_argument('--min-free-gib', type=float, default=5.0)
    ap.add_argument('--bench-lock', default='/tmp/motioncorr-bench.lock')
    ap.add_argument('--gpu-lock', default='/tmp/motioncorr-gpu0-correctness.lock')
    a = ap.parse_args()
    a.binary = os.path.abspath(a.binary)
    a.corpus, a.replay, a.results = (os.path.abspath(x) for x in (a.corpus, a.replay, a.results))
    d = Driver(a)
    os.sched_setaffinity(0, {104})     # the driver (idle apart from the NVML sampler) stays off the measured lane 96-103
    getattr(d, 'phase_' + a.phase)()


if __name__ == '__main__':
    main()
