"""Tests for driver_v5_1 (criteria frozen in AMENDMENT_M1_RESOURCE_RECEIPTS.md). Fake child only; no MotionCorr child, no movie.
Linux-only groups (real /proc sampling, real flock/lease controls, parent-death signal) run on cpu64 under the lane leases and are
reported as SKIPPED elsewhere (a skip is not a pass).

usage: python -B tests/test_driver_v5_1.py RESULT.json [group ...]   (real NumPy interpreter; threads <= 2)
"""
import json, os, shutil, signal, subprocess, sys, tempfile, threading, time, traceback
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import test_release_v5 as TR
import driver_v5_1 as D
import pair_decision_v5 as P5

LINUX = sys.platform.startswith('linux')
RESULTS, SKIPPED = [], []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''), flush=True)


def skip(name, why):
    SKIPPED.append({'name': name, 'why': why})
    print('SKIPPED ' + name + ' :: ' + why, flush=True)


def expect_code(name, code, fn):
    try:
        fn()
    except (D.DriverStop, P5.PairError) as e:
        record(name, e.code == code, 'code=%s' % e.code if e.code == code else 'wanted %s got %s: %s' % (code, e.code, e))
        return
    except BaseException as e:
        record(name, False, 'wrong exception %s: %s' % (type(e).__name__, e))
        return
    record(name, False, 'ACCEPTED but wanted %s' % code)


def fresh(fn, **kw):
    saved = (P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256, P5.COMMANDS_PATH, P5.COMMANDS_V5_SHA256, P5._score_arm, D._read_text, D._listdir)
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v51-') as t:
        try:
            return fn(TR.W5(t, **kw))
        except BaseException as e:
            record('INFRA fault in %s' % fn.__name__, False, ''.join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256, P5.COMMANDS_PATH, P5.COMMANDS_V5_SHA256, P5._score_arm, D._read_text, D._listdir = saved


def guard_ok(step):
    return {'step': step}


def release51(w):
    r = {'release_module_sha256': TR.sha((TR.V5DIR / 'pair_decision_v5.py').read_bytes()), 'driver_sha256': TR.sha((TR.V5DIR / 'driver_v5_1.py').read_bytes()),
         'admission_sha256': TR.sha(P5.ADMISSION_PATH.read_bytes()), 'delta_review_report_sha256': 'a' * 64, 'approved_by': 'parent'}
    w.dec.mkdir(exist_ok=True)
    (w.dec / 'PARENT_RELEASE.json').write_text(json.dumps(r))


def run51(w, **kw):
    return D.run_campaign(w.dec, execute=True, guard=kw.pop('guard', guard_ok), cpus=None, timeout=kw.pop('timeout', 30))


def pid_gone(pid, wait=3.0):
    t = time.time()
    while time.time() - t < wait:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if LINUX:
            try:
                if ' Z' in (open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1][:3]):
                    return True
            except OSError:
                return True
        time.sleep(0.05)
    return False


# ---- fake /proc ----------------------------------------------------------------------------------------------------------------
STATUS = 'Name:\t%s\nState:\tS (sleeping)\nPid:\t%d\nPPid:\t%d\nThreads:\t%d\nCpus_allowed_list:\t%s\nVmRSS:\t   1234 kB\n'


def fake_proc(spec):
    """spec: {pid: dict(ppid, threads, mask, children=[pids], fail=<exception or None>, stat=bool)} -> (_read_text, _listdir) substitutes."""
    def rt(path):
        parts = path.split('/')
        if len(parts) < 4 or parts[1] != 'proc':
            raise FileNotFoundError(path)
        pid = int(parts[2]); s = spec.get(pid)
        if s is None:
            raise FileNotFoundError(path)
        what = parts[3]
        if what == 'status':
            if s.get('fail_status'):
                raise s['fail_status']
            return STATUS % ('fakechild', pid, s['ppid'], s['threads'], s['mask'])
        if what == 'stat':
            if s.get('fail_stat'):
                raise s['fail_stat']
            return '%d (fake child) S %d 0 0 0 0 0 0 0 0 0 7 3 0 0 20 0 %d 0 0' % (pid, s['ppid'], s['threads'])
        if what == 'task' and parts[5] == 'children':
            if s.get('no_children_file'):
                raise FileNotFoundError(path)
            return ' '.join(map(str, s.get('children', []))) + ' '
        raise FileNotFoundError(path)

    def ld(path):
        parts = path.split('/')
        pid = int(parts[2]); s = spec.get(pid)
        if s is None:
            raise FileNotFoundError(path)
        return [str(pid + i) for i in range(s['threads'])]
    return rt, ld


# =============================== groups ===============================================================================================
def g_parse(w):
    st = D.parse_proc_status(STATUS % ('x', 5, 1, 3, '32-47'))
    record('parse /proc status', st['threads'] == 3 and st['cpus_allowed_list'] == '32-47' and st['ppid'] == 1 and st['vmrss_kb'] == 1234)
    record('parse /proc stat times (utime/stime)', D.parse_proc_stat_times('9 (a b) c) S 1 0 0 0 0 0 0 0 0 0 7 3 0 0') == (7, 3))
    locks = D.parse_proc_locks('1: FLOCK  ADVISORY  WRITE 4242 fd:00:1234 0 EOF\n2: POSIX  ADVISORY  READ 55 08:01:99 0 EOF\ngarbage\n')
    record('parse /proc/locks', locks == [('FLOCK', 'WRITE', 4242, 0xfd, 0, 1234), ('POSIX', 'READ', 55, 8, 1, 99)])
    ppid = {50: 40, 40: 30, 30: 1, 1: 0}
    record('ancestor chain through a wrapper', D.ancestor_pids(50, lambda p: ppid.get(p, 0)) == [40, 30, 1])
    dev = os.makedev(8, 1)
    E = lambda kind='FLOCK', mode='WRITE', pid=30, major=8, minor=1, ino=100: (kind, mode, pid, major, minor, ino)
    anc = [40, 30, 1]
    ok, _ = D.lease_owner([E()], dev, 100, anc); record('lease control: ours (held by an ancestor)', ok)
    ok, _ = D.lease_owner([], dev, 100, anc); record('lease control: unheld is refused', not ok)
    ok, why = D.lease_owner([E(pid=999)], dev, 100, anc); record('lease control: peer-held is refused', not ok and 'none of them an ancestor' in str(why), str(why))
    ok, why = D.lease_owner([E(pid=30, ino=77), E(pid=999, ino=100)], dev, 100, anc)
    record('lease control: lane holds an orphaned inode, a peer holds the recreated path', not ok and 'none of them an ancestor' in str(why), str(why))
    ok, _ = D.lease_owner([E(mode='READ')], dev, 100, anc); record('lease control: a read-mode entry is refused', not ok)
    ok, _ = D.lease_owner([E(kind='POSIX')], dev, 100, anc); record('lease control: a POSIX lock is refused', not ok)
    ok, _ = D.lease_owner([E(major=9)], dev, 100, anc); record('lease control: same inode on another device is refused', not ok)
    ok, _ = D.lease_owner([E(pid=40)], dev, 100, [40, 30, 1]); record('lease control: an intermediate wrapper owner is an ancestor too', ok)


def g_sampler(w):
    rt, ld = fake_proc({1000: dict(ppid=1, threads=3, mask='40-41', children=[1001]), 1001: dict(ppid=1000, threads=1, mask='40-41')})
    D._read_text, D._listdir = rt, ld
    r = D.ResourceRecorder(); r.proc_available = True
    for t in (0, 20, 40):
        r.sample(1000, t)
    rc = r.receipt()
    s = rc['summary']
    record('multi-thread child with a differing mask: OBSERVED, receipts keep what /proc said (not the expected 32-47)',
           rc['status'] == 'OBSERVED' and s['max_threads'] == 3 and s['max_tasks'] == 3 and s['distinct_cpus_allowed_lists'] == ['40-41'] and s['processes_seen'] == [1000, 1001] and rc['n_samples'] == 3, str(s))
    record('resource keys are non-empty when observable', rc['samples'] and rc['samples'][0]['procs'][0]['name'] == 'fakechild' and rc['samples'][0]['procs'][0]['cpus_allowed_list'] == '40-41' and rc['samples'][0]['procs'][0]['utime_ticks'] == 7)
    # a read failure other than "process already gone" is recorded, never hidden
    rt, ld = fake_proc({1000: dict(ppid=1, threads=2, mask='32-47', fail_stat=PermissionError('denied'))})
    D._read_text, D._listdir = rt, ld
    r = D.ResourceRecorder(); r.proc_available = True; r.sample(1000, 0)
    rc = r.receipt()
    record('a read failure gives PARTIAL with the error kept', rc['status'] == 'PARTIAL' and rc['read_failures'] >= 1 and 'PermissionError' in rc['first_errors'][0], str(rc['first_errors']))
    # nothing readable
    rt, ld = fake_proc({})
    D._read_text, D._listdir = rt, ld
    r = D.ResourceRecorder(); r.proc_available = True; r.sample(1000, 0)
    rc = r.receipt()
    record('child gone before the first read gives UNOBSERVED with a reason (no invented sample)', rc['status'] == 'UNOBSERVED' and rc['reason'] and rc['summary']['max_threads'] == 0 and rc['stored_samples'] == 1 and rc['samples'][0]['procs'] == [] and rc['vanished_reads'] >= 1)
    r = D.ResourceRecorder(); r.proc_available = False; r.sample(1000, 0)
    record('no /proc on the host is stated as the reason', r.receipt()['status'] == 'UNOBSERVED' and 'no /proc' in r.receipt()['reason'])
    # truncation: summary keeps updating beyond the stored cap
    spec = {1000: dict(ppid=1, threads=1, mask='32-47')}
    rt, ld = fake_proc(spec); D._read_text, D._listdir = rt, ld
    r = D.ResourceRecorder(cap=3); r.proc_available = True
    for i in range(10):
        if i == 7:
            spec[1000]['threads'] = 5
        r.sample(1000, i * 20)
    rc = r.receipt()
    record('truncation is flagged and the summary still sees the later 5 threads', rc['truncated'] and rc['stored_samples'] == 3 and rc['n_samples'] == 10 and rc['summary']['max_threads'] == 5)
    # missing children files are counted, not silently treated as "no descendants"
    spec = {1000: dict(ppid=1, threads=1, mask='32-47', no_children_file=True)}
    rt, ld = fake_proc(spec); D._read_text, D._listdir = rt, ld
    r = D.ResourceRecorder(); r.proc_available = True; r.sample(1000, 0)
    record('a missing children file is recorded', r.receipt()['children_file_missing_reads'] >= 1)


def _stage_launch(w, case, arm, **kw):
    ctx = P5.context(w.dec)
    d = D.stage_run(ctx, case, arm)
    return D.launch(ctx, case, arm, d, ctx.expected(case, arm), cpus=None, timeout=kw.pop('timeout', 30), guard_receipt={}, **kw), d


def g_launch(w):
    r, d = _stage_launch(w, 'noisy', 'OFF')
    rs = r['resource_samples']
    record('RUN.json carries resource_samples with a stated status', rs['status'] in ('OBSERVED', 'PARTIAL', 'UNOBSERVED') and 'schedule' in rs and r['child_pid'] > 0)
    if rs['status'] == 'UNOBSERVED':
        record('a fast/unreadable child is reported UNOBSERVED honestly (reason present, no invented values)', bool(rs['reason']) and rs['summary']['max_threads'] == 0)
    else:
        record('a fast child that was observed has real reads behind it', rs['n_samples'] > 0 and rs['summary']['max_threads'] >= 1)
    try:
        P5.admit_single('noisy', 'OFF'); record('the extra resource_samples key leaves admit_producer passing', True)
    except Exception as e:
        record('the extra resource_samples key leaves admit_producer passing', False, repr(e))
    # a slower fake child with synthetic /proc: enough samples, mask as read, no gate on the thread count
    w.modes({'affine/OFF': {'sleep': 0.5}})
    def rt2(path):
        pid = int(path.split('/')[2]); spec = {pid: dict(ppid=1, threads=3, mask='40-41')}
        return fake_proc(spec)[0](path)
    def ld2(path):
        pid = int(path.split('/')[2]); return fake_proc({pid: dict(ppid=1, threads=3, mask='40-41')})[1](path)
    D._read_text, D._listdir = rt2, ld2
    r, d = _stage_launch(w, 'affine', 'OFF')
    rs = r['resource_samples']
    record('slow child: enough samples at the 20 ms schedule and OBSERVED', rs['status'] == 'OBSERVED' and rs['n_samples'] >= 8, 'n=%d' % rs['n_samples'])
    record('Threads 3 and mask 40-41 are receipts, not a stop (run exit 0, no gate)', rs['summary']['max_threads'] == 3 and rs['summary']['distinct_cpus_allowed_lists'] == ['40-41'] and r['exit'] == 0)
    w.modes({'pedestal/OFF': {'exit': 1}, 'zero/OFF': {'sleep': 3}})
    r, d = _stage_launch(w, 'pedestal', 'OFF')
    record('a non-zero exit still carries resource_samples', r['exit'] == 1 and r['resource_samples']['n_samples'] >= 1)
    r, d = _stage_launch(w, 'zero', 'OFF', timeout=0.5)
    record('a timeout still carries resource_samples and is marked', r['timed_out'] and r['resource_samples']['n_samples'] >= 1 and r['resource_samples']['summary']['last_ms'] >= 400)


def _child_dead(w, case='noisy'):
    r = json.loads((w.ev / case / 'OFF' / 'RUN.json').read_text())
    return r, pid_gone(r['child_pid'])


def g_kbd(w):
    release51(w); w.modes({'noisy/OFF': {'sleep': 30}})
    calls = {'n': 0}
    real = D.ResourceRecorder.sample
    def sample(self, pid, t):
        calls['n'] += 1
        if calls['n'] == 3:
            raise KeyboardInterrupt()
        return real(self, pid, t)
    D.ResourceRecorder.sample = sample
    try:
        try:
            run51(w); record('KeyboardInterrupt during the wait propagates', False, 'returned')
        except KeyboardInterrupt:
            record('KeyboardInterrupt during the wait propagates', True)
    finally:
        D.ResourceRecorder.sample = real
    r, gone = _child_dead(w)
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    record('own child is reaped after KeyboardInterrupt', gone and r['aborted'] and 'KeyboardInterrupt' in r['aborted'] and r['exit'] is not None)
    record('ledger keeps the real exception and a STOP', led[-1]['event'] == 'STOP' and 'KeyboardInterrupt' in led[-1]['exception'] and any(e.get('aborted') for e in led if e['event'] == 'finished'))
    record('no next launch after cleanup', sum(1 for e in led if e['event'] == 'launching') == 1 and sorted(p.name for p in w.ev.iterdir()) == ['noisy'])


def g_sigterm(w):
    release51(w); w.modes({'noisy/OFF': {'sleep': 30}})
    prev_handler = signal.getsignal(signal.SIGTERM)
    timer = threading.Timer(0.6, os.kill, [os.getpid(), signal.SIGTERM]); timer.start()
    try:
        try:
            run51(w); record('SIGTERM during the wait is raised inside the campaign', False, 'returned')
        except D.Terminated:
            record('SIGTERM during the wait is raised inside the campaign', True)
    finally:
        timer.cancel()
    r, gone = _child_dead(w)
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    record('own child is reaped after SIGTERM', gone and r['aborted'] and 'Terminated' in r['aborted'])
    record('ledger keeps SIGTERM as the real cause, no next launch', led[-1]['event'] == 'STOP' and 'Terminated' in led[-1]['exception'] and sum(1 for e in led if e['event'] == 'launching') == 1)
    record('the previous SIGTERM handler is restored', signal.getsignal(signal.SIGTERM) == prev_handler)


def g_sampler_error(w):
    release51(w); w.modes({'noisy/OFF': {'sleep': 30}})
    calls = {'n': 0}
    real = D.ResourceRecorder.sample
    def sample(self, pid, t):
        calls['n'] += 1
        if calls['n'] == 3:
            raise RuntimeError('sampler broke')
        return real(self, pid, t)
    D.ResourceRecorder.sample = sample
    try:
        try:
            run51(w); record('unexpected exception in the wait propagates', False, 'returned')
        except RuntimeError as e:
            record('unexpected exception in the wait propagates', 'sampler broke' in str(e))
    finally:
        D.ResourceRecorder.sample = real
    r, gone = _child_dead(w)
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    record('child reaped, aborted RUN.json, STOP carries RuntimeError, one launch only', gone and 'RuntimeError' in r['aborted'] and led[-1]['event'] == 'STOP' and 'RuntimeError' in led[-1]['exception'] and sum(1 for e in led if e['event'] == 'launching') == 1)


def g_popen(w):
    release51(w)
    w.binpath.chmod(0o644)  # same bytes (the pin holds) but not executable: Popen fails
    expect_code('Popen failure is a LAUNCH stop', 'LAUNCH', lambda: run51(w))
    r = json.loads((w.ev / 'noisy' / 'OFF' / 'RUN.json').read_text())
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    record('Popen failure keeps a RUN.json with the real exception and a ledger STOP, no next launch', r['launch_error'] and 'PermissionError' in r['launch_error'] and r['exit'] is None and r['child_pid'] is None and led[-1]['event'] == 'STOP' and sum(1 for e in led if e['event'] == 'launching') == 1)


def g_guard_fields(w):
    if not LINUX:
        skip('real_guard receipt fields and the free-disk floor', 'needs Linux /proc and /proc/locks (run on cpu64 under the lane)')
        return
    pol = dict(w.adm['fresh_venue_resource_admission'], campaign_root=str(w.s), cpus=os.environ.get('V51_TEST_CPUS', '32-47'), max_foreign_busy_cores=1000, min_available_mem_mb=1, prior_scratch_bytes=123, scratch_cap_bytes=1 << 50)
    adm = {'fresh_venue_resource_admission': pol}
    rcpt = D.real_guard(adm, 'test')
    record('real guard under the real lane: ancestor-owned leases, free disk and the frozen-prior label', rcpt['free_bytes'] > 0 and rcpt['free_floor_bytes'] == 1 << 30 and rcpt['prior_scratch_frozen'] is True and len(rcpt['lease_owner_pids']) == len(D.overlapping_locks(pol['cpus'])), str({k: rcpt[k] for k in ('free_bytes', 'prior_scratch_frozen')}))
    expect_code('free disk below the floor is refused', 'GUARD', lambda: D.real_guard({'fresh_venue_resource_admission': dict(pol, min_free_bytes=1 << 62)}, 'test'))


# ---- Linux real-process controls --------------------------------------------------------------------------------------------------
CHECKER = '''
import os, sys, json
sys.path.insert(0, %r)
import driver_v5_1 as D
st = os.stat(sys.argv[1])
entries = D.parse_proc_locks(open('/proc/locks').read())
anc = D.ancestor_pids(os.getpid(), lambda p: D.parse_proc_status(open('/proc/%%d/status' %% p).read())['ppid'])
ok, why = D.lease_owner(entries, st.st_dev, st.st_ino, anc)
print(json.dumps([ok, str(why)]))
'''
HOLDER = '''
import fcntl, sys, time
f = open(sys.argv[1], 'a+'); fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(float(sys.argv[2]))
'''


def _check(path, wrapper=False):
    cmd = [sys.executable, '-c', CHECKER % str(HERE.parent), str(path)]
    if wrapper:
        cmd = ['bash', '-c', ' '.join(subprocess.list2cmdline([c]) for c in cmd) + '; true']
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip().splitlines()[-1]
    return json.loads(out)


def g_linux_locks(w):
    import fcntl
    if not LINUX:
        skip('real flock lease controls', 'needs Linux /proc/locks'); return
    d = Path(w.s) / 'locks'; d.mkdir()
    a = d / 'ours.lock'; fa = open(a, 'a+'); fcntl.flock(fa, fcntl.LOCK_EX)
    record('real control: ours (the test process is the ancestor owner)', _check(a)[0] is True)
    record('real control: an intermediate bash wrapper between owner and checker', _check(a, wrapper=True)[0] is True)
    b = d / 'unheld.lock'; b.write_text('')
    ok, why = _check(b); record('real control: unheld is refused', ok is False, why)
    c = d / 'peer.lock'
    peer = subprocess.Popen([sys.executable, '-c', HOLDER, str(c), '30'], stdout=subprocess.PIPE, text=True); peer.stdout.readline()
    ok, why = _check(c); record('real control: held by a peer (sibling) is refused', ok is False and 'ancestor' in why, why)
    e = d / 'recreated.lock'; fe = open(e, 'a+'); fcntl.flock(fe, fcntl.LOCK_EX)  # we hold the ORIGINAL inode
    os.unlink(e)
    peer2 = subprocess.Popen([sys.executable, '-c', HOLDER, str(e), '30'], stdout=subprocess.PIPE, text=True); peer2.stdout.readline()  # peer holds the recreated path
    ok, why = _check(e); record('real control: lane holds an orphaned inode, a peer holds the recreated path: refused', ok is False and 'ancestor' in why, why)
    peer.kill(); peer2.kill(); peer.wait(); peer2.wait()


def g_linux_sampling(w):
    if not LINUX:
        skip('real /proc sampling of a multi-thread child', 'needs Linux /proc'); return
    code = ('import subprocess, threading, time, os\n'
            'ts = [threading.Thread(target=time.sleep, args=(1.0,)) for _ in range(3)]\n[t.start() for t in ts]\n'
            'g = subprocess.Popen(["sleep", "1.0"])\n'
            'print(sorted(os.sched_getaffinity(0))[0], flush=True)\ntime.sleep(1.0)\n')
    cpus = '%d-%d' % (min(os.sched_getaffinity(0)), min(os.sched_getaffinity(0)) + 1)
    p = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, start_new_session=True, preexec_fn=D._child_preexec(cpus))
    rec = D.ResourceRecorder()
    rc = D._wait_with_sampling(p, 20, rec)
    r = rec.receipt(); s = r['summary']
    record('real child: OBSERVED with Threads > 1 and the task count', rc == 0 and r['status'] in ('OBSERVED', 'PARTIAL') and s['max_threads'] >= 4 and s['max_tasks'] >= 4, str(s))
    record('real child: the mask is what the kernel reports for the child (set 2 CPUs), not an expected copy', cpus in s['distinct_cpus_allowed_lists'], str(s['distinct_cpus_allowed_lists']))
    record('real child: the grandchild is seen through the children files, or the missing files are counted', len(s['processes_seen']) >= 2 or r['children_file_missing_reads'] > 0, str(s['processes_seen']))
    record('real child: immediate sample then 20 ms polls give enough samples', r['n_samples'] >= 20, 'n=%d' % r['n_samples'])


def g_linux_pdeath(w):
    if not LINUX:
        skip('parent-death signal', 'needs Linux prctl'); return
    driver = ('import subprocess, sys, time\nsys.path.insert(0, %r)\nimport driver_v5_1 as D\n'
              'pre = D._child_preexec(None) if sys.argv[1] == "with" else None\n'
              'p = subprocess.Popen(["sleep", "60"], start_new_session=True, preexec_fn=pre)\nprint(p.pid, flush=True)\ntime.sleep(60)\n') % str(HERE.parent)
    pids = {}
    for mode in ('with', 'without'):
        mini = subprocess.Popen([sys.executable, '-c', driver, mode], stdout=subprocess.PIPE, text=True)
        pids[mode] = int(mini.stdout.readline()); time.sleep(0.2)
        mini.kill(); mini.wait()
    record('parent-death signal: the child dies when the driver is SIGKILLed', pid_gone(pids['with'], 3.0))
    record('control without the signal: the child survives (so the test discriminates)', not pid_gone(pids['without'], 1.0))
    os.kill(pids['without'], signal.SIGKILL)


GROUPS = {'parse': g_parse, 'sampler': g_sampler, 'launch': g_launch, 'kbd': g_kbd, 'sigterm': g_sigterm, 'sampler_error': g_sampler_error, 'popen': g_popen,
          'guard_fields': g_guard_fields, 'linux_locks': g_linux_locks, 'linux_sampling': g_linux_sampling, 'linux_pdeath': g_linux_pdeath}


def main(result_path, only=None):
    for name, fn in GROUPS.items():
        if only and name not in only:
            continue
        fresh(fn)
    failed = [r for r in RESULTS if not r['ok']]
    Path(result_path).write_text(json.dumps({'total': len(RESULTS), 'failed': len(failed), 'skipped': SKIPPED, 'results': RESULTS}, indent=1, allow_nan=False) + '\n')
    print('TOTAL %d FAILED %d SKIPPED %d' % (len(RESULTS), len(failed), len(SKIPPED)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], set(sys.argv[2:]) or None))
