#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One retained serial control suite for gpu_worker_v6_1 (CONTRACT-v6.md + AMENDMENT-v6.1.md; replaces the r2 runner after R3-M1).

usage: run_v6_1_controls.py BASE --session-id ID --owner-pid PID --owner-birth JSON
                          --expect-worker SHA --expect-harness SHA

Admission (pure function `admission`, unit-tested on synthetic process tables):
- the owner (the author's Claude process) is given explicitly by PID and birth; it must be in this
  runner's ancestor chain, have exactly that birth, and carry an exact --resume=<id> / --resume <id>
  token. Substrings are not used, so the runner's own --session-id never selects the runner;
- another author is any process outside the owner's process tree carrying that exact token (the
  owner's own helpers, such as T3's parent-death watchdog, are inside its tree);
- a control process is one whose argv names test_gpu_worker_v*.py, run_v[456](?:_1)?_controls*.py or a
  gpu_worker_v*_controls* path, outside this runner's own ancestor chain;
- the 1- and 5-minute load averages must not exceed the logical CPU count.
A refusal writes REFUSED_UNRUN and exits 75; there is no waiting or retry. The load check is a
resource admission check, not a numerical gate.

Run: a nonblocking lifetime fcntl lease on BASE/.lease; an immutable namespace
BASE/attempt-<UTC>-<uuid4>/ with TMPDIR inside it; frozen, hashed copies of every input; then, serially,
the real worker's full harness and each targeted mutant from v6_1_mutants.json with --only, each in its
own session under a 180 s bound. A bound overrun gets SIGTERM then SIGKILL only after a fresh
PID/birth/session/UID check; if that identity cannot be established the runner records
CLEANUP_UNVERIFIED_LEASE_HELD and keeps the lease until an operator stops it.
"""
import fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = next(p for p in [TOOLS, *TOOLS.parents] if (p / 'tools/multi_gpu/process_ownership.py').exists())
sys.path.insert(0, str(REPO / 'tools/multi_gpu'))
from process_ownership import ProcessTable  # noqa: E402

INPUTS = {'worker': TOOLS / 'gpu_worker_v6_1.py', 'harness': TOOLS / 'test_gpu_worker_v6_1.py',
          'mutants': TOOLS / 'v6_1_mutants.json', 'runner': Path(__file__).resolve(), 'campaign': TOOLS / 'campaign.py',
          'process_ownership': REPO / 'tools/multi_gpu/process_ownership.py'}
CONTROL_RE = re.compile(r'(?:^|[\s/])(?:test_gpu_worker_v\d+(?:_1)?\.py|run_v[456](?:_1)?_controls\w*\.py)(?:\s|$)|gpu_worker_v\d+(?:_1)?_controls')
BOUND_S = 180


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def utc(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def has_resume_token(cmd, sid):
    tok = cmd.split()
    return f'--resume={sid}' in tok or any(a == '--resume' and b == sid for a, b in zip(tok, tok[1:]))


def admission(rows, my_pid, owner_pid, owner_birth, sid):
    """Pure admission decision over rows of dict(pid, ppid, uid, cmd[, start])."""
    by = {r['pid']: r for r in rows}
    chain, p = [], my_pid
    while p in by and p not in chain:
        chain.append(p); p = by[p]['ppid']
    d = dict(ancestor_chain=chain, owner_pid=owner_pid)
    if owner_pid not in chain: return False, 'owner PID is not an ancestor of this runner', d
    if json.dumps(by[owner_pid].get('start')) != json.dumps(owner_birth):
        return False, 'owner birth does not match', dict(d, owner_start=by[owner_pid].get('start'))
    if not has_resume_token(by[owner_pid]['cmd'], sid): return False, 'owner lacks the exact --resume token', d
    kids = {}
    for r in rows: kids.setdefault(r['ppid'], []).append(r['pid'])
    family, todo = {owner_pid}, [owner_pid]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in family: family.add(c); todo.append(c)
    authors = [r for r in rows if r['pid'] not in family and has_resume_token(r['cmd'], sid)]
    controls = [r for r in rows if r['pid'] not in chain and CONTROL_RE.search(r['cmd'])]
    d.update(other_authors=authors, control_processes=controls, owner_family_size=len(family))
    if authors: return False, 'another process of the author session is live', d
    if controls: return False, 'another v4/v5/v6/v6.1 control process is live', d
    return True, 'admitted', d


def processes():
    out = subprocess.run(['ps', '-axo', 'pid=,ppid=,uid=,command='], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        f = line.split(None, 3)
        if len(f) == 4: rows.append(dict(pid=int(f[0]), ppid=int(f[1]), uid=int(f[2]), cmd=f[3]))
    return rows


def run_bounded(cmd, cwd, env, log, rec):
    t = ProcessTable()
    with open(log, 'w') as so:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=so, stderr=subprocess.STDOUT, start_new_session=True)
        birth = t.read(p.pid)
        rec.update(pid=p.pid, start=birth and birth['start'], argv=cmd, start_utc=utc())
        try:
            code = p.wait(timeout=BOUND_S)
        except subprocess.TimeoutExpired:
            rec['fallback'] = []
            code = None
            for s, wait in ((signal.SIGTERM, 60), (signal.SIGKILL, 10)):
                cur = t.read(p.pid)
                if not (cur and birth and json.dumps(cur['start']) == json.dumps(birth['start']) and os.getsid(p.pid) == p.pid):
                    if p.poll() is None:
                        rec['fallback'].append(['IDENTITY_UNVERIFIED', utc()]); return 'UNVERIFIED'
                    break
                os.kill(p.pid, 0); os.kill(p.pid, s); rec['fallback'].append([int(s), utc()])
                try: code = p.wait(timeout=wait); break
                except subprocess.TimeoutExpired: pass
    rec.update(exit=code, end_utc=utc())
    return code


def main():
    base = Path(sys.argv[1]).resolve()
    arg = lambda k: sys.argv[sys.argv.index(k) + 1]
    sid, owner_pid, owner_birth = arg('--session-id'), int(arg('--owner-pid')), json.loads(arg('--owner-birth'))
    exp = dict(worker=arg('--expect-worker'), harness=arg('--expect-harness'))
    base.mkdir(parents=True, exist_ok=True)
    ns = base / f"attempt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4()}"
    ns.mkdir()
    rec = dict(schema='gpu-worker-v6.1-controls/1', namespace=ns.name, start_utc=utc(), session_id=sid, owner_pid=owner_pid,
               owner_birth=owner_birth, runner_pid=os.getpid(), uid=os.getuid(), ncpu=os.cpu_count(), load_avg=os.getloadavg(),
               numeric_threads=1, inputs={k: dict(path=str(p), sha256=sha(p)) for k, p in INPUTS.items()})
    def write(): (ns / 'ATTEMPT.json').write_text(json.dumps(rec, indent=1, default=str) + '\n')
    def refuse(reason, **d):
        rec.update(status='REFUSED_UNRUN', reason=reason, end_utc=utc(), **d); write()
        print(ns.name, 'REFUSED_UNRUN', reason); sys.exit(75)
    lease = open(base / '.lease', 'a')
    try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: refuse('attempts-dir lease held by another runner')
    rows = processes()
    for r in rows:
        if r['pid'] == owner_pid:
            b = ProcessTable().read(owner_pid); r['start'] = b and b['start']
    ok, reason, det = admission(rows, os.getpid(), owner_pid, owner_birth, sid)
    rec['admission'] = det
    if not ok: refuse(reason)
    l1, l5, _ = os.getloadavg()
    if l1 > os.cpu_count() or l5 > os.cpu_count(): refuse(f'load average {l1:.2f}/{l5:.2f} exceeds {os.cpu_count()} logical CPUs')
    for k in exp:
        if rec['inputs'][k]['sha256'] != exp[k]: refuse('input hash differs from expected', expected=exp)
    frozen = ns / 'frozen'; (frozen / 'tools/multi_gpu').mkdir(parents=True)
    for k, p in INPUTS.items():
        dst = frozen / ('tools/multi_gpu' if k == 'process_ownership' else '') / p.name
        shutil.copy2(p, dst); assert sha(dst) == rec['inputs'][k]['sha256']
    (ns / 'tmp').mkdir()
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', TMPDIR=str(ns / 'tmp'))
    harness = frozen / 'test_gpu_worker_v6_1.py'
    plan = [('worker-' + g, frozen / 'gpu_worker_v6_1.py', None, g) for g in ('base', 'r3', 'r4')]
    mutants = json.loads((frozen / 'v6_1_mutants.json').read_text())
    src = (frozen / 'gpu_worker_v6_1.py').read_text()
    for name, spec in mutants.items():
        s = src
        for a, b in spec['replace']:
            if s.count(a) != 1: refuse(f'mutant {name}: replacement target not unique')
            s = s.replace(a, b)
        path = frozen / f'_v6_1mutant_{name}.py'; path.write_text(s)
        plan.append((name, path, spec['only'], None))
    rec['status'] = 'RUNNING'; rec['runs'] = []; write()
    for name, worker, only, group in plan:
        r = dict(name=name, worker=str(worker), worker_sha256=sha(worker), only=only)
        rec['runs'].append(r)
        cmd = [sys.executable, '-B', str(harness), '--json', str(ns / f'controls-{name}.json'), '--worker', str(worker)]
        if only: cmd += ['--only', ','.join(only)]
        else: cmd += ['--group', group]
        size = sum(p.stat().st_size for p in ns.rglob('*') if p.is_file())
        if size > 256 * 1024**2: refuse('scratch cap 256 MiB exceeded', scratch_bytes=size)
        code = run_bounded(cmd, str(ns), env, ns / f'stdout-{name}.log', r)
        write()
        if code == 'UNVERIFIED':
            rec.update(status='CLEANUP_UNVERIFIED_LEASE_HELD', end_utc=utc()); write()
            print(ns.name, 'CLEANUP_UNVERIFIED_LEASE_HELD')
            while True: signal.pause()
        result_path = ns / f'controls-{name}.json'
        try:
            data = json.loads(result_path.read_text())
            rows = data['results']
            if not rows: raise ValueError('empty controls results')
            if only:
                failed = {x['control'].split()[0] for x in rows if x['result'] == 'FAIL'}
                r['verdict'] = 'PASS' if set(only) <= failed else 'FAIL'
            else:
                r['verdict'] = 'PASS' if all(x['result'] in ('PASS', 'UNRUN') for x in rows) else 'FAIL'
            r['controls_sha256'] = sha(result_path)
        except Exception as e:
            r.update(verdict='UNRUN', result_error=repr(e))
        write()
        if r['verdict'] != 'PASS':
            rec.update(status='STOPPED_FAILED_CONTROLS', end_utc=utc()); write()
            print(ns.name, rec['status'], name, r['verdict']); return 1
    after = {k: sha(p) for k, p in INPUTS.items()}
    rec.update(status='RAN', end_utc=utc(), load_avg_end=os.getloadavg(),
               inputs_changed_during_attempt=[k for k in INPUTS if after[k] != rec['inputs'][k]['sha256']],
               leftover_namespace_processes=[r for r in processes() if str(ns) in r['cmd']])
    write()
    print(ns.name, 'RAN', [(r['name'], r.get('exit')) for r in rec['runs']])
    sys.exit(0)


if __name__ == '__main__':
    sys.exit(main())
