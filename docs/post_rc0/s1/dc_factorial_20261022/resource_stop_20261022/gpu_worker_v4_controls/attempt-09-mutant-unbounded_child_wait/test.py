#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host mock controls for gpu_worker_v4.py (successor of the v3 harness). Every GPU query is a fake nvidia-smi; no GPU, no motioncorr.

Signals are sent only to processes this harness created or that the mock jobs
recorded, after re-checking PID, birth identity, process group and session, and
only if kill(pid, 0) succeeds (same UID for a non-root user). No name-based
signal is ever used. Each control's processes are reaped in a finally block.
The worker runs under a launcher whose own process stays in the worker's
process group as a sentinel; it logs any signal it receives.

Linux subreaper adoption is not available on macOS. Controls marked "emulated
adoption" patch ProcessOwnership.refresh in the worker process (test-only) to
apply the helper's Linux adoption rule (direct child, PGID != worker PGID, not
a zombie) to real processes. That exercises the ordering/ownership branch; it
is not Linux execution, which remains UNRUN.

usage: test_gpu_worker_v4.py --json OUT.json [--worker PATH]
"""
import argparse, fcntl, hashlib, json, os, signal, subprocess, sys, tempfile, textwrap, time, traceback
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = next(p for p in [TOOLS, *TOOLS.parents] if (p / 'tools/multi_gpu/process_ownership.py').exists())
sys.path.insert(0, str(REPO / 'tools/multi_gpu'))
from process_ownership import ProcessOwnership, ProcessTable  # noqa: E402

UUID = 'GPU-00000000-test-test-test-000000000002'
TABLE = ProcessTable()
PY = sys.executable
CAMPAIGN_RUN_KEYS = ['id', 'tier', 'backend', 'arm', 'build', 'group', 'source_sha', 'binary', 'binary_sha256', 'argv',
                     'cwd', 'env', 'cpu', 'host', 'inputs', 'bench_lock', 'start_utc', 'gpu_before', 'exit',
                     'wall_s_unqualified', 'end_utc', 'gpu_witness_uuids', 'gpu_after', 'dc_witness', 'outputs']

IDENT = textwrap.dedent(f'''\
    import json, os, sys
    sys.path.insert(0, {str(REPO / 'tools/multi_gpu')!r})
    from process_ownership import ProcessTable
    def ident(pid):
        r = ProcessTable().read(pid)
        return dict(pid=pid, start=r['start'], pgid=r['pgid'], sid=os.getsid(pid)) if r else None
    def record(path, pid):
        with open(path, 'a') as f: f.write(json.dumps(ident(pid)) + '\\n')
''')

FAKE_SMI = IDENT + textwrap.dedent('''\
    import fcntl, time
    st_path = os.environ['FAKE_SMI_STATE']
    st = json.load(open(st_path))
    record(st['smi_pids'], os.getpid())
    apps = 'compute-apps' in ' '.join(sys.argv[1:])
    n = 0
    if apps:
        with open(st['counter'], 'a+') as c:
            fcntl.flock(c, fcntl.LOCK_EX); c.seek(0); n = int(c.read() or 0) + 1; c.seek(0); c.truncate(); c.write(str(n))
        open(st['calls'], 'a').write('start %d\\n' % n)
    if st.get('create_dir_on_call') and apps and n == st['create_dir_on_call'][0]:
        os.makedirs(st['create_dir_on_call'][1])
    if apps and str(n) in st.get('sleep_on_call', {}): time.sleep(st['sleep_on_call'][str(n)])
    if apps and os.path.exists(st['hold_flag']) and not os.path.exists(st['held_marker']):
        open(st['held_marker'], 'w').write(str(os.getpid())); time.sleep(st.get('hold_s', 2.5))
    if st.get('sleep_always'): time.sleep(st['sleep_always'])
    if st.get('fail_always') or (st.get('fail_if_exists') and os.path.exists(st['fail_if_exists'])): sys.exit(9)
    if not apps:
        print('0, GPU-other-0, 1 MiB, 0 %, 0')
        print('%s, %s, 1 MiB, 0 %%, %s' % (st.get('index', 2), os.environ['FAKE_UUID'], st.get('ecc', '0')))
        sys.exit(0)
    if st.get('malformed'): print('%s, notapid, 1 MiB' % os.environ['FAKE_UUID'])
    foreign = list(st.get('foreign', []))
    for k, pids in st.get('foreign_from_call', {}).items():
        if n >= int(k): foreign += pids
    if st.get('foreign_if_exists') and os.path.exists(st['foreign_if_exists'][0]): foreign += st['foreign_if_exists'][1]
    own = []
    if os.path.exists(st['own']):
        for line in open(st['own']):
            r = json.loads(line); cur = ProcessTable().read(r['pid'])
            # Real nvidia-smi lists live CUDA contexts only; an exited (zombie) process has none.
            if cur and json.dumps(cur['start']) == json.dumps(r['start']) and cur['state'] != 'Z': own.append(r['pid'])
    if st.get('hide_own'): own = []
    for pid in foreign + own: print('%s, %d, 10 MiB' % (os.environ['FAKE_UUID'], pid))
''')

MOCK_JOB = IDENT + textwrap.dedent('''\
    import subprocess, time
    mode, out = sys.argv[1], sys.argv[2]
    st = json.load(open(os.environ['FAKE_SMI_STATE']))
    record(st['own'], os.getpid())
    def tree():
        k = subprocess.Popen(['sleep', '300']); record(st['tree'], k.pid)
        g = subprocess.Popen([sys.executable, '-c', 'import os,time;os.setsid();time.sleep(300)'])
        while os.getsid(g.pid) == os.getsid(0): time.sleep(0.01)
        record(st['tree'], g.pid)
        gg = subprocess.Popen(['sleep', '301'], start_new_session=True); record(st['tree'], gg.pid)
        open(st['tree_ready'], 'w').write('ready')
        time.sleep(300)
    if mode == 'ok': time.sleep(0.6); open(out + '/product.txt', 'w').write('ok\\n'); sys.exit(0)
    if mode == 'touch_then_ok':
        time.sleep(0.6); open(os.environ['FAKE_FAULT_FLAG'], 'w').write('x'); time.sleep(0.8); sys.exit(0)
    if mode == 'tree': tree()
    if mode in ('hold_exit', 'hold_tree'):
        time.sleep(0.6); open(st['hold_flag'], 'w').write('x')
        deadline = time.time() + 15
        while not os.path.exists(st['held_marker']) and time.time() < deadline: time.sleep(0.01)
        if mode == 'hold_exit': sys.exit(0)
        tree()
    if mode == 'flag_tree':
        open(os.environ['FAKE_FAULT_FLAG'], 'w').write('x'); tree()
''')

EMULATE = textwrap.dedent('''\
    def emulate_linux_adoption(cls):
        """Test-only: apply process_ownership's Linux adoption rule (direct child outside the parent's group)."""
        orig = cls.refresh
        def refresh(self):
            orig(self)
            for pid, r in self.table.records().items():
                if r['ppid'] == self.parent_pid and r['pgid'] != self.parent_group and r['state'] != 'Z':
                    with self._lock: self.identities.setdefault(pid, r['start'])
        cls.refresh = refresh
    def emulate_linux_restore(cls):
        """Test-only: Linux restore() refuses while observer errors remain (process_ownership.py restore)."""
        orig = cls.restore
        def restore(self):
            if self.errors: raise RuntimeError('Cannot restore subreaper while owned children or errors remain')
            return orig(self)
        cls.restore = restore
''')

FAULT_ENTRY = EMULATE + textwrap.dedent('''\
    import importlib.util, os, sys
    spec = importlib.util.spec_from_file_location('gpu_worker_under_test', sys.argv[1])
    m = importlib.util.module_from_spec(spec); sys.modules['gpu_worker_under_test'] = m; spec.loader.exec_module(m)
    faults = os.environ.get('V3_FAULT', '').split(',')
    if 'emulate_adoption' in faults: emulate_linux_adoption(m.ProcessOwnership)
    if 'emulate_linux_restore' in faults: emulate_linux_restore(m.ProcessOwnership)
    if 'refresh_after_flag' in faults:
        orig = m.ProcessOwnership.refresh
        def refresh(self):
            if os.path.exists(os.environ['FAKE_FAULT_FLAG']): raise RuntimeError('injected ownership refresh failure')
            return orig(self)
        m.ProcessOwnership.refresh = refresh
    sys.exit(m.main(sys.argv[2:]))
''')

LAUNCHER = IDENT + textwrap.dedent('''\
    import signal, subprocess
    log, pidfile = sys.argv[1], sys.argv[2]
    def h(s, f): open(log, 'a').write('signal %d\\n' % s)
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGUSR1): signal.signal(s, h)
    w = subprocess.Popen(sys.argv[3:])  # same process group: this launcher is the shared-PG sentinel
    record(pidfile, w.pid)
    sys.exit(w.wait())
''')


def same(a, b): return json.dumps(a) == json.dumps(b)


class Registry:
    """Processes created by this control. Signals only after a fresh identity match."""
    def __init__(self): self.items, self.actions = [], []

    def add(self, ident):
        if ident and all(not same(ident, x) for x in self.items): self.items.append(ident)

    def add_file(self, path):
        if Path(path).exists():
            for line in Path(path).read_text().splitlines():
                if line.strip(): self.add(json.loads(line))

    def alive(self, ident):
        r = TABLE.read(ident['pid'])
        return bool(r and same(r['start'], ident['start']) and r['state'] != 'Z')

    def kill(self, ident, sig=signal.SIGKILL):
        r = TABLE.read(ident['pid'])
        if not (r and same(r['start'], ident['start']) and r['state'] != 'Z'): return 'gone'
        try:
            if r['pgid'] != ident['pgid'] or os.getsid(ident['pid']) != ident['sid']: return 'identity-changed'
            os.kill(ident['pid'], 0)
        except (ProcessLookupError, PermissionError) as e:
            return 'refused: ' + type(e).__name__
        os.kill(ident['pid'], sig); self.actions.append([ident['pid'], int(sig)]); return 'signalled'

    def reap_all(self):
        for ident in reversed(self.items): self.kill(ident)
        deadline = time.time() + 10
        while time.time() < deadline and any(self.alive(i) for i in self.items): time.sleep(0.05)
        return [i for i in self.items if self.alive(i)]


def ident_of(pid):
    r = TABLE.read(pid)
    return dict(pid=pid, start=r['start'], pgid=r['pgid'], sid=os.getsid(pid)) if r else None


class Fixture:
    def __init__(self, tmp, worker, modes=('ok',), state=None, prefix='', backend='cuda', inputs=None, dup=False):
        self.t = Path(tmp); t = self.t
        (t / 'root/runs').mkdir(parents=True); (t / 'root/SOURCE_SHA').write_text('mock-source\n')
        (t / 'smi.py').write_text(FAKE_SMI); (t / 'mock_job').write_text(f'#!{PY}\n' + MOCK_JOB)
        (t / 'mock_job').chmod(0o755)
        (t / 'fault_entry.py').write_text(FAULT_ENTRY); (t / 'launcher.py').write_text(LAUNCHER)
        smi = t / 'nvidia-smi'; smi.write_text(f'#!/bin/sh\nexec {PY} {t / "smi.py"} "$@"\n'); smi.chmod(0o755)
        self.binaries = t / 'binaries.json'
        self.binaries.write_text(json.dumps({'cuda-exp': dict(path=str(t / 'mock_job'), sha256=sha(t / 'mock_job'))}))
        q = [dict(id=f'J{i}-{m}', tier='C', backend=backend if i == 0 else 'cuda', arm='both', build='cuda-exp' if backend == 'cuda' or i else 'cpu-exp',
                  group='g', cwd=str(t), args=[m, '{OUT}'], inputs=inputs or {}, model=False) for i, m in enumerate(modes)]
        if dup: q.append(dict(q[0]))
        self.queue = t / 'queue.json'; self.queue.write_text(json.dumps(q, indent=1))
        self.n = len(q)
        st = dict(own=str(t / 'own.txt'), tree=str(t / 'tree.txt'), tree_ready=str(t / 'tree.ready'),
                  hold_flag=str(t / 'hold.flag'), held_marker=str(t / 'held.marker'),
                  smi_pids=str(t / 'smi_pids.txt'), counter=str(t / 'counter'), calls=str(t / 'calls.log'))
        st.update(state or {})
        self.state = t / 'state.json'; self.state.write_text(json.dumps(st))
        self.runs = t / 'root/runs-v3'
        self.prefix, self.worker = prefix, worker
        self.reg = Registry()

    def args(self, **over):
        a = dict(root=self.t / 'root', queue=self.queue, queue_sha256=sha(self.queue), expected_jobs=self.n,
                 runs_dir=self.runs, binaries=self.binaries, binaries_sha256=sha(self.binaries), uuid=UUID, cpu=0,
                 gpu_index=2, lock_dir=self.t, job_timeout=30, query_timeout=5, cleanup_grace=3,
                 smi=self.t / 'nvidia-smi', prefix=self.prefix)
        a.update(over)
        out = []
        for k, v in a.items(): out += ['--' + k.replace('_', '-'), str(v)]
        return out

    def start(self, fault='', **over):
        env = dict(os.environ, FAKE_SMI_STATE=str(self.state), FAKE_UUID=UUID, FAKE_FAULT_FLAG=str(self.t / 'fault.flag'),
                   V3_FAULT=fault)
        pidfile = self.t / f'worker-{time.time_ns()}.pid'
        cmd = [PY, '-B', str(self.t / 'launcher.py'), str(self.t / 'sentinel.log'), str(pidfile),
               PY, '-B', str(self.t / 'fault_entry.py'), str(self.worker)] + self.args(**over)
        p = subprocess.Popen(cmd, env=env, stdout=open(self.t / 'worker.out', 'a'), stderr=subprocess.STDOUT,
                             start_new_session=True)
        self.reg.add(ident_of(p.pid))
        # The launcher writes one complete JSON line; read only once the newline is present.
        deadline = time.time() + 10
        while time.time() < deadline and p.poll() is None:
            if pidfile.exists() and pidfile.read_text().endswith('\n'): break
            time.sleep(0.01)
        text = pidfile.read_text() if pidfile.exists() else ''
        self.worker_ident = json.loads(text.splitlines()[0]) if text.endswith('\n') else None
        if not self.worker_ident and p.poll() is None:
            raise RuntimeError('worker identity not recorded by launcher within 10 s')
        self.reg.add(self.worker_ident)
        return p

    def wait(self, p, timeout=60):
        try: return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired: return None

    def refresh_registry(self):
        for f in ('own.txt', 'tree.txt', 'smi_pids.txt'): self.reg.add_file(self.t / f)

    def receipts(self, kind):
        return [json.loads(p.read_text()) for p in sorted(self.runs.glob(kind + '-*.json'))] if self.runs.exists() else []

    def run(self, jid):
        p = self.runs / jid / 'RUN.json'
        return json.loads(p.read_text()) if p.exists() else None

    def lease_free(self):
        with open(self.t / 'motioncorr-gpu2-correctness.lock', 'a') as f:
            try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); return True
            except BlockingIOError: return False

    def sentinel_signals(self):
        p = self.t / 'sentinel.log'
        return p.read_text() if p.exists() else ''


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def wait_for(path, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(path).exists(): return True
        time.sleep(0.02)
    return False


def calls_started(f, n, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        c = f.t / 'calls.log'
        if c.exists() and f'start {n}' in c.read_text(): return True
        time.sleep(0.02)
    return False


# ---- controls -------------------------------------------------------------
def k_invalid(tmp, W):
    out = {}
    cases = {
        'queue_sha': dict(over=dict(queue_sha256='0' * 64)),
        'expected_count': dict(over=dict(expected_jobs=99)),
        'backend': dict(fx=dict(backend='cpu', modes=('ok', 'ok'))),
        'duplicate_id': dict(fx=dict(dup=True)),
        'binaries_sha': dict(over=dict(binaries_sha256='0' * 64)),
        'binary_hash': dict(tamper=True),
        'nonempty_runs': dict(nonempty=True),
    }
    ok = True
    for name, c in cases.items():
        d = Path(tmp) / name; d.mkdir(); out[name] = {}
        f = Fixture(d, W, **c.get('fx', {}))
        try:
            if c.get('tamper'):
                b = json.loads(f.binaries.read_text()); b['cuda-exp']['sha256'] = '1' * 64
                f.binaries.write_text(json.dumps(b))
            if c.get('nonempty'): f.runs.mkdir(); (f.runs / 'old-NOT_LAUNCHED').mkdir()
            over = dict(c.get('over', {}))
            if c.get('tamper'): over['binaries_sha256'] = sha(f.binaries)
            p = f.start(**over); code = f.wait(p)
            created = f.runs.exists() and not c.get('nonempty')
            res = code == 64 and not created and f.lease_free() and not (f.t / 'own.txt').exists()
            out[name].update(exit=code, runs_created=created, result=res)
            ok &= res
        finally:
            f.refresh_registry(); out[name]['leftovers'] = f.reg.reap_all()
            ok &= not out[name]['leftovers']
    return ok, out


def single(tmp, W, modes, state, check, fault='', prefix='', over=None, during=None, timeout=60, inputs=None):
    f = Fixture(tmp, W, modes=modes, state=state, prefix=prefix, inputs=inputs)
    detail = {}
    try:
        p = f.start(fault=fault, **(over or {}))
        if during: during(f, p, detail)
        code = f.wait(p, timeout)
        f.refresh_registry()
        detail.update(exit=code, stop=[r.get('reason') for r in f.receipts('STOP')],
                      final=[dict(code=r['code'], census=r['census']) for r in f.receipts('FINAL')],
                      sentinel=f.sentinel_signals())
        ok = check(f, code, detail)
    except Exception:
        detail['harness_error'] = traceback.format_exc(); ok = False
    finally:
        f.refresh_registry()
        detail['leftovers'] = f.reg.reap_all()
        detail['harness_signals'] = f.reg.actions
    return ok and not detail['leftovers'] and not detail.get('sentinel'), detail


def no_job(f): return not any(f.runs.glob('J*')) and not (f.t / 'own.txt').exists()


def controls(W):
    C = {}
    with tempfile.TemporaryDirectory() as t: C['K1 invalid binding refused before lease/output (exit 64)'] = k_invalid(t, W)
    for name, state in [('K2a ECC [N/A] fails closed', dict(ecc='[N/A]')), ('K2b ECC 1', dict(ecc='1')),
                        ('K2c UUID at wrong index', dict(index=1)), ('K3 foreign process before launch', dict(foreign=[424242]))]:
        with tempfile.TemporaryDirectory() as t:
            C[name] = single(t, W, ('ok',), state, lambda f, c, d: c == 75 and 'ADMISSION_REFUSED' in d['stop'] and no_job(f) and f.lease_free())
    for name, state, reason in [('K4a query nonzero exit', dict(fail_always=True), 'QUERY_FAILED'),
                                ('K4b query timeout (bounded, query session killed)', dict(sleep_always=8), 'QUERY_TIMEOUT'),
                                ('K4c malformed compute-app row', dict(malformed=True), 'QUERY_MALFORMED')]:
        with tempfile.TemporaryDirectory() as t:
            C[name] = single(t, W, ('ok',), state, lambda f, c, d, r=reason: c == 75 and r in d['stop'] and no_job(f)
                             and f.lease_free() and not any(f.reg.alive(i) for i in f.reg.items if i['pid'] in smi_pids(f)),
                             over=dict(query_timeout=1))

    def k5(f, c, d):
        recs = [f.run(j) for j in ('J0-ok', 'J1-ok')]
        d['records'] = [dict(status=r['status'], exit=r['exit'], witness=r['gpu_witness_uuids'],
                             sampler=r['resource']['sampler'], missing_keys=[k for k in CAMPAIGN_RUN_KEYS if k not in r]) for r in recs if r]
        return (c == 0 and len(d['records']) == 2 and all(x['status'] == 'EXITED' and x['exit'] == 0 and x['witness'] == [UUID]
                and x['sampler']['ok'] > 0 and x['sampler']['failed'] == 0 and not x['sampler']['foreign_on_target_during']
                and not x['missing_keys'] for x in d['records']) and d['final'][0]['census']['complete'] and f.lease_free())
    with tempfile.TemporaryDirectory() as t:
        C['K5 clean queue via /usr/bin/time prefix (grandchild route), witness, schema, census'] = single(
            t, W, ('ok', 'ok'), {}, k5, prefix='/usr/bin/time -l -o {out}/time-v.log')
    with tempfile.TemporaryDirectory() as t:
        C['K6 foreign appears mid-job: recorded, stop before next launch, census incomplete'] = single(
            t, W, ('touch_then_ok', 'ok'), dict(foreign_if_exists=[str(Path(t) / 'fault.flag'), [999999]]),
            lambda f, c, d: c == 75 and '999999' in json.dumps(f.run('J0-touch_then_ok')['resource'])
            and not (f.runs / 'J1-ok').exists() and not d['final'][0]['census']['complete'] and f.lease_free(), )
    with tempfile.TemporaryDirectory() as t:
        C['K7 mid-job query failure counted, stop before next launch'] = single(
            t, W, ('touch_then_ok', 'ok'), dict(fail_if_exists=str(Path(t) / 'fault.flag')),
            lambda f, c, d: c == 75 and f.run('J0-touch_then_ok')['resource']['sampler']['failed'] > 0
            and f.run('J0-touch_then_ok')['resource']['sampler']['ok'] > 0 and not (f.runs / 'J1-ok').exists())
    C['K8 restart after NOT_LAUNCHED cannot pass'] = k8(W)
    with tempfile.TemporaryDirectory() as t:
        C['K9 directory collision: nonzero stop, foreign directory untouched'] = single(
            t, W, ('ok',), dict(create_dir_on_call=[1, str(Path(t) / 'root/runs-v3/J0-ok')]),
            lambda f, c, d: c == 70 and 'DIRECTORY_COLLISION' in d['stop'] and not (f.runs / 'J0-ok/RUN.json').exists()
            and not (f.t / 'own.txt').exists())

    def cancel_on(n):
        def during(f, p, d):
            d['call_seen'] = calls_started(f, n)
            if d['call_seen'] and f.worker_ident: d['sigterm'] = f.reg.kill(f.worker_ident, signal.SIGTERM)
        return during
    with tempfile.TemporaryDirectory() as t:
        C['K10 cancel during main-loop admission query: no launch'] = single(
            t, W, ('ok',), dict(sleep_on_call={'1': 2}), lambda f, c, d: c == 4 and no_job(f) and f.lease_free(), during=cancel_on(1))
    with tempfile.TemporaryDirectory() as t:
        C['K11 cancel during pre-launch recheck: CANCELLED_BEFORE_LAUNCH, no Popen'] = single(
            t, W, ('ok',), dict(sleep_on_call={'2': 2}), lambda f, c, d: c == 4 and f.run('J0-ok')['status'] == 'CANCELLED_BEFORE_LAUNCH'
            and not (f.t / 'own.txt').exists() and f.lease_free(), during=cancel_on(2))

    def tree_ok(status, code, jid='J0-tree'):
        def chk(f, c, d):
            r = f.run(jid); tree = [json.loads(x) for x in (f.t / 'tree.txt').read_text().splitlines()] if (f.t / 'tree.txt').exists() else []
            d['tree'] = tree; d['tree_alive_after_worker'] = [i for i in tree if f.reg.alive(i)]
            d['status'] = r and r['status']; d['cleanup'] = r and r['cleanup']
            return (c == code and r and r['status'] == status and len(tree) == 3 and not d['tree_alive_after_worker']
                    and not r['cleanup']['errors'] and f.lease_free() and not (f.runs / 'J1-ok').exists())
        return chk
    with tempfile.TemporaryDirectory() as t:
        C['K12 timeout: child, setsid grandchild and detached sleep reaped; sentinel unsignalled (own-group exclusion: K22)'] = single(
            t, W, ('tree', 'ok'), {}, tree_ok('TIMEOUT', 78), over=dict(job_timeout=3))

    def cancel_tree(f, p, d):
        d['tree_ready'] = wait_for(f.t / 'tree.ready')
        f.refresh_registry()
        if f.worker_ident: d['sigterm'] = f.reg.kill(f.worker_ident, signal.SIGTERM)
    with tempfile.TemporaryDirectory() as t:
        C['K13 SIGTERM mid-job: tree reaped, CANCELLED, sentinel unsignalled (own-group exclusion: K22)'] = single(
            t, W, ('tree', 'ok'), {}, tree_ok('CANCELLED', 4), over=dict(job_timeout=600), during=cancel_tree)

    def held(f, p, d):
        d['receipt_seen'] = False
        deadline = time.time() + 40
        while time.time() < deadline and not d['receipt_seen']:
            d['receipt_seen'] = bool(f.receipts('CLEANUP_FAILED_LEASE_HELD')); time.sleep(0.1)
        f.refresh_registry()
        d['lease_held_while_alive'] = not f.lease_free()
        d['worker_alive'] = bool(f.worker_ident and f.reg.alive(f.worker_ident))
        d['run_status'] = (f.run('J0-flag_tree') or {}).get('status')
        d['kill_worker'] = f.reg.kill(f.worker_ident) if f.worker_ident else None
    with tempfile.TemporaryDirectory() as t:
        C['K14 observer error during timeout: CLEANUP_FAILED record and receipt, lease held'] = single(
            t, W, ('flag_tree', 'ok'), {}, lambda f, c, d: d['receipt_seen'] and d['lease_held_while_alive']
            and d['worker_alive'] and d['run_status'] == 'CLEANUP_FAILED' and not (f.runs / 'J1-ok').exists(),
            fault='refresh_after_flag', over=dict(job_timeout=2), during=held)
    with tempfile.TemporaryDirectory() as t:
        Path(t, 'fault.flag').write_text('x')
        C['K15 observer refresh failure before launch: no launch'] = single(
            t, W, ('ok',), {}, lambda f, c, d: c == 75 and not (f.t / 'own.txt').exists() and f.lease_free(), fault='refresh_after_flag')
    C['K16 PID reuse: exited owned PID with new birth is foreign'] = k16(W)
    with tempfile.TemporaryDirectory() as t:
        C['K17 input admission failure typed (exit 65)'] = single(
            t, W, ('ok',), {}, lambda f, c, d: c == 65 and f.run('J0-ok')['status'] == 'INPUT_ADMISSION_FAILED'
            and not (f.t / 'own.txt').exists(), inputs={str(Path(t) / 'state.json'): '0' * 64})
    with tempfile.TemporaryDirectory() as t:
        C['K18 final health query failure after complete census (exit 76)'] = single(
            t, W, ('ok',), dict(fail_if_exists=str(Path(t) / 'root/runs-v3/J0-ok/RUN.json')),
            lambda f, c, d: c == 76 and d['final'][0]['census']['complete'] and f.lease_free())

    # ---- R2 controls ----
    with tempfile.TemporaryDirectory() as t:
        Path(t, 'fault.flag').write_text('x')
        C['K15L observer failure before any launch, Linux restore emulated: exit 75, lease released'] = single(
            t, W, ('ok',), {}, lambda f, c, d: c == 75 and 'OBSERVER_FAILED_ZERO_JOBS' in d['stop'] and f.lease_free()
            and not f.receipts('CLEANUP_FAILED_LEASE_HELD') and not (f.t / 'own.txt').exists(),
            fault='refresh_after_flag,emulate_linux_restore')
    with tempfile.TemporaryDirectory() as t:
        C['K19a query held in flight across job exit, emulated adoption: clean exit 0'] = single(
            t, W, ('hold_exit', 'ok'), {}, lambda f, c, d: c == 0 and (f.t / 'held.marker').exists()
            and f.run('J0-hold_exit')['status'] == 'EXITED' and d['final'][0]['census']['complete'] and f.lease_free(),
            fault='emulate_adoption')

    def tree_hold(status, code):
        inner = tree_ok(status, code, 'J0-hold_tree')
        return lambda f, c, d: (f.t / 'held.marker').exists() and inner(f, c, d)
    with tempfile.TemporaryDirectory() as t:
        C['K19b query held in flight across timeout, emulated adoption: TIMEOUT 78, tree reaped'] = single(
            t, W, ('hold_tree', 'ok'), dict(hold_s=4.0), tree_hold('TIMEOUT', 78), fault='emulate_adoption', over=dict(job_timeout=2.5))

    def cancel_held(f, p, d):
        d['held'] = wait_for(f.t / 'held.marker'); d['tree_ready'] = wait_for(f.t / 'tree.ready')
        f.refresh_registry()
        if f.worker_ident: d['sigterm'] = f.reg.kill(f.worker_ident, signal.SIGTERM)
    with tempfile.TemporaryDirectory() as t:
        C['K19c query held in flight across cancellation, emulated adoption: CANCELLED 4, tree reaped'] = single(
            t, W, ('hold_tree', 'ok'), dict(hold_s=4.0), tree_hold('CANCELLED', 4), fault='emulate_adoption',
            over=dict(job_timeout=600), during=cancel_held)
    C['K20 query process never owned under emulated adoption (unit; positive control adopted)'] = k20(W)
    C['K22 own process group never signalled (unit, injected process view)'] = k22(W)
    with tempfile.TemporaryDirectory() as t:
        C['K23 OK requires a successful sample and the route witness'] = single(
            t, W, ('ok', 'ok'), dict(hide_own=True), lambda f, c, d: c == 75 and f.run('J0-ok')['status'] == 'EXITED'
            and 'route_witness_problem' in f.run('J0-ok') and not (f.runs / 'J1-ok').exists())
    with tempfile.TemporaryDirectory() as t:
        Path(t, 'afile').write_text('x')
        C['K24 error before the lease: typed stdout receipt, exit 74'] = single(
            t, W, ('ok',), {}, lambda f, c, d: c == 74 and 'PRELEASE_IO_ERROR' in (f.t / 'worker.out').read_text()
            and f.lease_free() and not (f.t / 'own.txt').exists(), over=dict(runs_dir=Path(t) / 'afile/runs'))
    return C


def load(W, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, W)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def k20(W):
    ns = {}; exec(EMULATE, ns)
    d, reg = {}, Registry()
    with tempfile.TemporaryDirectory() as t:
        f = Fixture(t, W, state=dict(sleep_always=2.0))
        m = load(W, 'gpu_worker_k20')
        class Own(ProcessOwnership): pass
        ns['emulate_linux_adoption'](Own)
        own = Own()
        os.environ.update(FAKE_SMI_STATE=str(f.state), FAKE_UUID=UUID)
        positive = None
        try:
            smi = m.Smi(str(f.t / 'nvidia-smi'), UUID, 2, 10, TABLE)
            th = __import__('threading').Thread(target=lambda: d.setdefault('query', smi.query()), daemon=True); th.start()
            deadline = time.time() + 10
            while time.time() < deadline and not (f.t / 'smi_pids.txt').exists(): time.sleep(0.02)
            time.sleep(0.2)
            qpids = sorted(smi_pids(f)); reg.add_file(f.t / 'smi_pids.txt')
            positive = subprocess.Popen(['sleep', '30'], start_new_session=True); reg.add(ident_of(positive.pid))
            time.sleep(0.2)
            own.refresh()
            owned = {r['pid'] for r in own.known_live()}
            d.update(query_pids=qpids, owned=sorted(owned), positive_pid=positive.pid,
                     query_pgids=[TABLE.read(q)['pgid'] if TABLE.read(q) else None for q in qpids], worker_pgid=os.getpgrp())
            ok = bool(qpids) and not (set(qpids) & owned) and positive.pid in owned
            th.join(15)
        except Exception:
            d['harness_error'] = traceback.format_exc(); ok = False
        finally:
            d['leftovers'] = reg.reap_all()
            if positive: positive.wait(5)
    return ok and not d['leftovers'], d


def k22(W):
    m = load(W, 'gpu_worker_k22')
    me = os.getpgrp()
    class Table:
        def group_live(self, g): return True
    class Own:
        errors = []; table = Table()
        def refresh(self): pass
        def known_live(self): return [dict(pid=900001, pgid=me, start=1), dict(pid=900002, pgid=900002, start=2)]
        def verified_group(self, g): return True
    class Root:
        pid = 900000
        def poll(self): return 0
    calls, real = [], os.killpg
    os.killpg = lambda g, s: calls.append([g, int(s)])
    try:
        signalled, errors = m.terminate_owned(Own(), Root(), 0.05)
    finally:
        os.killpg = real
    groups = sorted({g for g, _ in calls})
    d = dict(own_group=me, groups_signalled=groups, errors=errors)
    return me not in groups and 900002 in groups, d


def smi_pids(f):
    p = f.t / 'smi_pids.txt'
    return {json.loads(x)['pid'] for x in p.read_text().splitlines()} if p.exists() else set()


def k8(W):
    d = {}
    with tempfile.TemporaryDirectory() as t:
        f = Fixture(t, W, modes=('ok',), state=dict(foreign_from_call={'2': [777777]}))
        try:
            d['run1'] = f.wait(f.start()); d['run1_status'] = (f.run('J0-ok') or {}).get('status')
            d['run1_census'] = f.receipts('FINAL')[-1]['census'] if f.receipts('FINAL') else None
            # Clean GPU from here on, so only namespace/census logic decides runs 2 and 3.
            st = json.loads(f.state.read_text()); st['foreign_from_call'] = {}; f.state.write_text(json.dumps(st))
            d['run2_same_namespace'] = f.wait(f.start())
            d['run2_receipts_unchanged'] = (f.run('J0-ok') or {}).get('status') == 'NOT_LAUNCHED'
            d['run2_launched'] = (f.t / 'own.txt').exists()
            f.runs = f.t / 'root/runs-v3-second'
            d['run3_fresh_namespace'] = f.wait(f.start(runs_dir=f.runs))
        except Exception:
            d['harness_error'] = traceback.format_exc()
        finally:
            f.refresh_registry(); d['leftovers'] = f.reg.reap_all(); d['sentinel'] = f.sentinel_signals()
    ok = (d.get('run1') == 75 and d.get('run1_status') == 'NOT_LAUNCHED' and d['run1_census'] and not d['run1_census']['complete']
          and d.get('run2_same_namespace') not in (0, None) and d.get('run2_receipts_unchanged') and not d.get('run2_launched')
          and d.get('run3_fresh_namespace') == 0 and not d['leftovers'] and not d['sentinel'])
    return ok, d


def k16(W):
    import importlib.util
    spec = importlib.util.spec_from_file_location('gpu_worker_v3_k16', W)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    class FakeTable:
        def __init__(self, births): self.births = births
        def read(self, pid): return dict(pid=pid, ppid=1, pgid=pid, start=self.births[pid], state='S') if pid in self.births else None
    own = ProcessOwnership(table=FakeTable({4242: 222}))
    own.identities = {4242: 111}  # recorded as ours with an earlier birth
    pre = m.live_owned(own); post = m.live_owned(own)
    owned, foreign = m.classify([4242], pre, post)
    own2 = ProcessOwnership(table=FakeTable({4242: 111})); own2.identities = {4242: 111}
    owned2, foreign2 = m.classify([4242], m.live_owned(own2), m.live_owned(own2))
    d = dict(reused=dict(owned=owned, foreign=foreign), same_birth=dict(owned=owned2, foreign=foreign2))
    return foreign == [4242] and owned2 == [4242], d


def _terminate(*_):
    # The runner's bounded fallback sends SIGTERM first; unwinding runs every control's finally cleanup.
    raise KeyboardInterrupt('SIGTERM')


def main():
    signal.signal(signal.SIGTERM, _terminate)
    ap = argparse.ArgumentParser(); ap.add_argument('--json', required=True)
    ap.add_argument('--worker', default=str(TOOLS / 'gpu_worker_v4.py')); a = ap.parse_args()
    W = Path(a.worker).resolve()
    results = []
    for name, (ok, detail) in controls(W).items():
        results.append(dict(control=name, result='PASS' if ok else 'FAIL', detail=detail))
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
    Path(a.json).write_text(json.dumps(dict(schema='gpu-worker-v4-host-controls/1', python=sys.version, platform=sys.platform,
        worker=str(W), worker_sha256=sha(W), test_sha256=sha(__file__), ownership_sha256=sha(REPO / 'tools/multi_gpu/process_ownership.py'),
        results=results, limits='macOS host mocks; fake nvidia-smi for every query; ProcessOwnership polling mode, with '
        'test-only emulation of the Linux adoption rule where stated; Linux subreaper execution UNRUN; /usr/bin/time prefix '
        'tested, taskset prefix UNRUN; uninterruptible-sleep query hang not reproducible.'), indent=1, default=str) + '\n')
    sys.exit(0 if all(r['result'] == 'PASS' for r in results) else 1)


if __name__ == '__main__':
    main()
