#!/usr/bin/env python3
"""Paired whole-job driver for the RC0 CPU comparisons (#179, #183; register rows C5/C7).

Measurement only: it runs prebuilt binaries and records every run to runs.jsonl.

Per family: one discarded warm-up per arm (the first A warm-up tree is the product
reference), then ROUNDS rounds. A round is one lock hold and contains, for each
comparison of the family, one pair: A,B in even rounds and B,A in odd rounds, plus one
A,A null pair. A pair with a disturbed run (foreign load on the lane) is repeated once;
both attempts stay in runs.jsonl, the analyser uses the latest undisturbed attempt.

Every run is timed from outside with CLOCK_MONOTONIC (whole process, both movies), wrapped
in /usr/bin/time -v, checked for foreign CPU load from /proc/stat, and its product tree is
compared with the reference tree using tools/profiling/lib/identity.py (MRC header with the
writer clock masked, payload, STAR/EPS byte-identical; .log and .pdf excluded).
"""
import argparse
import fcntl
import gzip
import importlib.util
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
SETTLE_BUSY_CORES = 0.25
SETTLE_MAX_S = 60
OPTS_COMMON = ['--use_own', '--j', '8', '--dose_weighting', '--bfactor', '150', '--seed', '1',
               '--patch_x', '5', '--patch_y', '5']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lane_cpus(spec):
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += range(int(a), int(b or a) + 1)
    return out


def read_stat():
    """Per-cpu busy seconds (everything except idle and iowait)."""
    out = {}
    with open('/proc/stat') as f:
        for line in f:
            p = line.split()
            if p[0].startswith('cpu') and p[0] != 'cpu':
                v = list(map(int, p[1:9]))      # user nice system idle iowait irq softirq steal
                out[int(p[0][3:])] = (v[0] + v[1] + v[2] + v[5] + v[6] + v[7]) / os.sysconf('SC_CLK_TCK')
    return out


def ps_top(n=6):
    ps = subprocess.run(['ps', '-eLo', 'pid,psr,pcpu,user,comm', '--sort=-pcpu'], stdout=subprocess.PIPE,
                        universal_newlines=True).stdout.splitlines()
    return [l.strip() for l in ps[1:n + 1]]


class Lock:
    def __init__(self):
        self.fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o666)

    def __enter__(self):
        t0 = time.monotonic()
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        if os.fstat(self.fd).st_ino != os.stat(LOCK).st_ino:
            raise SystemExit('lock file replaced while waiting (split mutex)')
        self.waited = time.monotonic() - t0
        self.t_acquired = time.monotonic()
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fd, fcntl.LOCK_UN)


TIME_FIELDS = [('user_s', r'User time \(seconds\): ([\d.]+)', float),
               ('sys_s', r'System time \(seconds\): ([\d.]+)', float),
               ('maxrss_kb', r'Maximum resident set size \(kbytes\): (\d+)', int),
               ('majflt', r'Major \(requiring I/O\) page faults: (\d+)', int),
               ('minflt', r'Minor \(reclaiming a frame\) page faults: (\d+)', int),
               ('exit_status', r'Exit status: (\d+)', int)]


def parse_time(text):
    return {k: (cast(m.group(1)) if (m := re.search(rx, text)) else None) for k, rx, cast in TIME_FIELDS}


def thp():
    try:
        return re.search(r'\[(\w+)\]', Path('/sys/kernel/mm/transparent_hugepage/enabled').read_text()).group(1)
    except OSError:
        return None


class Ctx:
    pass


def build_cmd(fam, ctx):
    opts = ['--i', 'movies.star', '--o', 'out/', '--dose_per_frame', repr(fam['dose']),
            '--expected_frames', str(fam['frames'])] + OPTS_COMMON
    if fam.get('gain'):
        opts += ['--gainref', fam['gain_link']]
    if fam['container'].startswith('EER'):
        opts += ['--eer_grouping', str(fam['eer_grouping']), '--eer_upsampling', '1']
    return opts


def run_one(ctx, fam, arm, tag, role, comp, rnd, attempt, pos):
    """Run one measured arm. Returns the record (already appended to runs.jsonl)."""
    lane = lane_cpus(ctx.mask)
    cwd = ctx.work / fam['id']
    res = ctx.results / fam['id']
    res.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(cwd / 'out', ignore_errors=True)
    timefile = str(res / (tag + '.time'))
    opts = build_cmd(fam, ctx)
    env = ['env', '-u', 'OMP_PROC_BIND', '-u', 'OMP_PLACES', '-u', 'GLIBC_TUNABLES', 'OMP_NUM_THREADS=8']
    cmd = ['/usr/bin/time', '-v', '-o', timefile, 'taskset', '-c', ctx.mask] + env + [ctx.bins[arm]] + opts
    rec = {'tag': tag, 'family': fam['id'], 'arm': arm, 'role': role, 'comp': comp, 'round': rnd,
           'attempt': attempt, 'pos': pos, 'mask': ctx.mask, 'thp': thp(), 'glibc_tunables': os.environ.get('GLIBC_TUNABLES'),
           'binary': ctx.bins[arm], 'binary_sha256': ctx.shas[arm], 'cmd': ' '.join(cmd), 'cwd': str(cwd),
           'nmovies': len(fam['movies']), 'lock_wait_s': round(ctx.lock_wait, 1)}
    # settle: lane (and the rest of the node 0 neighbourhood) quiet before starting
    waited, quiet = 0, None
    while True:
        s0, t0 = read_stat(), time.monotonic()
        time.sleep(5)
        s1 = read_stat()
        dt = time.monotonic() - t0
        quiet = sum(s1[c] - s0[c] for c in lane) / dt
        if quiet < SETTLE_BUSY_CORES or waited >= SETTLE_MAX_S:
            break
        waited += 5
    rec['settle_wait_s'] = waited
    rec['settle_busy_cores'] = round(quiet, 3)
    rec['settle_timeout'] = quiet >= SETTLE_BUSY_CORES
    rec['ps_before'] = ps_top()
    rec['loadavg'] = os.getloadavg()
    s0 = read_stat()
    t0 = time.monotonic_ns()
    rec['start_epoch'] = time.time()
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t1 = time.monotonic_ns()
    s1 = read_stat()
    rec['ps_after'] = ps_top()
    rec['wall_s'] = (t1 - t0) / 1e9
    rec['rc'] = proc.returncode
    rec.update(parse_time(Path(timefile).read_text()) if os.path.exists(timefile) else {})
    own = (rec.get('user_s') or 0) + (rec.get('sys_s') or 0)
    busy = {c: s1[c] - s0[c] for c in s1}
    lane_busy = sum(busy[c] for c in lane)
    rec['foreign_lane_cores'] = round((lane_busy - own) / rec['wall_s'], 3)
    # busy cores outside the lane (excluding the driver's own cpus 60-63): where the neighbours sit
    others = {c: round(busy[c] / rec['wall_s'], 2) for c in busy if c not in lane and c < 60 and busy[c] / rec['wall_s'] > 0.25}
    rec['foreign_other_cpus'] = others
    rec['foreign_other_cores'] = round(sum(others.values()), 2)
    rec['flag_foreign'] = rec['foreign_lane_cores'] > SETTLE_BUSY_CORES or rec['settle_timeout']
    (res / (tag + '.log.gz')).write_bytes(gzip.compress(proc.stdout))
    out = cwd / 'out'
    rec['products'] = sum(1 for _ in out.rglob('*.mrc')) if out.exists() else 0
    rec['ok'] = rec['rc'] == 0 and rec['products'] == rec['nmovies']
    # product identity against the family reference tree (not timed)
    ref = ctx.refs / fam['id']
    keep = ctx.trees / fam['id'] / tag
    if rec['ok']:
        if not ref.exists():
            ref.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(out), str(ref))
            rec['identity'] = {'reference': True}
            rec['identical'] = True
        else:
            cmp = ctx.identity.compare_trees(str(ref), str(out), expect_mrc=rec['nmovies'])
            rec['identity'] = {k: cmp[k] for k in ('identical', 'problems', 'differences', 'only_a', 'only_b',
                                                  'compared', 'mrc_compared', 'excluded')}
            rec['identical'] = cmp['identical']
            if cmp['identical']:
                shutil.rmtree(out, ignore_errors=True)
            else:
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(out), str(keep))
                rec['kept_tree'] = str(keep)
    else:
        shutil.rmtree(out, ignore_errors=True)
    with ctx.runs.open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print('%s %s %s r%s a%s rc=%d wall=%.2fs foreign_lane=%.2f other=%.2f%s%s' % (
        fam['id'], tag, role, rnd, attempt, rec['rc'], rec['wall_s'], rec['foreign_lane_cores'],
        rec['foreign_other_cores'], ' FLAG' if rec['flag_foreign'] else '',
        '' if rec.get('identical', False) else ' PRODUCT-DIFF/FAIL'), flush=True)
    if not rec['ok']:
        raise SystemExit('run failed: %s' % tag)
    return rec


def setup_workdir(ctx, fam):
    cwd = ctx.work / fam['id']
    cwd.mkdir(parents=True, exist_ok=True)
    src = ctx.corpus / fam['id']
    for name in ('Movies', fam.get('gain_link') or ''):
        if name and not (cwd / name).exists():
            (cwd / name).symlink_to(src / name)
    shutil.copy(src / 'movies.star', cwd / 'movies.star')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--families', required=True)
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--mask', required=True)
    ap.add_argument('--plan', required=True, help="JSON {family: [comparison arms]} e.g. {\"e10216\": [\"179\", \"183\"]}")
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--only', default='')
    ap.add_argument('--smoke', action='store_true', help='one A run per family, no pairs')
    a = ap.parse_args()
    ctx = Ctx()
    root = Path(a.root)
    ctx.mask, ctx.corpus = a.mask, Path(a.corpus)
    ctx.work, ctx.results, ctx.refs, ctx.trees = root / 'work', root / 'results', root / 'refs', root / 'trees'
    ctx.runs = ctx.results / 'runs.jsonl'
    ctx.bins = {arm: str(root / ('build-%s' % arm) / 'motioncorr') for arm in ('A', '179', '183')}
    ctx.shas = {arm: subprocess.run(['sha256sum', b], stdout=subprocess.PIPE, universal_newlines=True).stdout.split()[0]
                for arm, b in ctx.bins.items()}
    ctx.identity = load(str(root / 'src-A/tools/profiling/lib/identity.py'), 'mc_identity')
    os.sched_setaffinity(0, set(range(60, 64)))      # keep the driver off the measured lane
    plan = json.loads(a.plan)
    fams = {f['id']: f for f in json.loads(Path(a.families).read_text())['families']}
    done = set()
    if ctx.runs.exists():
        for line in ctx.runs.read_text().splitlines():
            r = json.loads(line)
            done.add((r['family'], r['role'], r['comp'], r['round'], r['attempt'], r['pos']))
    only = [x for x in a.only.split(',') if x]
    for fid, comps in plan.items():
        if only and fid not in only:
            continue
        fam = fams[fid]
        setup_workdir(ctx, fam)
        arms = ['A'] + comps
        # warm-ups: one per arm, discarded. The first A warm-up is the reference tree.
        todo = [x for x in arms if (fid, 'warmup', x, 0, 0, 0) not in done]
        if a.smoke:
            todo = ['A']
        if todo:
            with Lock() as lock:
                ctx.lock_wait = lock.waited
                for arm in todo:
                    run_one(ctx, fam, arm, '%s-warmup-%s' % (fid, arm), 'warmup', arm, 0, 0, 0)
        if a.smoke:
            continue
        for rnd in range(a.rounds):
            for attempt in (0, 1):
                # pairs of this round that still need (this attempt of) running
                pairs = []
                for comp in comps + ['null']:
                    if attempt == 1:
                        # repeat only pairs whose attempt 0 was disturbed or failed identity/timing
                        recs = [json.loads(l) for l in ctx.runs.read_text().splitlines()]
                        mine = [r for r in recs if r['family'] == fid and r['comp'] == comp and r['round'] == rnd
                                and r['attempt'] == 0 and r['role'] == 'pair']
                        if not any(r['flag_foreign'] for r in mine):
                            continue
                    if (fid, 'pair', comp, rnd, attempt, 1) in done:
                        continue
                    pairs.append(comp)
                if not pairs:
                    continue
                random.Random('%s-%d-%d' % (fid, rnd, attempt)).shuffle(pairs)
                with Lock() as lock:
                    ctx.lock_wait = lock.waited
                    for comp in pairs:
                        seq = ('A', 'A') if comp == 'null' else (('A', comp) if rnd % 2 == 0 else (comp, 'A'))
                        for pos, arm in enumerate(seq):
                            run_one(ctx, fam, arm, '%s-%s-r%d-a%d-%d%s' % (fid, comp, rnd, attempt, pos, arm),
                                    'pair', comp, rnd, attempt, pos)
                        # a pair record needs both positions
                        done.add((fid, 'pair', comp, rnd, attempt, 1))


if __name__ == '__main__':
    main()
