#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run ONE retained real-worker attempt of test_gpu_worker_v4.py (r2 runner, after the 23:48Z owner collision).

usage: run_v4_controls_r2.py ATTEMPTS_DIR --session-id ID --expect-worker SHA --expect-harness SHA

- Takes a nonblocking fcntl lease on ATTEMPTS_DIR/.lease for its whole life. If the lease is held,
  or another process of the same author session (argv contains --session-id, outside this runner's
  own ancestor chain), or another v4 runner/harness process exists, or the 1- or 5-minute load
  average exceeds the logical CPU count, it writes a REFUSED record (UNRUN) and exits 75. It never
  waits or retries. The load check is a resource admission check, not a numerical gate.
- Each invocation gets an immutable namespace ATTEMPTS_DIR/attempt-<UTC>-<uuid4>/ created with mkdir
  (never reused). Worker, harness, this runner, campaign.py and process_ownership.py are copied
  there and hashed before launch; the worker and harness must equal --expect-worker and
  --expect-harness. The harness runs from the frozen copies with the frozen worker.
- The harness runs in its own session; the actual exit is propagated. After it exits, the runner
  re-hashes the live inputs and records whether any changed during the attempt, and scans for
  leftover mock processes by command line (read-only; it signals nothing).
- A bounded fallback (1200 s) sends SIGTERM and then SIGKILL to the harness only after a fresh
  PID/birth/session/UID check.
"""
import fcntl, hashlib, json, os, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = next(p for p in [TOOLS, *TOOLS.parents] if (p / 'tools/multi_gpu/process_ownership.py').exists())
sys.path.insert(0, str(REPO / 'tools/multi_gpu'))
from process_ownership import ProcessTable  # noqa: E402

INPUTS = {'worker': TOOLS / 'gpu_worker_v4.py', 'harness': TOOLS / 'test_gpu_worker_v4.py',
          'runner': Path(__file__).resolve(), 'campaign': TOOLS / 'campaign.py',
          'process_ownership': REPO / 'tools/multi_gpu/process_ownership.py'}
MOCK_MARKERS = ('mock_job', 'launcher.py', 'fault_entry.py', 'smi.py', 'test_gpu_worker_v4', 'run_v4_controls')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def utc(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def processes():
    out = subprocess.run(['ps', '-axo', 'pid=,ppid=,uid=,command='], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        f = line.split(None, 3)
        if len(f) == 4: rows.append(dict(pid=int(f[0]), ppid=int(f[1]), uid=int(f[2]), cmd=f[3]))
    return rows


def ancestors(rows):
    by = {r['pid']: r for r in rows}; chain, p = set(), os.getpid()
    while p in by and p not in chain:
        chain.add(p); p = by[p]['ppid']
    return chain


def main():
    base = Path(sys.argv[1]).resolve()
    arg = lambda k: sys.argv[sys.argv.index(k) + 1]
    session, exp_worker, exp_harness = arg('--session-id'), arg('--expect-worker'), arg('--expect-harness')
    base.mkdir(parents=True, exist_ok=True)
    ns = base / f"attempt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4()}"
    ns.mkdir()
    rec = dict(schema='gpu-worker-v4-controls-r2/1', namespace=ns.name, start_utc=utc(), session_id=session,
               runner_pid=os.getpid(), uid=os.getuid(), ncpu=os.cpu_count(), load_avg=os.getloadavg(),
               numeric_threads=1, inputs={k: dict(path=str(p), sha256=sha(p)) for k, p in INPUTS.items()})
    lease = open(base / '.lease', 'a')
    def refuse(reason, **d):
        rec.update(status='REFUSED_UNRUN', reason=reason, end_utc=utc(), **d)
        (ns / 'ATTEMPT.json').write_text(json.dumps(rec, indent=1) + '\n')
        print(ns.name, 'REFUSED_UNRUN', reason); sys.exit(75)
    try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: refuse('attempts-dir lease held by another runner')
    rows = processes(); mine = ancestors(rows)
    others = [r for r in rows if r['pid'] not in mine and (session in r['cmd'] or any(m in r['cmd'] for m in MOCK_MARKERS))
              and 'ps -axo' not in r['cmd']]
    rec['admission'] = dict(ancestor_pids=sorted(mine), other_author_or_control_processes=others)
    if others: refuse('another author-session or v4 control process is live')
    l1, l5, _ = os.getloadavg()
    if l1 > os.cpu_count() or l5 > os.cpu_count(): refuse(f'load average {l1:.2f}/{l5:.2f} exceeds {os.cpu_count()} logical CPUs')
    if rec['inputs']['worker']['sha256'] != exp_worker or rec['inputs']['harness']['sha256'] != exp_harness:
        refuse('input hash differs from expected', expected=dict(worker=exp_worker, harness=exp_harness))
    frozen = ns / 'frozen'; frozen.mkdir()
    for k, p in INPUTS.items():
        shutil.copy2(p, frozen / p.name); assert sha(frozen / p.name) == rec['inputs'][k]['sha256']
    # The frozen harness locates process_ownership.py by walking up from its own directory.
    (frozen / 'tools/multi_gpu').mkdir(parents=True)
    shutil.copy2(INPUTS['process_ownership'], frozen / 'tools/multi_gpu/process_ownership.py')
    cmd = [sys.executable, '-B', str(frozen / 'test_gpu_worker_v4.py'), '--json', str(ns / 'controls.json'),
           '--worker', str(frozen / 'gpu_worker_v4.py')]
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    with open(ns / 'stdout.log', 'w') as so:
        p = subprocess.Popen(cmd, stdout=so, stderr=subprocess.STDOUT, start_new_session=True, env=env, cwd=str(ns))
        t = ProcessTable(); birth = t.read(p.pid)
        rec['launch'] = dict(pid=p.pid, start=birth['start'], pgid=birth['pgid'], sid=os.getsid(p.pid), argv=cmd, utc=utc())
        try: code = p.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            rec['fallback'] = []
            for s, wait in ((signal.SIGTERM, 120), (signal.SIGKILL, 10)):
                cur = t.read(p.pid)
                if cur and json.dumps(cur['start']) == json.dumps(birth['start']) and os.getsid(p.pid) == p.pid:
                    os.kill(p.pid, 0); os.kill(p.pid, s); rec['fallback'].append([int(s), utc()])
                try: code = p.wait(timeout=wait); break
                except subprocess.TimeoutExpired: code = None
    after = {k: sha(p) for k, p in INPUTS.items()}
    rec.update(status='RAN', exit=code, end_utc=utc(), load_avg_end=os.getloadavg(),
               inputs_changed_during_attempt=[k for k in INPUTS if after[k] != rec['inputs'][k]['sha256']],
               leftover_mock_processes=[r for r in processes() if any(m in r['cmd'] for m in MOCK_MARKERS[:4])])
    (ns / 'ATTEMPT.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(ns.name, 'exit', code)
    sys.exit(0 if code == 0 else 1)


if __name__ == '__main__':
    main()
