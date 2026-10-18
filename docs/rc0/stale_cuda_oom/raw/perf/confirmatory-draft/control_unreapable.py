#!/usr/bin/env python3
"""Integrated control (review of 202fd5bf, 14:33Z): an unreapable payload must not keep the locks.

Runs the real `confirm_pairs.py run` of a given driver directory in a child process in which only the
payload (argv[0] == 'taskset') is replaced by a process that SIGKILL can never reap: wait() without a
timeout blocks forever, poll() is None, killpg finds no such group. Everything else (lock acquisition,
watchdog, supervisor, run_window's finally, release) is the driver's own code. From outside, the
window's private lock must be released within the window budget, and the window must end INCOMPLETE
with the payload recorded as unreaped.

usage: control_unreapable.py --driver-dir DIR --work DIR --payload-cpus L --runner-cpus L [--budget S]
"""
import argparse, hashlib, json, os, signal, stat, subprocess, sys, threading, time
from pathlib import Path


def wrapped():
    """Child mode: patch Popen for the payload only, then run the driver's main()."""
    ddir = sys.argv[2]
    sys.argv = ['confirm_pairs.py'] + sys.argv[3:]
    sys.dont_write_bytecode = True
    sys.path.insert(0, ddir)
    real = subprocess.Popen

    class Unreapable:
        def __init__(self, cmd, **kw):
            self.args, self.pid, self.returncode = cmd, 4_000_000 + os.getpid() % 100_000, None
            self._never = threading.Event()

        def poll(self):
            return None

        def wait(self, timeout=None):
            if timeout is None:
                self._never.wait()                       # blocks forever: SIGKILL never reaps it
            time.sleep(timeout)
            raise subprocess.TimeoutExpired(self.args, timeout)

    def popen(cmd, *a, **kw):
        if isinstance(cmd, list) and cmd and cmd[0] == 'taskset':
            return Unreapable(cmd, **kw)
        return real(cmd, *a, **kw)
    subprocess.Popen = popen
    import confirm_pairs as cp
    sys.exit(cp.main())


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def integrated(driver_dir, work, payload_cpus, runner_cpus, budget=20, grace_after=15):
    driver_dir, work = Path(driver_dir).resolve(), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    bins = {}
    for arm in ('main', 'fix'):
        b = work / arm
        b.write_text('#!/bin/sh\nexit 0\n'); b.chmod(b.stat().st_mode | stat.S_IXUSR)
        bins[arm] = {'path': str(b), 'sha256': sha256(b)}
    data = work / 'data'; data.mkdir(exist_ok=True)
    (data / 'movies.star').write_text('data_movies\nloop_\n_rlnMicrographMovieName #1\nMovies/m1.tiff\n')
    lock = work / 'window.lock'
    frozen = ('confirm_pairs.py', 'rule.txt', 'vendor/stats.py', 'vendor/identity.py')
    m = {'status': 'CONTROL', 'venue': 'control', 'gpu_uuid': None, 'locks': [str(lock)],
         'payload_cpus': payload_cpus, 'runner_cpus': runner_cpus,
         'frozen_files': {f: sha256(driver_dir / f) for f in frozen}, 'binaries': bins,
         'budget_s': budget, 'payload_timeout_s': 3, 'max_attempts': 3,
         'workloads': {'w': {'n': 16, 'windows': 2, 'movies': ['Movies/m1.tiff'], 'args': [], 'data': str(data),
                             'expected_pdf_pages': 4, 'inputs': {}, 'plan': ['main,fix,AB', 'fix,main,BA']}}}
    mp = work / 'manifest.json'
    mp.write_text(json.dumps(m))
    out = work / 'out'
    cmd = [sys.executable, '-B', __file__, '--wrapped', str(driver_dir), 'run', '--manifest', str(mp),
           '--workload', 'w', '--window', '1', '--out', str(out), '--scratch', str(work / 'scratch'),
           '--dry-run-inputs']
    held = lambda: subprocess.run(['flock', '-n', str(lock), 'true']).returncode != 0
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    acquired = released = None
    while time.monotonic() - t0 < budget + grace_after:
        if acquired is None and held():
            acquired = time.monotonic() - t0
        if acquired is not None and not held():
            released = time.monotonic() - t0
            break
        time.sleep(0.1)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    alive = proc.poll() is None
    if alive:
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
    wd = out / 'w' / 'window1'
    inc = wd / 'incomplete.json'
    mk = json.loads(inc.read_text()) if inc.is_file() else {}
    recs = [json.loads(l) for l in (wd / 'runs.jsonl').read_text().splitlines()] if (wd / 'runs.jsonl').is_file() else []
    unreaped_rec = [r for r in recs if r.get('failure') == 'unreaped']
    ok = (acquired is not None and released is not None and released <= budget + 1.0 and inc.is_file()
          and 0 <= mk.get('released_after_s', 1e9) <= budget and mk.get('remaining_budget_s', -1) > 0
          and not (wd / 'complete.json').exists() and bool(mk.get('unreaped_pids')) and bool(unreaped_rec))
    detail = {'lock_acquired_s': acquired, 'lock_released_s': released, 'budget_s': budget,
              'driver_still_running_after': alive, 'marker': mk, 'unreaped_records': unreaped_rec}
    return ok, detail


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--wrapped':
        return wrapped()
    ap = argparse.ArgumentParser()
    for k in ('driver-dir', 'work', 'payload-cpus', 'runner-cpus'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--budget', type=int, default=20)
    o = ap.parse_args()
    ok, detail = integrated(o.driver_dir, o.work, o.payload_cpus, o.runner_cpus, o.budget)
    print(('PASS' if ok else 'FAIL'), json.dumps(detail, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
