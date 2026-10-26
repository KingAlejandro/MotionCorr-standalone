"""Continuation driver v5.2 (criteria: CONTINUATION_PLAN.md): a modified copy of driver_v5_1.py; driver_v5_1.py and driver_v5.py are unchanged.

Only the campaign part differs: the r1 pilot stopped after the frozen first OFF (noisy/OFF); this driver REUSES that exact produced OFF once (verified byte for byte against the
frozen continuation block of the admission, the old ledger/STOP hashes checked before and after), re-evaluates its pre-ON gate from the saved outputs against the correct baseline
root (no producer), launches noisy ON and then the remaining 7 cases OFF/ON (15 launches at most, 16 globally with the reused OFF), and runs decide_pilot once. Launch, sampling,
lease ownership, cleanup and staging code are unchanged from v5.1. Real launch needs a parent release file naming this driver, the v5.2 module, the v5.2 admission and commands and
the reused OFF RUN.json hash. No generic resume, no other reuse case, no retry.
"""
from pathlib import Path
import glob, hashlib, json, os, re, shutil, signal, subprocess, sys, time
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pair_decision_v5_2 as P5  # noqa: E402

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


# ---- /proc readers (module-level so tests can substitute them) ---------------------------------------------------------------
def _read_text(path):
    with open(path) as f:
        return f.read()


def _listdir(path):
    return os.listdir(path)


def parse_proc_status(text):
    d = {}
    for line in text.splitlines():
        k, _, v = line.partition(':')
        d[k.strip()] = v.strip()
    return {'name': d['Name'], 'state': d['State'], 'ppid': int(d['PPid']), 'threads': int(d['Threads']),
            'cpus_allowed_list': d['Cpus_allowed_list'], 'vmrss_kb': int(d['VmRSS'].split()[0]) if 'VmRSS' in d else None}


def parse_proc_stat_times(text):
    rest = text[text.rindex(')') + 2:].split()  # fields after the command name: state is rest[0], utime/stime are fields 14/15 overall
    return int(rest[11]), int(rest[12])


def parse_proc_locks(text):
    """Entries (kind, mode, pid, major, minor, inode) of /proc/locks lines such as `1: FLOCK  ADVISORY  WRITE 4242 fd:00:1234 0 EOF`."""
    out = []
    for line in text.splitlines():
        m = re.match(r'^\d+:\s+(\w+)\s+\w+\s+(\w+)\s+(-?\d+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)\s', line)
        if m:
            out.append((m[1], m[2], int(m[3]), int(m[4], 16), int(m[5], 16), int(m[6])))
    return out


def ancestor_pids(pid, ppid_of):
    """Ancestors of pid (excluding pid) up to init, through a ppid reader; a wrapper shell between lane and the driver is just one more ancestor."""
    out, seen = [], {pid}
    cur = ppid_of(pid)
    while cur and cur not in seen:
        out.append(cur); seen.add(cur)
        cur = ppid_of(cur)
    return out


def lease_owner(entries, st_dev, st_ino, ancestors):
    """(ok, why): the CURRENT inode of the lock path must carry a FLOCK WRITE entry owned by an ancestor of the driver (our lane), not by a peer."""
    maj, mnr = os.major(st_dev), os.minor(st_dev)
    here = [e for e in entries if e[5] == st_ino and (e[3], e[4]) == (maj, mnr) and e[0] == 'FLOCK' and e[1] == 'WRITE']
    if not here:
        return False, 'no FLOCK WRITE entry on the current inode (unheld, or held only on an orphaned inode)'
    mine = [e for e in here if e[2] in ancestors]
    if not mine:
        return False, 'the current inode is flock-held by pid(s) %s, none of them an ancestor of the driver' % sorted({e[2] for e in here})
    return True, mine[0][2]


# ---- child resource sampling (a record, never a gate) --------------------------------------------------------------------------
SAMPLE_CAP = 400
MAX_PROCS_PER_SAMPLE = 32


class ResourceRecorder:
    def __init__(self, cap=SAMPLE_CAP):
        self.cap, self.samples, self.n = cap, [], 0
        self.max_threads = self.max_tasks = 0
        self.cpus, self.pids = set(), set()
        self.first_ms = self.last_ms = None
        self.child_reads = 0
        self.failures, self.first_errors, self.vanished, self.children_missing = 0, [], 0, 0
        self.proc_available = os.path.exists('/proc/self/status')

    def _fail(self, what, exc, pid, is_child):
        if isinstance(exc, (FileNotFoundError, ProcessLookupError)):
            self.vanished += 1  # a process that has already exited is normal, not a read failure
            return
        self.failures += 1
        if len(self.first_errors) < 5:
            self.first_errors.append('%s pid %d: %s: %s' % (what, pid, type(exc).__name__, exc))

    def _one(self, pid, is_child):
        try:
            st = parse_proc_status(_read_text('/proc/%d/status' % pid))
        except (OSError, ValueError, KeyError) as e:
            self._fail('status', e, pid, is_child)
            return None
        rec = dict(st, pid=pid)
        try:
            rec['tasks'] = len(_listdir('/proc/%d/task' % pid))
        except OSError as e:
            self._fail('task', e, pid, is_child); rec['tasks'] = None
        try:
            rec['utime_ticks'], rec['stime_ticks'] = parse_proc_stat_times(_read_text('/proc/%d/stat' % pid))
        except (OSError, ValueError, IndexError) as e:
            self._fail('stat', e, pid, is_child); rec['utime_ticks'] = rec['stime_ticks'] = None
        if is_child:
            self.child_reads += 1
        return rec

    def sample(self, child_pid, t_ms):
        procs, queue, seen = [], [child_pid], {child_pid}
        while queue and len(procs) < MAX_PROCS_PER_SAMPLE:
            pid = queue.pop(0)
            rec = self._one(pid, pid == child_pid)
            if rec is None:
                continue
            procs.append(rec)
            try:
                for tid in _listdir('/proc/%d/task' % pid):
                    try:
                        kids = _read_text('/proc/%d/task/%s/children' % (pid, tid)).split()
                    except FileNotFoundError:
                        self.children_missing += 1  # no children file (kernel option) or the thread just exited: descendants not observable this time
                        continue
                    for c in kids:
                        if int(c) not in seen:
                            seen.add(int(c)); queue.append(int(c))
            except (OSError, ValueError) as e:
                self._fail('children', e, pid, pid == child_pid)
        self.n += 1
        self.first_ms = t_ms if self.first_ms is None else self.first_ms
        self.last_ms = t_ms
        for r in procs:
            self.pids.add(r['pid'])
            self.max_threads = max(self.max_threads, r['threads'])
            if r['tasks'] is not None:
                self.max_tasks = max(self.max_tasks, r['tasks'])
            self.cpus.add(r['cpus_allowed_list'])
        if len(self.samples) < self.cap:
            self.samples.append({'t_ms': t_ms, 'procs': procs})

    def receipt(self):
        if self.child_reads:
            status = 'PARTIAL' if self.failures else 'OBSERVED'
            reason = None
        else:
            status = 'UNOBSERVED'
            reason = 'no /proc on this host' if not self.proc_available else ('the child exited before any readable sample' if self.n and not self.failures else 'no sample was readable')
        return {'status': status, 'reason': reason,
                'schedule': 'immediately after Popen, then every 20 ms for 1 s, then every 100 ms until exit or timeout; stored samples capped at %d' % self.cap,
                'n_samples': self.n, 'stored_samples': len(self.samples), 'truncated': self.n > len(self.samples),
                'read_failures': self.failures, 'first_errors': self.first_errors, 'vanished_reads': self.vanished, 'children_file_missing_reads': self.children_missing,
                'summary': {'max_threads': self.max_threads, 'max_tasks': self.max_tasks, 'distinct_cpus_allowed_lists': sorted(self.cpus),
                            'processes_seen': sorted(self.pids), 'first_ms': self.first_ms, 'last_ms': self.last_ms},
                'samples': self.samples,
                'note': 'a record only: deviations (for example Threads 3) are not a gate and --j 2 is never proof of Threads == 2'}


def _wait_with_sampling(p, timeout, rec):
    t0 = time.monotonic()
    deadline = t0 + timeout
    while True:
        rec.sample(p.pid, int((time.monotonic() - t0) * 1000))  # the first iteration is the immediate post-Popen sample
        rc = p.poll()
        if rc is not None:
            return rc
        now = time.monotonic()
        if now >= deadline:
            raise subprocess.TimeoutExpired(p.args, timeout)
        time.sleep(min(0.02 if now - t0 < 1.0 else 0.1, max(0.0, deadline - now)))


def _kill_own_group(p):
    """Terminate and reap only our own child's process group (the child is its own session/group leader); never a group we do not own."""
    if p.poll() is not None:
        return
    try:
        pgid = os.getpgid(p.pid)
        if pgid != p.pid or pgid == os.getpgrp():
            p.kill(); p.wait(); return
        os.killpg(pgid, signal.SIGTERM)
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL); p.wait()
    except ProcessLookupError:
        p.wait()


def _child_preexec(cpus):
    lo = hi = None
    if cpus:
        lo, hi = (int(x) for x in cpus.split('-'))

    libc = None
    if sys.platform.startswith('linux'):
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)

    def pre():
        if libc is not None:
            libc.prctl(1, int(signal.SIGKILL), 0, 0, 0)  # PR_SET_PDEATHSIG: the direct child dies with the driver (not its grandchildren)
        if lo is not None:
            os.sched_setaffinity(0, range(lo, hi + 1))
    return pre


class Terminated(BaseException):
    """SIGTERM received by the driver (raised inside the campaign so cleanup runs)."""


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
    """Fresh occupancy/affinity/lease/scratch/disk check; raises DriverStop on any problem and returns a receipt otherwise."""
    pol = adm['fresh_venue_resource_admission']
    cpus = pol['cpus']
    held = json.loads(os.environ.get('MOTIONCORR_HELD_LEASES', '[]'))
    want = overlapping_locks(cpus)
    if sorted(held) != want:
        raise DriverStop('GUARD', 'held leases %s differ from the overlapping set %s' % (sorted(held), want))
    try:  # the current inode of every lock path must be flock-held by an ancestor of this process (our lane), not by a peer
        entries = parse_proc_locks(_read_text('/proc/locks'))
        anc = ancestor_pids(os.getpid(), lambda pid: parse_proc_status(_read_text('/proc/%d/status' % pid))['ppid'])
    except (OSError, ValueError, KeyError) as e:
        raise DriverStop('GUARD', '/proc/locks or the ancestor chain is unreadable: %s' % e)
    owners = {}
    for p in want:
        try:
            st = os.stat(p)
        except OSError as e:
            raise DriverStop('GUARD', 'lock path missing: %s (%s)' % (p, e))
        ok, why = lease_owner(entries, st.st_dev, st.st_ino, anc)
        if not ok:
            raise DriverStop('GUARD', 'lease %s: %s' % (p, why))
        owners[p] = why
    allowed = [l.split(':', 1)[1].strip() for l in open('/proc/self/status') if l.startswith('Cpus_allowed_list')][0]
    if allowed != cpus:
        raise DriverStop('GUARD', 'allowed CPUs %s differ from %s' % (allowed, cpus))
    busy = _busy_cores(cpus)
    if busy > pol['max_foreign_busy_cores']:
        raise DriverStop('GUARD', 'foreign compute on CPUs %s: %.2f busy cores' % (cpus, busy))
    mem = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}
    if mem['MemAvailable'] / 1024 < pol['min_available_mem_mb']:
        raise DriverStop('GUARD', 'available memory below the floor')
    vfs = os.statvfs(pol['campaign_root'])
    free = vfs.f_bavail * vfs.f_frsize
    floor = max(1 << 30, pol.get('min_free_bytes', 0))
    if free < floor:
        raise DriverStop('GUARD', 'free disk %d below the floor %d' % (free, floor))
    campaign = sum(f.stat().st_size for f in Path(pol['campaign_root']).rglob('*') if f.is_file())
    total = campaign + pol['prior_scratch_bytes']
    if total > pol['scratch_cap_bytes']:
        raise DriverStop('GUARD', 'combined scratch %d exceeds the cap' % total)
    return {'step': step, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'held_leases': held, 'lease_owner_pids': owners, 'allowed_cpus': allowed,
            'foreign_busy_cores': busy, 'mem_available_mb': mem['MemAvailable'] // 1024, 'free_bytes': free, 'free_floor_bytes': floor,
            'scratch_bytes_combined': total, 'prior_scratch_bytes': pol['prior_scratch_bytes'], 'prior_scratch_frozen': True,
            'note': 'prior_scratch_bytes is a frozen conservative constant; a live pre-launch measurement of the prior namespaces by the parent is still required'}


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


def launch(ctx, case, arm, run_dir, expected, *, cpus, timeout, guard_receipt, ledger=None):
    """Run the one frozen command; write the v3 receipt from what actually happened (never from the expected row)."""
    env = dict(expected['environment'])
    env['PATH'] = '/usr/bin:/bin'
    argv = list(expected['argv'])
    cwd = expected['cwd']
    P5._verify_identity(ctx.adm)  # the binary on disk must still equal the pin immediately before the launch
    t0 = time.monotonic(); timed_out = False; aborted = None; launch_error = None; rc = None; child_pid = None
    rec = ResourceRecorder()
    pin = lambda n: ({'bytes': (run_dir / n).stat().st_size, 'sha256': _sha(run_dir / n)} if (run_dir / n).is_file() else None)  # noqa: E731

    def write_receipt():
        receipt = {'schema': V3.RECEIPT_SCHEMA, 'case': case, 'arm': arm, 'exit': rc, 'binary_sha256': ctx.binary_sha256, 'run_dir': str(run_dir.resolve()),
                   'argv': argv, 'cwd': cwd, 'environment': dict(expected['environment']),
                   'controlled_environment_observed': {k: v for k, v in env.items() if k.startswith(V3.CONTROLLED_PREFIXES)},
                   'publication': _inventory(run_dir / 'output'), 'runtime': pin('runtime.json'), 'stdout': pin('stdout.log'),
                   'extra_child_environment': {'PATH': env['PATH']}, 'timed_out': timed_out, 'wall_seconds_receipt_only': time.monotonic() - t0,
                   'guard_receipt_sha256': hashlib.sha256(json.dumps(guard_receipt, sort_keys=True).encode()).hexdigest(),
                   'child_pid': child_pid, 'resource_samples': rec.receipt(), 'aborted': aborted, 'launch_error': launch_error}
        _write(run_dir / 'RUN.json', receipt)
        return receipt
    with open(run_dir / 'stdout.log', 'wb') as f:
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=_child_preexec(cpus))
        except BaseException as e:  # the child never started: keep the real exception, launch nothing else
            launch_error = repr(e)
            write_receipt()
            if ledger is not None:
                _ledger(ledger, {'event': 'finished', 'case': case, 'arm': arm, 'exit': None, 'launch_error': launch_error})
            if isinstance(e, Exception):
                raise DriverStop('LAUNCH', launch_error)
            raise
        child_pid = p.pid
        try:
            rc = _wait_with_sampling(p, timeout, rec)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_own_group(p)
            rc = p.wait()
        except BaseException as e:  # any other interruption (also KeyboardInterrupt/SIGTERM): our own child group only, reaped, then re-raised
            aborted = repr(e)
            _kill_own_group(p)
            rc = p.poll()
            write_receipt()
            if ledger is not None:
                _ledger(ledger, {'event': 'finished', 'case': case, 'arm': arm, 'exit': rc, 'aborted': aborted, 'child_pid': child_pid})
            raise
    return write_receipt()


def check_release(ctx, decision_dir):
    rp = Path(decision_dir) / 'PARENT_RELEASE.json'
    if not rp.is_file():
        raise DriverStop('RELEASE', 'PARENT_RELEASE.json absent: the real launch path is closed')
    r = json.loads(rp.read_text())
    want = {'release_module_sha256': _sha(HERE / 'pair_decision_v5_2.py'), 'driver_sha256': _sha(HERE / 'driver_v5_2.py'),
            'admission_sha256': hashlib.sha256(P5.ADMISSION_PATH.read_bytes()).hexdigest(), 'commands_sha256': hashlib.sha256(P5.COMMANDS_PATH.read_bytes()).hexdigest(),
            'reused_off_run_json_sha256': ctx.continuation['run_json_sha256']}
    for k, v in want.items():
        if r.get(k) != v:
            raise DriverStop('RELEASE', '%s does not equal the file in use' % k)
    if not (isinstance(r.get('delta_review_report_sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', r['delta_review_report_sha256'])) or r.get('approved_by') != 'parent':
        raise DriverStop('RELEASE', 'release file lacks a delta-review report hash or parent approval')
    return r


def _tree_inventory(root):
    inv = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            raise DriverStop('REUSE', 'symlink in the reused OFF: %s' % p)
        if p.is_file():
            inv[p.relative_to(root).as_posix()] = _sha(p)
    return inv


def verify_reuse(ctx):
    """The only reuse case: the frozen first OFF, byte for byte, with nothing else in evidence_root and the r1 records unchanged."""
    c = ctx.continuation
    first = (ctx.adm['case_order'][0], 'OFF')
    if (c.get('case'), c.get('arm')) != first or c.get('kind') != 'reuse_first_off_after_r1_stop':
        raise DriverStop('REUSE', 'only the frozen first OFF %s may be reused, got %s' % (first, (c.get('case'), c.get('arm'))))
    ev = Path(ctx.evidence_root)
    if not ev.is_dir() or sorted(p.name for p in ev.iterdir()) != [first[0]] or sorted(p.name for p in (ev / first[0]).iterdir()) != ['OFF']:
        raise DriverStop('REUSE', 'evidence_root must hold exactly %s/OFF and nothing else' % first[0])
    off = ev / first[0] / 'OFF'
    inv = _tree_inventory(off)
    if inv != c['evidence_inventory'] or hashlib.sha256(P5._canon(inv)).hexdigest() != c['evidence_inventory_sha256']:
        raise DriverStop('REUSE', 'the first OFF differs from the frozen inventory (changed, missing or extra file)')
    if _sha(off / 'RUN.json') != c['run_json_sha256']:
        raise DriverStop('REUSE', 'the first OFF RUN.json differs from the frozen hash')
    r1 = Path(c['r1_decision_dir'])
    for name, key in (('ledger.jsonl', 'r1_ledger_sha256'), ('STOP.json', 'r1_stop_sha256'), ('PARENT_RELEASE.json', 'r1_release_sha256'), ('PARENT_RELEASE_INDEX.json', 'r1_release_index_sha256')):
        if not (r1 / name).is_file() or _sha(r1 / name) != c[key]:
            raise DriverStop('REUSE', 'r1 record %s differs from the frozen hash' % name)
    return inv


def run_continuation(decision_dir, *, execute=False, guard=None, cpus=None, timeout=900):
    """Validate and, only with a parent release, continue the pilot: reuse noisy/OFF, gate it, then 15 launches; decide_pilot once."""
    ctx = P5.context(decision_dir)
    guard = guard or (lambda step: real_guard(ctx.adm, step))
    budget = ctx.adm['native_producer_budget']
    order = ctx.adm['case_order']
    plan = [(order[0], 'ON')] + [(c, a) for c in order[1:] for a in ARMS]
    c = ctx.continuation
    if len(plan) + c['launches_before'] != budget or c['remaining'] != len(plan) or c['global_ceiling'] != budget or budget != 16:
        raise DriverStop('BUDGET', 'plan %d + reused %d must equal the global budget 16' % (len(plan), c['launches_before']))
    validate_inputs(ctx)
    verify_reuse(ctx)
    g0 = guard('validate')
    if not execute:
        return {'mode': 'dry-run-continuation', 'reused': [order[0], 'OFF'], 'launches_planned': len(plan), 'rows': [ctx.expected(cs, a) for cs, a in plan], 'guard': g0, 'created': []}
    dd = Path(decision_dir)
    check_release(ctx, dd)
    ledger = dd / 'ledger.jsonl'
    if ledger.exists():
        raise DriverStop('EXISTS', 'ledger already exists: the continuation decision directory must be fresh')
    _ledger(ledger, {'event': 'REUSED', 'case': order[0], 'arm': 'OFF', 'run_json_sha256': c['run_json_sha256'], 'r1_ledger_sha256': c['r1_ledger_sha256'], 'r1_stop_sha256': c['r1_stop_sha256'],
                     'launches_before': c['launches_before'], 'remaining': len(plan), 'global_ceiling': budget})
    launched = 0

    def _on_term(signum, frame):
        raise Terminated('SIGTERM')
    old_term = signal.signal(signal.SIGTERM, _on_term)
    try:
        g = guard('reuse-gate/%s' % order[0])
        (dd / 'guard').mkdir(exist_ok=True)
        _write(dd / 'guard' / ('%s_OFF_reuse_gate.json' % order[0]), g)
        P5.pre_ON_gate(order[0], decision_dir=dd)  # re-evaluated from the saved outputs against the audited baseline root; no producer
        for case, arm in plan:
            if launched >= budget - c['launches_before']:
                raise DriverStop('BUDGET', 'launch ceiling reached')
            g = guard('%s/%s' % (case, arm))
            P5._verify_identity(ctx.adm)  # before anything is staged or counted: the binary must still equal its pin
            _write(dd / 'guard' / ('%s_%s.json' % (case, arm)), g)
            run_dir = stage_run(ctx, case, arm)
            expected = ctx.expected(case, arm)
            _ledger(ledger, {'event': 'launching', 'case': case, 'arm': arm, 'argv_sha256': hashlib.sha256(json.dumps(expected['argv']).encode()).hexdigest(), 'index': launched + 1})
            launched += 1
            receipt = launch(ctx, case, arm, run_dir, expected, cpus=cpus, timeout=timeout, guard_receipt=g, ledger=ledger)
            _ledger(ledger, {'event': 'finished', 'case': case, 'arm': arm, 'exit': receipt['exit'], 'timed_out': receipt['timed_out'], 'receipt_sha256': _sha(run_dir / 'RUN.json')})
            if receipt['exit'] != 0 or receipt['timed_out']:
                raise DriverStop('PRODUCER', 'exit %r timed_out %r for %s/%s' % (receipt['exit'], receipt['timed_out'], case, arm))
            if arm == 'OFF':
                P5.pre_ON_gate(case, decision_dir=dd)
            else:
                P5.admit_single(case, 'ON', decision_dir=dd)
        result = P5.decide_pilot(decision_dir=dd)
        verify_reuse_records_unchanged(ctx)
    except BaseException as e:  # first failure (also KeyboardInterrupt/SIGTERM/SystemExit) stops everything and is kept with the real exception; nothing is retried
        _ledger(ledger, {'event': 'STOP', 'code': getattr(e, 'code', type(e).__name__), 'message': str(e) or repr(e), 'exception': repr(e), 'launches': launched})
        raise
    finally:
        signal.signal(signal.SIGTERM, old_term)
    _ledger(ledger, {'event': 'DECIDED', 'prediction': result['prediction'], 'acceptance': result['acceptance'], 'launches': launched, 'global_launches': launched + c['launches_before']})
    return result


def verify_reuse_records_unchanged(ctx):
    c = ctx.continuation
    r1 = Path(c['r1_decision_dir'])
    for name, key in (('ledger.jsonl', 'r1_ledger_sha256'), ('STOP.json', 'r1_stop_sha256')):
        if _sha(r1 / name) != c[key]:
            raise DriverStop('REUSE', 'r1 record %s changed during the continuation' % name)
    if _sha(Path(ctx.evidence_root) / c['case'] / 'OFF' / 'RUN.json') != c['run_json_sha256']:
        raise DriverStop('REUSE', 'the reused OFF RUN.json changed during the continuation')


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--decision-dir', required=True)
    ap.add_argument('--execute', action='store_true', help='real launch; requires PARENT_RELEASE.json in the decision directory')
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--receipt', help='write the full result JSON here (must not exist)')
    a = ap.parse_args(argv)
    cpus = P5.context(None).adm['fresh_venue_resource_admission']['cpus']
    out = run_continuation(a.decision_dir, execute=a.execute, cpus=cpus, timeout=a.timeout)
    text = json.dumps(out, indent=1, default=str) + '\n'
    if a.receipt:
        with open(a.receipt, 'x') as f:
            f.write(text)
    print(text[:2000])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
