#!/usr/bin/env python3
"""CPU baseline driver for the workload corpus (issue #186).

For each family: one discarded warm-up run, then rounds of interleaved arms. An arm is
a cell (alignment config G|L x --j 1|4|8 with its cpuset) plus a kind (unprofiled, or
with --profile). Each round runs every cell unprofiled once, and the first
--prof-reps rounds also run every cell profiled once, in a shuffled order (fixed seed
per family and round), so drift does not fall on one arm.

The driver holds /tmp/motioncorr-cpu64-bench.lock (flock on the shared file, never
deleted) for one block of work at a time (a warm-up, or one round of a family) and
releases it between blocks. Every run is wrapped in /usr/bin/time -v, is timed with CLOCK_MONOTONIC from outside,
and records foreign CPU load on the lane from /proc/stat deltas. The run must exit 0 and
produce one *.mrc per movie. Products are deleted except the first unprofiled j8 run
per (family, config), whose tree is hashed.

Results are appended to RESULTS/runs.jsonl; a rerun skips arms already recorded ok and
unflagged, so a flagged run (foreign load on the lane) is repeated and the analyser
ignores the flagged record.
"""
import argparse
import fcntl
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

LOCK = '/tmp/motioncorr-cpu64-bench.lock'
CELLS = {1: '0', 4: '0-3', 8: '0-7'}   # j -> cpuset, all on NUMA node 0
CONFIGS = ('G', 'L')
MAX_HOLD_S = 5400                      # per-run-lock: longest single lock hold (90 min)
QUIET_HOLD_S = 600                     # per-run-lock: longest wait for a quiet lane while holding the lock
SETTLE_BUSY_CORES = 0.25               # lane must be this quiet before a run starts
SETTLE_MAX_S = 300                     # overridden by --settle-max


def lane_cpus(spec):
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += range(int(a), int(b or a) + 1)
    return out


def read_stat(cpus):
    busy = 0
    want = {'cpu%d' % c for c in cpus}
    with open('/proc/stat') as f:
        for line in f:
            p = line.split()
            if p[0] in want:
                v = list(map(int, p[1:9]))      # user nice system idle iowait irq softirq steal
                busy += v[0] + v[1] + v[2] + v[5] + v[6] + v[7]
    return busy / os.sysconf('SC_CLK_TCK')


CCD = list(range(8))    # cpus 0-7: the j8 lane. The j1 and j4 lanes sit inside it.


def node_quiet(max_busy_cores, window=10.0):
    """Busy cores on cpus 0-7 over a window. A j1 or j4 run is checked against all of 0-7, not just
    its own lane, because foreign jobs on neighbouring cores slow it down without showing in
    lane-only counters (the guest reports one L3 for cpus 0-31)."""
    cpus = CCD
    b0, t0 = read_stat(cpus), time.monotonic()
    time.sleep(window)
    busy = (read_stat(cpus) - b0) / (time.monotonic() - t0)
    return busy <= max_busy_cores, busy


class Lock:
    def __init__(self):
        self.fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o666)   # O_CLOEXEC is the python default
        self.waited = 0.0

    def __enter__(self):
        # Blocking acquire: other users take this lock with blocking flock(1), which wins every
        # handoff against a polling client and starves it. This enters the kernel wait queue too.
        t0 = time.monotonic()
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        if os.fstat(self.fd).st_ino != os.stat(LOCK).st_ino:
            raise SystemExit('lock file replaced while waiting (split mutex)')
        self.waited = time.monotonic() - t0
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fd, fcntl.LOCK_UN)


TIME_FIELDS = [
    ('user_s', r'User time \(seconds\): ([\d.]+)', float),
    ('sys_s', r'System time \(seconds\): ([\d.]+)', float),
    ('maxrss_kb', r'Maximum resident set size \(kbytes\): (\d+)', int),
    ('majflt', r'Major \(requiring I/O\) page faults: (\d+)', int),
    ('minflt', r'Minor \(reclaiming a frame\) page faults: (\d+)', int),
    ('vcsw', r'Voluntary context switches: (\d+)', int),
    ('ivcsw', r'Involuntary context switches: (\d+)', int),
    ('fs_out_blocks', r'File system outputs: (\d+)', int),
    ('exit_status', r'Exit status: (\d+)', int),
]


def parse_time(text):
    out = {}
    for key, rx, cast in TIME_FIELDS:
        m = re.search(rx, text)
        out[key] = cast(m.group(1)) if m else None
    return out


def build_cmd(fam, cfg, j, cpus, outdir, profile):
    opts = ['--i', 'movies.star', '--o', outdir + '/', '--use_own', '--j', str(j),
            '--dose_weighting', '--dose_per_frame', repr(fam['dose']),
            '--bfactor', '150', '--seed', '1', '--expected_frames', str(fam['frames'])]
    if cfg == 'L':
        opts += ['--patch_x', '5', '--patch_y', '5']
    if fam.get('gain'):
        opts += ['--gainref', fam['gain_link']]
    if fam['container'].startswith('EER'):
        opts += ['--eer_grouping', str(fam['eer_grouping']), '--eer_upsampling', '1']
    opts += list(fam.get('extra_options', []))      # families-formats.json, e.g. gain orientation
    if profile:
        opts += ['--profile', profile]
    return opts


def count_products(root):
    return sum(1 for _ in Path(root).rglob('*.mrc'))


def tree_hashes(root):
    out = {}
    for p in sorted(Path(root).rglob('*')):
        if not p.is_file():
            continue
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda: f.read(8 << 20), b''):
                h.update(b)
        rec = {'bytes': p.stat().st_size, 'sha256': h.hexdigest()}
        if p.suffix == '.mrc':       # payload hash: the header carries a timestamp label
            with p.open('rb') as f:
                hdr = f.read(1024)
                nsymbt = int.from_bytes(hdr[92:96], 'little')
                f.seek(1024 + nsymbt)
                ph = hashlib.sha256()
                for b in iter(lambda: f.read(8 << 20), b''):
                    ph.update(b)
            rec['payload_sha256'] = ph.hexdigest()
        out[str(p.relative_to(root))] = rec
    return out


def run_one(a, fam, cfg, j, kind, rep, keep, lock_wait_s):
    cpus = CELLS[j]
    lane = lane_cpus(cpus)
    tag = '%s-%s-j%d-%s-r%d' % (fam['id'], cfg, j, kind, rep)
    cdir = Path(a.corpus) / fam['id']
    outdir = 'out/' + tag
    res_dir = Path(a.results) / fam['id']
    res_dir.mkdir(parents=True, exist_ok=True)
    profile = None
    if kind == 'prof':
        profile = str(res_dir / (tag + '.jsonl'))
        if os.path.exists(profile):
            os.unlink(profile)
    timefile = str(res_dir / (tag + '.time'))
    opts = build_cmd(fam, cfg, j, cpus, outdir, profile)
    env_args = ['env', '-u', 'OMP_PROC_BIND', '-u', 'OMP_PLACES', 'OMP_NUM_THREADS=%d' % j]
    cmd = ['/usr/bin/time', '-v', '-o', timefile, 'taskset', '-c', cpus] + env_args + [a.binary] + opts
    shutil.rmtree(cdir / outdir, ignore_errors=True)
    rec = {'family': fam['id'], 'cfg': cfg, 'j': j, 'kind': kind, 'rep': rep, 'cpuset': cpus,
           'omp_num_threads': j, 'omp_proc_bind': 'unset', 'cmd': ' '.join(cmd), 'cwd': str(cdir),
           'nmovies': len(fam['movies'])}
    rec['block_lock_wait_s'] = round(lock_wait_s, 1)
    # settle: wait for the lane to be quiet
    waited = 0.0
    while True:
        b0, t0 = read_stat(lane), time.monotonic()
        time.sleep(2)
        quiet = (read_stat(lane) - b0) / (time.monotonic() - t0)
        if quiet < SETTLE_BUSY_CORES or waited >= SETTLE_MAX_S:
            break
        waited += 2
    rec['settle_wait_s'] = waited
    settle_timeout = quiet >= SETTLE_BUSY_CORES
    if waited:      # who was on the lane (threads on the lane CPUs, by CPU time share)
        ps = subprocess.run(['ps', '-eLo', 'pid,psr,pcpu,user,args', '--sort=-pcpu'],
                            stdout=subprocess.PIPE, universal_newlines=True).stdout.splitlines()
        rec['lane_threads_at_settle'] = [l[:160] for l in ps[1:] if l.split()[1:2] and
                                         int(l.split()[1]) in lane][:5]
    rec['settle_busy_cores'] = round(quiet, 3)
    rec['loadavg'] = os.getloadavg()
    b0 = read_stat(lane)
    c0 = read_stat(CCD)
    t0 = time.monotonic_ns()
    rec['start_epoch'] = time.time()
    proc = subprocess.run(cmd, cwd=cdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t1 = time.monotonic_ns()
    busy = read_stat(lane) - b0
    ccd_busy = read_stat(CCD) - c0
    rec['wall_s'] = (t1 - t0) / 1e9
    rec['rc'] = proc.returncode
    tm = parse_time(Path(timefile).read_text()) if os.path.exists(timefile) else {}
    rec.update(tm)
    own = (tm.get('user_s') or 0) + (tm.get('sys_s') or 0)
    rec['lane_busy_cpu_s'] = round(busy, 2)
    rec['foreign_cpu_s'] = round(busy - own, 2)
    rec['foreign_cores'] = round((busy - own) / rec['wall_s'], 3)
    rec['ccd_foreign_cores'] = round((ccd_busy - own) / rec['wall_s'], 3)   # cpus 0-7, whatever the lane
    rec['flag_foreign'] = (rec['foreign_cores'] > SETTLE_BUSY_CORES or rec['ccd_foreign_cores'] > SETTLE_BUSY_CORES
                           or settle_timeout)
    rec['products'] = count_products(cdir / outdir)
    rec['ok'] = rec['rc'] == 0 and rec['products'] == rec['nmovies']
    (res_dir / (tag + '.log.gz')).write_bytes(__import__('gzip').compress(proc.stdout))
    if keep and rec['ok']:
        th = tree_hashes(cdir / outdir)
        (res_dir / ('tree-%s-%s-j%d.json' % (fam['id'], cfg, j))).write_text(
            json.dumps({'run': tag, 'files': th}, indent=1) + '\n')
        rec['kept_tree'] = str(cdir / outdir)
    else:
        shutil.rmtree(cdir / outdir, ignore_errors=True)
    return rec


def schedule(a, fam):
    cells = [(cfg, j) for cfg in CONFIGS for j in a.js if j not in fam.get('skip_j', [])]
    rounds = []
    for r in range(a.reps):
        rnd = [(cfg, j, 'unprof', r) for cfg, j in cells]
        if r < a.prof_reps:
            rnd += [(cfg, j, 'prof', r) for cfg, j in cells]
        random.Random('%s-%d' % (fam['id'], r)).shuffle(rnd)
        rounds.append(rnd)
    return rounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--families', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--binary', required=True)
    ap.add_argument('--results', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--js', default='1,4,8')
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--prof-reps', type=int, default=2)
    ap.add_argument('--settle-max', type=int, default=300,
                    help='seconds to wait for a quiet lane before a run (a timeout flags the run)')
    ap.add_argument('--per-run-lock', action='store_true',
                    help='repair mode: take the lock per run, run only when node 0 is quiet, '
                         'otherwise release it and retry (never hold the lock while waiting)')
    ap.add_argument('--node-busy-max', type=float, default=0.25,
                    help='per-run-lock: max busy cores on cpus 0-7 before a run starts')
    ap.add_argument('--redo', default='',
                    help='JSON {"gen": N, "arms": [[family,cfg,j,kind,rep],...]}: rerun these arms')
    ap.add_argument('--warmup-only', action='store_true',
                    help='run only the discarded L/j8 warm-up per family (also the budget estimate)')
    a = ap.parse_args()
    a.js = [int(x) for x in a.js.split(',')]
    global SETTLE_MAX_S
    SETTLE_MAX_S = 30 if a.per_run_lock else a.settle_max   # per-run-lock never waits holding the lock
    a.corpus, a.results, a.binary = (os.path.abspath(x) for x in (a.corpus, a.results, a.binary))
    os.sched_setaffinity(0, set(range(60, 64)))      # keep the driver off the measured lanes
    results = Path(a.results)
    results.mkdir(parents=True, exist_ok=True)
    runs = results / 'runs.jsonl'
    done = set()
    if runs.exists():
        for line in runs.read_text().splitlines():
            r = json.loads(line)
            if r.get('ok') and not r.get('flag_foreign'):   # flagged runs are rerun on resume
                done.add((r['family'], r['cfg'], r['j'], r['kind'], r['rep']))
    redo = json.loads(Path(a.redo).read_text()) if a.redo else None
    if redo:
        redo_arms = {tuple(x) for x in redo['arms']}
        done = {k for k in done if k not in redo_arms}
        for line in runs.read_text().splitlines():
            r = json.loads(line)
            k = (r['family'], r['cfg'], r['j'], r['kind'], r['rep'])
            if k in redo_arms and r.get('ok') and not r.get('flag_foreign') and r.get('redo_gen') == redo['gen']:
                done.add(k)
    fams = json.loads(Path(a.families).read_text())['families']
    only = [x for x in a.only.split(',') if x]
    famby = {f['id']: f for f in fams}
    work = []        # (family, item) not yet done, in schedule order
    for fam in fams:
        if only and fam['id'] not in only:
            continue
        blocks = [[('L', 8, 'warmup', 0)]] + ([] if a.warmup_only else schedule(a, fam))
        for block in blocks:
            todo = [i for i in block if (fam['id'], i[0], i[1], i[2], i[3]) not in done]
            if a.per_run_lock:
                work += [(fam, i) for i in todo]
            elif todo:
                # One lock hold per block (a warm-up, or one round of a family): continuous work,
                # released between blocks so other users of the host can interleave.
                with Lock() as lock:
                    for item in todo:
                        execute(a, fam, item, lock.waited, results, runs, redo)
    # Repair mode: one blocking lock hold covers consecutive arms while cpus 0-7 stay quiet
    # (other users' queued jobs take the lock the moment it is released). The hold ends when the
    # lane has not been quiet for QUIET_HOLD_S, or after MAX_HOLD_S.
    t_start = time.monotonic()
    while work:
        with Lock() as lock:
            t_hold = time.monotonic()
            while work and time.monotonic() - t_hold < MAX_HOLD_S:
                t_wait, ok, nb = time.monotonic(), False, None
                while time.monotonic() - t_wait < QUIET_HOLD_S:
                    ok, nb = node_quiet(a.node_busy_max)
                    if ok:
                        break
                if not ok:
                    break
                fam, item = work.pop(0)
                execute(a, fam, item, lock.waited, results, runs, redo)
        if work:
            if time.monotonic() - t_start > a.settle_max:
                print('cpus 0-7 not quiet enough within %ds (last %.2f busy cores); %d arms left' % (
                    a.settle_max, nb or -1, len(work)), flush=True)
                break
            time.sleep(120)


def execute(a, fam, item, lock_wait, results, runs, redo):
    cfg, j, kind, rep = item
    keep = kind == 'unprof' and j == 8 and rep == 0
    rec = run_one(a, fam, cfg, j, kind, rep, keep, lock_wait)
    if redo:
        rec['redo_gen'] = redo['gen']
    with runs.open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print('%s %s j%d %s r%d rc=%d products=%d wall=%.1fs rss=%.2fGiB foreign=%.2f%s' % (
        fam['id'], cfg, j, kind, rep, rec['rc'], rec['products'], rec['wall_s'],
        (rec.get('maxrss_kb') or 0) / 1048576, rec['foreign_cores'],
        ' FLAG' if rec['flag_foreign'] else ''), flush=True)
    if not rec['ok']:
        sys.exit('run failed: %s (see %s)' % (fam['id'], results / fam['id']))


if __name__ == '__main__':
    main()
