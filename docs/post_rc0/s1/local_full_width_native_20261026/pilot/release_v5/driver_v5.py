"""Minimal producer driver v5 (criteria: V5_PLAN.md section 4). It launches exactly the frozen commands of the anchored admission.

Real launch is refused without a parent release file (PARENT_RELEASE.json in the decision directory) naming the sha256 of the v5 module,
this driver, the anchored admission and a delta-review report. Without it only the validation (dry run) is possible. No hidden retry: each
(case, arm) is launched at most once, every failure stops all further launches and is kept. Truth files are never staged.
"""
from pathlib import Path
import fcntl, glob, hashlib, json, os, re, shutil, signal, subprocess, sys, time
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pair_decision_v5 as P5  # noqa: E402

V3 = P5.V3
ARMS = ('OFF', 'ON')


class DriverStop(RuntimeError):
    def __init__(self, code, message=''):
        super().__init__(code + (': ' + message if message else ''))
        self.code = code


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _write(p, obj):
    Path(p).write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def _ledger(path, rec):
    rec = dict(rec, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    with open(path, 'a') as f:
        f.write(json.dumps(rec, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


# ---- the real per-step guard (Linux; run under lane.py) ------------------------------------------------------------------------
def overlapping_locks(cpus):
    lo, hi = (int(x) for x in cpus.split('-'))
    locks = {'/tmp/motioncorr-cpu64-bench.lock', '/tmp/motioncorr-b2-cpu32-47.lock'}
    for p in glob.glob('/tmp/motioncorr*.lock'):
        m = re.search(r'cpu-?(\d+)(?:-(\d+))?', os.path.basename(p))
        if m and int(m[1]) <= hi and int(m[2] or m[1]) >= lo:
            locks.add(p)
    return sorted(locks)


def _busy_cores(cpus, seconds=2.0):
    lo, hi = (int(x) for x in cpus.split('-'))

    def snap():
        d = {}
        for line in open('/proc/stat'):
            if line.startswith('cpu') and line[3].isdigit():
                f = line.split(); n = int(f[0][3:])
                if lo <= n <= hi:
                    v = list(map(int, f[1:])); d[n] = (sum(v), v[3] + v[4])
        return d
    a = snap(); time.sleep(seconds); b = snap()
    return sum((b[n][0] - a[n][0] - (b[n][1] - a[n][1])) / max(1, b[n][0] - a[n][0]) for n in a)


def real_guard(adm, step):
    """Fresh occupancy/affinity/lease/scratch check; raises DriverStop on any problem and returns a receipt otherwise."""
    pol = adm['fresh_venue_resource_admission']
    cpus = pol['cpus']
    held = json.loads(os.environ.get('MOTIONCORR_HELD_LEASES', '[]'))
    want = overlapping_locks(cpus)
    if sorted(held) != want:
        raise DriverStop('GUARD', 'held leases %s differ from the overlapping set %s' % (sorted(held), want))
    for p in want:  # a fresh open file description must be unable to take a lock that lane.py holds
        with open(p, 'a+') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            fcntl.flock(f, fcntl.LOCK_UN)
            raise DriverStop('GUARD', 'lease not actually held: ' + p)
    allowed = [l.split(':', 1)[1].strip() for l in open('/proc/self/status') if l.startswith('Cpus_allowed_list')][0]
    if allowed != cpus:
        raise DriverStop('GUARD', 'allowed CPUs %s differ from %s' % (allowed, cpus))
    busy = _busy_cores(cpus)
    if busy > pol['max_foreign_busy_cores']:
        raise DriverStop('GUARD', 'foreign compute on CPUs %s: %.2f busy cores' % (cpus, busy))
    mem = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}
    if mem['MemAvailable'] / 1024 < pol['min_available_mem_mb']:
        raise DriverStop('GUARD', 'available memory below the floor')
    campaign = sum(f.stat().st_size for f in Path(pol['campaign_root']).rglob('*') if f.is_file())
    total = campaign + pol['prior_scratch_bytes']
    if total > pol['scratch_cap_bytes']:
        raise DriverStop('GUARD', 'combined scratch %d exceeds the cap' % total)
    return {'step': step, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'held_leases': held, 'allowed_cpus': allowed,
            'foreign_busy_cores': busy, 'mem_available_mb': mem['MemAvailable'] // 1024, 'scratch_bytes_combined': total}


# ---- staging, launch, receipt -------------------------------------------------------------------------------------------------
def validate_inputs(ctx):
    """All fixtures and the retained baselines must equal the frozen pins before anything is staged or launched."""
    for n, pin in ctx.adm['fixture_files'].items():
        p = Path(ctx.fixture_dir) / n
        if not p.is_file() or p.stat().st_size != pin['bytes'] or _sha(p) != pin['sha256']:
            raise DriverStop('FIXTURE', 'fixture differs from its pin: ' + n)
    for case in ctx.adm['case_order']:
        try:
            P5._verify_baseline(ctx, case, ctx.baseline_dir(case))
        except P5.PairError as e:
            raise DriverStop('BASELINE', str(e))


def stage_run(ctx, case, arm):
    run_dir = Path(ctx.evidence_root) / case / arm
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()  # exclusive: an existing run directory is never reused
    except FileExistsError:
        raise DriverStop('EXISTS', 'run directory already exists: %s' % run_dir)
    inp = run_dir / 'input'
    inp.mkdir()
    for name in (case + '.star', case + '.mrcs'):
        pin = ctx.adm['fixture_files'][name]
        shutil.copyfile(Path(ctx.fixture_dir) / name, inp / name)
        if (inp / name).stat().st_size != pin['bytes'] or _sha(inp / name) != pin['sha256']:
            raise DriverStop('FIXTURE', 'staged copy differs from its pin: ' + name)
    if sorted(os.listdir(inp)) != sorted([case + '.mrcs', case + '.star']):
        raise DriverStop('STAGING', 'staged cwd must hold exactly the case STAR and MRCS (truth is never staged)')
    return run_dir


def _inventory(out):
    inv = {}
    if out.is_dir():
        for p in sorted(out.rglob('*')):
            if p.is_file() and not p.is_symlink():
                b = p.read_bytes(); inv[p.relative_to(out).as_posix()] = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    return inv


def launch(ctx, case, arm, run_dir, expected, *, cpus, timeout, guard_receipt):
    """Run the one frozen command; write the v3 receipt from what actually happened (never from the expected row)."""
    env = dict(expected['environment'])
    env['PATH'] = '/usr/bin:/bin'
    argv = list(expected['argv'])
    cwd = expected['cwd']
    P5._verify_identity(ctx.adm)  # the binary on disk must still equal the pin immediately before the launch
    pre = None
    if cpus:
        lo, hi = (int(x) for x in cpus.split('-'))
        pre = lambda: os.sched_setaffinity(0, range(lo, hi + 1))  # noqa: E731
    t0 = time.monotonic(); timed_out = False
    with open(run_dir / 'stdout.log', 'wb') as f:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=pre)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGKILL)
            rc = p.wait()
    wall = time.monotonic() - t0
    pin = lambda n: ({'bytes': (run_dir / n).stat().st_size, 'sha256': _sha(run_dir / n)} if (run_dir / n).is_file() else None)  # noqa: E731
    receipt = {'schema': V3.RECEIPT_SCHEMA, 'case': case, 'arm': arm, 'exit': rc, 'binary_sha256': ctx.binary_sha256, 'run_dir': str(run_dir.resolve()),
               'argv': argv, 'cwd': cwd, 'environment': dict(expected['environment']),
               'controlled_environment_observed': {k: v for k, v in env.items() if k.startswith(V3.CONTROLLED_PREFIXES)},
               'publication': _inventory(run_dir / 'output'), 'runtime': pin('runtime.json'), 'stdout': pin('stdout.log'),
               'extra_child_environment': {'PATH': env['PATH']}, 'timed_out': timed_out, 'wall_seconds_receipt_only': wall,
               'guard_receipt_sha256': hashlib.sha256(json.dumps(guard_receipt, sort_keys=True).encode()).hexdigest()}
    _write(run_dir / 'RUN.json', receipt)
    return receipt


def check_release(ctx, decision_dir):
    rp = Path(decision_dir) / 'PARENT_RELEASE.json'
    if not rp.is_file():
        raise DriverStop('RELEASE', 'PARENT_RELEASE.json absent: the real launch path is closed')
    r = json.loads(rp.read_text())
    want = {'release_module_sha256': _sha(HERE / 'pair_decision_v5.py'), 'driver_sha256': _sha(HERE / 'driver_v5.py'),
            'admission_sha256': hashlib.sha256(P5.ADMISSION_PATH.read_bytes()).hexdigest()}
    for k, v in want.items():
        if r.get(k) != v:
            raise DriverStop('RELEASE', '%s does not equal the file in use' % k)
    if not (isinstance(r.get('delta_review_report_sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', r['delta_review_report_sha256'])) or r.get('approved_by') != 'parent':
        raise DriverStop('RELEASE', 'release file lacks a delta-review report hash or parent approval')
    return r


def run_campaign(decision_dir, *, execute=False, guard=None, cpus=None, timeout=900):
    """Validate and, only with a parent release, run the pilot: per case OFF, pre-ON gate, ON; then decide_pilot once."""
    ctx = P5.context(decision_dir)
    guard = guard or (lambda step: real_guard(ctx.adm, step))
    budget = ctx.adm['native_producer_budget']
    plan = [(c, a) for c in ctx.adm['case_order'] for a in ARMS]
    if len(plan) > budget:
        raise DriverStop('BUDGET', 'plan exceeds the producer budget')
    validate_inputs(ctx)
    g0 = guard('validate')
    if not execute:
        return {'mode': 'dry-run', 'launches_planned': len(plan), 'rows': [ctx.expected(c, a) for c, a in plan], 'guard': g0, 'created': []}
    dd = Path(decision_dir)
    check_release(ctx, dd)
    ev = Path(ctx.evidence_root)
    if ev.exists() and any(ev.iterdir()):
        raise DriverStop('EXISTS', 'evidence_root is not empty')
    ledger = dd / 'ledger.jsonl'
    if ledger.exists():
        raise DriverStop('EXISTS', 'ledger already exists: a campaign is never resumed or restarted in place')
    launched = 0
    try:
        for case in ctx.adm['case_order']:
            for arm in ARMS:
                if launched >= budget:
                    raise DriverStop('BUDGET', 'launch ceiling reached')
                g = guard('%s/%s' % (case, arm))
                P5._verify_identity(ctx.adm)  # before anything is staged or counted: the binary must still equal its pin
                (dd / 'guard').mkdir(exist_ok=True)
                _write(dd / 'guard' / ('%s_%s.json' % (case, arm)), g)
                run_dir = stage_run(ctx, case, arm)
                expected = ctx.expected(case, arm)
                _ledger(ledger, {'event': 'launching', 'case': case, 'arm': arm, 'argv_sha256': hashlib.sha256(json.dumps(expected['argv']).encode()).hexdigest(), 'index': launched + 1})
                launched += 1
                receipt = launch(ctx, case, arm, run_dir, expected, cpus=cpus, timeout=timeout, guard_receipt=g)
                _ledger(ledger, {'event': 'finished', 'case': case, 'arm': arm, 'exit': receipt['exit'], 'timed_out': receipt['timed_out'], 'receipt_sha256': _sha(run_dir / 'RUN.json')})
                if receipt['exit'] != 0 or receipt['timed_out']:
                    raise DriverStop('PRODUCER', 'exit %r timed_out %r for %s/%s' % (receipt['exit'], receipt['timed_out'], case, arm))
                if arm == 'OFF':
                    P5.pre_ON_gate(case, decision_dir=dd)  # admits OFF, checks baseline/raw/manipulation/comparator before any ON exists
                else:
                    P5.admit_single(case, 'ON', decision_dir=dd)
        result = P5.decide_pilot(decision_dir=dd)
    except (DriverStop, P5.PairError, V3.AdmissionError) as e:  # first failure stops everything and is kept; nothing is retried
        _ledger(ledger, {'event': 'STOP', 'code': getattr(e, 'code', 'ADMISSION'), 'message': str(e), 'launches': launched})
        raise
    _ledger(ledger, {'event': 'DECIDED', 'prediction': result['prediction'], 'acceptance': result['acceptance']})
    return result


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--decision-dir', required=True)
    ap.add_argument('--execute', action='store_true', help='real launch; requires PARENT_RELEASE.json in the decision directory')
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--receipt', help='write the full result JSON here (must not exist)')
    a = ap.parse_args(argv)
    cpus = P5.context(None).adm['fresh_venue_resource_admission']['cpus']
    out = run_campaign(a.decision_dir, execute=a.execute, cpus=cpus, timeout=a.timeout)
    text = json.dumps(out, indent=1, default=str) + '\n'
    if a.receipt:
        with open(a.receipt, 'x') as f:
            f.write(text)
    print(text[:2000])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
