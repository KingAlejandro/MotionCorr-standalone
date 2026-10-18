#!/usr/bin/env python3
"""W-D10e paired whole-job CPU timing, main vs fix, with interleaved A/A2 nulls.

The declared design is rule.txt next to this file. This driver is the CPU-node adaptation of
W-D10's wd10_pairs.py (the CUDA run): no GPU check; the resource signal is foreign CPU time on
the payload CPUs; N is capped at 128; null blocks follow comparison block floor(j*(N/2)/8); every
run's products are validated; the verdict is computed only on a result that matches the plan.

usage: wd10e_cpu_pairs.py --name W --a BIN --a-sha HEX --b BIN --b-sha HEX --data DIR --cpus 0-15
                          --side 4096 --src SRCTREE --out DIR --keep DIR -- ARGS...
Run the driver itself pinned off the payload CPUs (taskset -c 16-19).
"""
import argparse, datetime, hashlib, json, math, os, shutil, struct, subprocess, sys, threading, time
from pathlib import Path

TARGET_FRAC = 0.005
PILOT_PAIRS, N_MIN, N_MAX, NULL_PAIRS, MAX_ATTEMPTS = 6, 32, 128, 16, 3
Z_MEDIAN = 1.96 * 1.2533
FOREIGN_FRAC = 0.0025           # violation: foreign CPU-s > FOREIGN_FRAC * wall * n_payload_cpus
SAMPLE_S = 0.5
PF_KTHREAD = 0x00200000
TICK = float(os.sysconf('SC_CLK_TCK'))
REQUIRED = ('corrected_micrographs.star', 'Movies/movie1.mrc', 'Movies/movie1.star', 'Movies/movie1.log')


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def parse_cpus(spec):
    out = set()
    for part in spec.split(','):
        lo, _, hi = part.partition('-')
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def siblings(cpus):
    sib = set()
    for c in cpus:
        try:
            sib |= parse_cpus(Path(f'/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list')
                              .read_text().strip())
        except OSError:
            pass
    return sib - cpus


def inventory(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


def check_products(root, side):
    """(problem or None, inventory, MRC payload sha256). Exit code 0 alone is not validity."""
    inv = inventory(root)
    missing = [p for p in REQUIRED if p not in inv]
    if missing:
        return 'missing ' + ','.join(missing), inv, None
    for p in REQUIRED:
        if os.path.getsize(os.path.join(root, p)) == 0:
            return 'empty ' + p, inv, None
    if 'Movies/movie1.mrc' not in Path(root, 'corrected_micrographs.star').read_text():
        return 'corrected_micrographs.star does not list Movies/movie1.mrc', inv, None
    mrc = os.path.join(root, 'Movies/movie1.mrc')
    with open(mrc, 'rb') as f:
        hd = f.read(1024)
        if len(hd) < 1024:
            return 'MRC shorter than its header', inv, None
        nx, ny, nz, mode = struct.unpack('<4i', hd[:16])
        nsymbt = struct.unpack('<i', hd[92:96])[0]
        if (nx, ny, nz, mode) != (side, side, 1, 2):
            return f'MRC header {nx}x{ny}x{nz} mode {mode}', inv, None
        if os.path.getsize(mrc) != 1024 + nsymbt + nx * ny * nz * 4:
            return 'MRC size does not match its header', inv, None
        f.seek(1024 + nsymbt)
        h = hashlib.sha256()
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return None, inv, h.hexdigest()


def snapshot():
    """{(pid, tid): (ticks, sid, last_cpu, is_kthread, comm)} for every thread on the node."""
    snap = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            tids = os.listdir(f'/proc/{pid}/task')
        except OSError:
            continue
        for tid in tids:
            try:
                with open(f'/proc/{pid}/task/{tid}/stat') as f:
                    raw = f.read()
            except OSError:
                continue                    # thread exited between listdir and open
            rp = raw.rfind(')')
            comm = raw[raw.find('(') + 1:rp]
            fl = raw[rp + 2:].split()       # fl[0] is field 3 (state)
            snap[(int(pid), int(tid))] = (int(fl[11]) + int(fl[12]), int(fl[3]), int(fl[36]),
                                          bool(int(fl[6]) & PF_KTHREAD), comm)
    return snap


class Witness:
    """Foreign CPU time during one payload run, from per-thread /proc deltas (additive form).

    The baseline snapshot is taken before the spawn, so CPU used during the run by threads that
    started earlier is counted as foreign, as is any thread created during the run."""

    def __init__(self, payload, sib):
        self.payload, self.sib = payload, sib
        self.sid = None                     # set to the payload's session id after spawn
        self.watch_sid = None               # witness control: the burst's session id
        self.watch_in = self.watch_out = 0.0
        self.prev = snapshot()
        self.foreign = self.kthread = self.sibling = self.outside = 0.0
        self.top = {}
        self.failed = None

    def step(self):
        try:
            cur = snapshot()
        except Exception as e:              # noqa: BLE001 - any sampling failure is a violation
            self.failed = repr(e)
            return
        for key, (ticks, sid, cpu, kth, comm) in cur.items():
            old = self.prev.get(key)
            dt = (ticks - old[0]) if old else ticks
            if dt <= 0 or sid == self.sid:
                continue
            s = dt / TICK
            if sid == self.watch_sid:
                if cpu in self.payload:
                    self.watch_in += s
                else:
                    self.watch_out += s
            if cpu in self.payload:
                if kth:
                    self.kthread += s
                else:
                    self.foreign += s
                    self.top[comm] = self.top.get(comm, 0.0) + s
            elif kth:
                continue
            elif cpu in self.sib:
                self.sibling += s
            else:
                self.outside += s
        self.prev = cur


def size_n(s, target):
    need = math.ceil((Z_MEDIAN * s / target) ** 2) if s > 0 else 0
    n = max(N_MIN, need + (need % 2))
    return min(n, N_MAX), n > N_MAX, need


def main():
    ap = argparse.ArgumentParser()
    for k in ('name', 'a', 'a-sha', 'b', 'b-sha', 'data', 'cpus', 'side', 'src', 'out', 'keep'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('args', nargs=argparse.REMAINDER)
    o = ap.parse_args()
    args = [x for x in o.args if x != '--']
    side = int(o.side)
    sys.path.insert(0, str(Path(o.src) / 'tools' / 'profiling'))
    from lib import stats, identity  # noqa: E402
    payload_cpus = parse_cpus(o.cpus)
    sib = siblings(payload_cpus)
    out = Path(o.out); out.mkdir(parents=True, exist_ok=True)
    runlogs = out / 'runlogs'; runlogs.mkdir(exist_ok=True)
    keep_root = Path(o.keep)
    scratch = Path(os.environ.get('TMPDIR', '/tmp')) / f'wd10e-{o.name}-scratch'
    shutil.rmtree(scratch, ignore_errors=True); scratch.mkdir(parents=True)
    log = open(out / 'runs.jsonl', 'w')
    seq = [0]
    ref_inv = [None]                        # inventory of the first valid run (warm-up A)

    def emit(rec):
        log.write(json.dumps(rec) + '\n'); log.flush()

    def finish_incomplete(reason, extra=None):
        res = {'workload': o.name, 'incomplete': reason, 'd14_label': 'INCOMPLETE', 't_end_utc': utc()}
        res.update(extra or {})
        (out / 'result.json').write_text(json.dumps(res, indent=1))
        emit({'phase': 'end', 'complete': False, 'reason': reason})
        print('RESULT', json.dumps(res), flush=True)
        sys.exit(2)

    # Frozen binaries: the hashes recorded by the job before the driver started.
    for arm, path, want in (('A', o.a, o.a_sha), ('B', o.b, o.b_sha)):
        if sha256(path) != want:
            finish_incomplete(f'binary {arm} hash differs from the frozen value before any run')
    if o.a_sha == o.b_sha:
        finish_incomplete('main and fix binaries are identical')

    def spawn_run(phase, arm, cmd, cwd, dst, burst=None):
        w = Witness(payload_cpus, sib)
        t_utc = utc()
        fo = open(dst / 'stdout.txt', 'w'); fe = open(dst / 'stderr.txt', 'w')
        t0 = time.monotonic()
        p = subprocess.Popen(cmd, cwd=cwd, stdout=fo, stderr=fe, start_new_session=True)
        w.sid = p.pid
        b = None
        if burst is not None:
            b = subprocess.Popen(['taskset', '-c', str(burst), sys.executable, '-c',
                                  'import time\nt=time.time()\nwhile time.time()-t<1.5: pass'],
                                 start_new_session=True)
            w.watch_sid = b.pid

        def sample():                       # off the timing path; driver is on non-payload CPUs
            while p.poll() is None:
                time.sleep(SAMPLE_S)
                w.step()
        th = threading.Thread(target=sample, daemon=True); th.start()
        p.wait()
        wall = time.monotonic() - t0
        th.join()
        fo.close(); fe.close()
        if b is not None:
            b.wait()
        w.step()                            # final interval, after reap
        limit = FOREIGN_FRAC * wall * len(payload_cpus)
        violation = w.failed is not None or w.foreign > limit
        rec = {'seq': seq[0], 'phase': phase, 'arm': arm, 'rc': p.returncode, 'wall_s': round(wall, 4),
               't_start_utc': t_utc, 'foreign_cpu_s': round(w.foreign, 3),
               'foreign_limit_s': round(limit, 3), 'kthread_cpu_s': round(w.kthread, 3),
               'sibling_foreign_cpu_s': round(w.sibling, 3), 'outside_cpu_s': round(w.outside, 3),
               'foreign_top': {k: round(v, 3) for k, v in sorted(w.top.items(), key=lambda x: -x[1])[:5]},
               'sample_failed': w.failed, 'resource_violation': violation}
        if burst is not None:
            rec.update({'burst_cpu': burst, 'burst_cpu_s_on_payload': round(w.watch_in, 3),
                        'burst_cpu_s_elsewhere': round(w.watch_out, 3)})
        return rec

    def run(phase, arm, binary, keep=False):
        seq[0] += 1
        dst = scratch / f'{seq[0]:04d}-{arm}'
        prod = dst / 'out'
        prod.mkdir(parents=True)
        cmd = ['taskset', '-c', o.cpus, binary, '--i', 'movies.star', '--o', str(prod) + '/'] + args
        rec = spawn_run(phase, arm, cmd, o.data, dst)
        problem, inv, payload = check_products(str(prod), side) if rec['rc'] == 0 else ('non-zero exit', None, None)
        if problem is None:
            if ref_inv[0] is None:
                ref_inv[0] = inv
            elif inv != ref_inv[0]:
                problem = 'inventory differs from warm-up A: %s' % sorted(set(inv) ^ set(ref_inv[0]))
        rec.update({'products_valid': problem is None, 'products_problem': problem,
                    'mrc_payload_sha256': payload})
        emit(rec)
        for n in ('stdout.txt', 'stderr.txt'):
            shutil.copyfile(dst / n, runlogs / f'{seq[0]:04d}-{arm}.{n}')
        if not keep:
            shutil.rmtree(dst, ignore_errors=True)
        return rec, prod

    # 0. Witness control: the same code path must see an in-lane burst and ignore an outside one.
    ctl = {}
    for label, burst in (('quiet', None), ('burst_in_lane_cpu5', 5), ('burst_outside_cpu24', 24)):
        seq[0] += 1
        dst = scratch / f'{seq[0]:04d}-ctl'; dst.mkdir()
        ctl[label] = spawn_run('witness-control', label, ['taskset', '-c', o.cpus, 'sleep', '3'],
                               str(scratch), dst, burst)
        emit(ctl[label])
        shutil.rmtree(dst, ignore_errors=True)
    # Attributed by the burst's session id, so host noise cannot satisfy or fail the checks.
    cin, cout = ctl['burst_in_lane_cpu5'], ctl['burst_outside_cpu24']
    ok_in = cin['resource_violation'] and cin['burst_cpu_s_on_payload'] >= 1.0
    ok_out = cout['burst_cpu_s_on_payload'] <= 0.1 and cout['burst_cpu_s_elsewhere'] >= 1.0
    ctl['pass'] = bool(ok_in and ok_out)
    (out / 'witness_control.json').write_text(json.dumps(ctl, indent=1))
    print('witness control', json.dumps(ctl), flush=True)
    if not ctl['pass']:
        finish_incomplete('witness control failed; no timed run')

    def pair(phase, first, second, kind, pos, keep=False):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            r1, d1 = run(phase, *first, keep=keep)
            r2, d2 = run(phase, *second, keep=keep)
            ok = all(r['rc'] == 0 and r['products_valid'] and not r['resource_violation'] for r in (r1, r2))
            emit({'phase': phase, 'pair': kind, 'position': pos, 'order': first[0] + '-' + second[0],
                  'attempt': attempt, 'retained': ok})
            if ok:
                return {first[0]: r1['wall_s'], second[0]: r2['wall_s']}, (d1, d2)
            shutil.rmtree(d1.parent, ignore_errors=True); shutil.rmtree(d2.parent, ignore_errors=True)
        return None, None

    A, B, A2 = ('A', o.a), ('B', o.b), ('A2', o.a)
    t_first_timed = utc()
    for arm in (A, B):
        r, _ = run('warmup', *arm)
        if not (r['rc'] == 0 and r['products_valid']):
            finish_incomplete(f'warm-up {arm[0]} failed: {r["products_problem"]}')

    # Pilot: excluded from the result.
    pilot = []
    for i in range(PILOT_PAIRS):
        first, second = (A, B) if i % 2 == 0 else (B, A)
        w, _ = pair('pilot', first, second, 'AB' if i % 2 == 0 else 'BA', i + 1)
        if w is None:
            (out / 'pilot.json').write_text(json.dumps({'incomplete': True, 'pairs': pilot}, indent=1))
            finish_incomplete(f'pilot pair {i + 1} rejected {MAX_ATTEMPTS} times')
        pilot.append({'order': 'AB' if i % 2 == 0 else 'BA', 'd': w['B'] - w['A'], 'A': w['A'], 'B': w['B']})
    pd = [p['d'] for p in pilot]
    s = 1.4826 * stats.mad(pd)
    m_pilot = stats.median([p['A'] for p in pilot])
    target = TARGET_FRAC * m_pilot
    n, cap_binds, need = size_n(s, target)
    nb = n // 2
    null_after = [(j * nb) // (NULL_PAIRS // 2) for j in range(1, NULL_PAIRS // 2 + 1)]
    design = {'workload': o.name, 'written_utc': utc(), 'pilot_robust_sd_s': s, 'pilot_median_wall_A_s': m_pilot,
              'target_s': target, 'N_required_uncapped': max(N_MIN, need + (need % 2)), 'N': n,
              'N_AB': nb, 'N_BA': nb, 'cap_binds': cap_binds, 'target_expected_reachable': not cap_binds,
              'null_pairs': NULL_PAIRS, 'k_blocks_per_null_block': nb / (NULL_PAIRS // 2),
              'null_block_after_comparison_blocks': null_after,
              'expected_upper_s_at_N': Z_MEDIAN * s / math.sqrt(n),
              'expected_upper_pct_at_N': 100 * Z_MEDIAN * s / math.sqrt(n) / m_pilot}
    (out / 'pilot.json').write_text(json.dumps({'pairs': pilot, 'median_d_s': stats.median(pd),
                                                'robust_sd_s': s, 'median_wall_A_s': m_pilot}, indent=1))
    (out / 'design.json').write_text(json.dumps(design, indent=1))
    print('design', json.dumps(design), flush=True)

    # Definitive: exactly once.
    plan = []
    for blk in range(1, nb + 1):
        plan += [(A, B, 'AB'), (B, A, 'BA')]
        for _ in range(null_after.count(blk)):
            plan += [(A, A2, 'null'), (A2, A, 'null')]
    plan_orders = [f[0] + '-' + s_[0] for f, s_, _ in plan]
    (out / 'plan.json').write_text(json.dumps(plan_orders))
    done, comp, null, walls_a, walls_b, ident, incomplete = [], [], [], [], [], None, None
    t_definitive = utc()
    for pos, (first, second, kind) in enumerate(plan, 1):
        keep = ident is None and kind == 'AB'
        w, dirs = pair('definitive', first, second, kind, pos, keep)
        if w is None:
            incomplete = f'position {pos} ({kind}) rejected {MAX_ATTEMPTS} times'
            break
        done.append((pos, first[0] + '-' + second[0]))
        if kind == 'null':
            null.append({'position': pos, 'order': first[0] + '-' + second[0], 'd': w['A2'] - w['A'],
                         'A': w['A'], 'A2': w['A2']})
        else:
            comp.append({'position': pos, 'order': kind, 'd': w['B'] - w['A'], 'A': w['A'], 'B': w['B']})
            walls_a.append(w['A']); walls_b.append(w['B'])
        if keep:
            ident = identity.compare_trees(str(dirs[0]), str(dirs[1]), expect_mrc=1)
            keep_root.mkdir(parents=True, exist_ok=True)
            for dname in dirs:
                shutil.move(str(dname.parent), str(keep_root / dname.parent.name))
    emit({'phase': 'definitive-end', 'positions_done': len(done), 'positions_planned': len(plan)})

    # Integrity accounting from the run log, by arm.
    runs = [json.loads(line) for line in open(out / 'runs.jsonl') if '"seq"' in line]
    timed = [r for r in runs if r['phase'] != 'witness-control']
    by_arm = {}
    for arm in ('A', 'B', 'A2'):
        rs = [r for r in timed if r['arm'] == arm]
        by_arm[arm] = {'runs': len(rs), 'nonzero_exits': sum(r['rc'] != 0 for r in rs),
                       'invalid_products': sum(r['rc'] == 0 and not r['products_valid'] for r in rs),
                       'resource_violations': sum(r['resource_violation'] for r in rs),
                       'distinct_mrc_payloads': len({r['mrc_payload_sha256'] for r in rs if r['mrc_payload_sha256']})}
    pair_recs = [json.loads(line) for line in open(out / 'runs.jsonl') if '"retained"' in line]
    discarded = [p for p in pair_recs if not p['retained']]
    integrity = {'timed_runs': len(timed), 'by_arm': by_arm,
                 'pair_attempts': len(pair_recs), 'pairs_discarded': len(discarded),
                 'discarded_detail': discarded,
                 'all_mrc_payloads_identical': len({r['mrc_payload_sha256'] for r in timed
                                                    if r['mrc_payload_sha256']}) == 1,
                 'max_foreign_cpu_s': max((r['foreign_cpu_s'] for r in timed), default=None),
                 'max_kthread_cpu_s': max((r['kthread_cpu_s'] for r in timed), default=None),
                 'max_sibling_foreign_cpu_s': max((r['sibling_foreign_cpu_s'] for r in timed), default=None)}

    # Completeness against the frozen plan, then the verdict. Anything missing is INCOMPLETE.
    blockers = []
    try:
        for arm, path, want in (('A', o.a, o.a_sha), ('B', o.b, o.b_sha)):
            if sha256(path) != want:
                blockers.append(f'binary {arm} changed during the run')
        if incomplete:
            raise ValueError(incomplete)
        if [x[1] for x in done] != plan_orders or [x[0] for x in done] != list(range(1, len(plan) + 1)):
            raise ValueError('retained positions/orders do not match plan.json')
        n_ab = sum(c['order'] == 'AB' for c in comp); n_ba = sum(c['order'] == 'BA' for c in comp)
        n_aa = sum(x['order'] == 'A-A2' for x in null); n_a2a = sum(x['order'] == 'A2-A' for x in null)
        if (len(comp), n_ab, n_ba) != (n, nb, nb) or (len(null), n_aa, n_a2a) != (NULL_PAIRS, NULL_PAIRS // 2, NULL_PAIRS // 2):
            raise ValueError(f'counts {len(comp)} ({n_ab} AB/{n_ba} BA), nulls {len(null)} ({n_aa}/{n_a2a}) differ from plan')
        if not all(isinstance(v, float) and math.isfinite(v) and v > 0 for c in comp for v in (c['A'], c['B'])):
            raise ValueError('non-finite or non-positive wall time')
        d = [c['d'] for c in comp]; d0 = [x['d'] for x in null]
        ci = stats.median_ci(d); ci0 = stats.median_ci(d0)
        if ci is None or ci0 is None:
            raise ValueError('no CI could be computed')
        ma = stats.median(walls_a)
        upper_pct = 100 * ci[1] / ma
        if ci[0] > 0:
            label = 'FAIL'
        elif upper_pct <= 100 * TARGET_FRAC:
            label = 'PASS'
        else:
            label = 'UNRESOLVED'
        if not (ident and ident.get('identical')):
            blockers.append('first definitive AB pair products not identical: %s' % (ident or {}).get('problems'))
        unexplained = {a: v['nonzero_exits'] + v['invalid_products'] for a, v in by_arm.items()}
        if any(unexplained.values()):
            blockers.append(f'unexplained run failures by arm (non-zero exit or invalid products): {unexplained}')
        timing_label = label
        if blockers and label == 'PASS':
            label = 'INCOMPLETE'
        stat = {
            'median_d_s': stats.median(d), 'ci95_s': ci[:2], 'ci_coverage': ci[2],
            'median_wall_A_s': ma, 'median_wall_B_s': stats.median(walls_b),
            'iqr_A_s': stats.iqr(walls_a), 'iqr_B_s': stats.iqr(walls_b),
            'median_d_pct': 100 * stats.median(d) / ma, 'ci_lower_pct': 100 * ci[0] / ma,
            'ci_upper_pct': upper_pct, 'timing_label': timing_label,
            'null_median_s': stats.median(d0), 'null_ci95_s': ci0[:2], 'null_ci_coverage': ci0[2],
            'null_range_s': [min(d0), max(d0)],
        }
        reason = None
    except Exception as e:                  # noqa: BLE001 - any defect in the evidence is INCOMPLETE
        label, stat, reason = 'INCOMPLETE', {}, repr(e)

    res = {'workload': o.name, 'args': args, 'cpus': o.cpus, 'design': design, 'd14_label': label,
           'incomplete': reason, 'pass_blockers': blockers,
           't_first_timed_run_utc': t_first_timed, 't_definitive_start_utc': t_definitive, 't_end_utc': utc(),
           'pairs': len(comp), 'pairs_AB': sum(c['order'] == 'AB' for c in comp),
           'pairs_BA': sum(c['order'] == 'BA' for c in comp), 'null_pairs': len(null)}
    res.update(stat)
    res.update({'integrity': integrity, 'identity': ident, 'comparison_pairs': comp, 'null_pairs_detail': null})
    (out / 'result.json').write_text(json.dumps(res, indent=1))
    emit({'phase': 'end', 'complete': label != 'INCOMPLETE', 'd14_label': label})
    shutil.rmtree(scratch, ignore_errors=True)
    summary = {k_: res.get(k_) for k_ in ('workload', 'd14_label', 'incomplete', 'pass_blockers', 'pairs',
                                         'pairs_AB', 'pairs_BA', 'null_pairs', 'median_d_s', 'ci95_s',
                                         'ci_coverage', 'median_d_pct', 'ci_upper_pct', 'null_median_s',
                                         'null_ci95_s', 'null_range_s', 'median_wall_A_s', 'median_wall_B_s')}
    summary['integrity'] = {k_: integrity[k_] for k_ in integrity if k_ != 'discarded_detail'}
    print('RESULT', json.dumps(summary), flush=True)
    print('identity identical:', (ident or {}).get('identical'), (ident or {}).get('problems'))
    sys.exit(0 if label != 'INCOMPLETE' else 2)


if __name__ == '__main__':
    main()
