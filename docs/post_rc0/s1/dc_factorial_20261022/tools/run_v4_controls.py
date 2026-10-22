#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run one retained attempt of test_gpu_worker_v4.py (real worker or one committed mutant).

usage: run_v4_controls.py ATTEMPTS_DIR LABEL [--mutant NAME | --worker-file PATH]
Creates ATTEMPTS_DIR/attempt-NN-LABEL (never reused) with the exact worker/test
sources, host occupancy, launch identity, stdout, JSON receipt and exit. The
test runs in its own session; on the 1200 s bound it gets an identity-checked
SIGTERM (its controls then reap their own processes), and SIGKILL only if it
remains, again after a PID/birth/session check. No name-based signals.
"""
import hashlib, json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = next(p for p in [TOOLS, *TOOLS.parents] if (p / 'tools/multi_gpu/process_ownership.py').exists())
sys.path.insert(0, str(REPO / 'tools/multi_gpu'))
from process_ownership import ProcessTable  # noqa: E402


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def utc(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def main():
    base, label = Path(sys.argv[1]), sys.argv[2]
    mutant = sys.argv[sys.argv.index('--mutant') + 1] if '--mutant' in sys.argv else None
    base.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.name.split('-')[1]) for p in base.glob('attempt-*')] or [0])
    out = base / f'attempt-{n:02d}-{label}'; out.mkdir()
    worker = TOOLS / 'gpu_worker_v4.py'
    if '--worker-file' in sys.argv:  # an unmodified committed worker, e.g. the frozen v3, under this harness
        worker = Path(sys.argv[sys.argv.index('--worker-file') + 1]).resolve()
    if mutant:
        spec = json.loads((TOOLS / 'v4_mutants.json').read_text())[mutant]
        src = worker.read_text()
        for a, b in spec['replace']:
            if src.count(a) != 1: raise SystemExit(f'mutant {mutant}: target not unique')
            src = src.replace(a, b)
        worker = TOOLS / f'_v4mutant_{mutant}.py'; worker.write_text(src)
    shutil.copy(worker, out / 'worker_under_test.py'); shutil.copy(TOOLS / 'test_gpu_worker_v4.py', out / 'test.py')
    rec = dict(label=label, mutant=mutant, runner_sha256=sha(__file__), worker_path=str(worker), start_utc=utc(), worker_sha256=sha(worker), test_sha256=sha(TOOLS / 'test_gpu_worker_v4.py'),
               load_avg=os.getloadavg(), ncpu=os.cpu_count(), python=sys.executable)
    cmd = [sys.executable, '-B', str(TOOLS / 'test_gpu_worker_v4.py'), '--json', str(out / 'controls.json'), '--worker', str(worker)]
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    with open(out / 'stdout.log', 'w') as so:
        p = subprocess.Popen(cmd, stdout=so, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        t = ProcessTable(); birth = t.read(p.pid); rec['launch'] = dict(pid=p.pid, start=birth['start'], pgid=birth['pgid'], argv=cmd)
        try: code = p.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            rec['fallback'] = []
            for sig, wait in ((signal.SIGTERM, 120), (signal.SIGKILL, 10)):
                cur = t.read(p.pid)
                if cur and json.dumps(cur['start']) == json.dumps(birth['start']) and os.getsid(p.pid) == p.pid:
                    os.kill(p.pid, sig); rec['fallback'].append([int(sig), utc()])
                try: code = p.wait(timeout=wait); break
                except subprocess.TimeoutExpired: code = None
    if mutant: worker.unlink()
    rec.update(exit=code, end_utc=utc())
    (out / 'ATTEMPT.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(out.name, 'exit', code)


if __name__ == '__main__':
    main()
