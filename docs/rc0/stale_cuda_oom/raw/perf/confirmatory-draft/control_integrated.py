#!/usr/bin/env python3
"""Integrated controls: no blocking call in a window's work can keep the window's lock past its budget.

Runs the real `confirm_pairs.py run` of a given driver directory with ONE fault injected, in whichever
process does the work: the single process of an old driver, or, for a driver with a lock-holder, the
worker it starts (the patch is carried into the worker by rewriting the holder's worker command).
From outside, the window's private lock is watched.

  unreapable   the payload (argv[0] == 'taskset') becomes a process SIGKILL can never reap
  fsync:N      the N-th os.fsync blocks forever (review of 5b430d4b: the 3rd, in emit())
  open-log     the first open() of a per-run log under /logs/ for writing blocks forever
  inherit      as fsync:3, plus: the worker holds no fd on the lock file, and killing only the
               holder frees the lock at once while the worker is still alive

usage: control_integrated.py --driver-dir DIR --work DIR --mode MODE --payload-cpus L --runner-cpus L [--budget S]
"""
import argparse, builtins, hashlib, json, os, signal, stat, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve()


def wrapped():
    """Child mode: inject the fault in this process, carry it into any worker, run the driver."""
    ddir, mode = sys.argv[2], sys.argv[3]
    sys.argv = ['confirm_pairs.py'] + sys.argv[4:]
    sys.dont_write_bytecode = True
    sys.path.insert(0, ddir)
    real_popen, never = subprocess.Popen, threading.Event()

    class Unreapable:
        def __init__(self, cmd, **kw):
            self.args, self.pid, self.returncode = cmd, 4_000_000 + os.getpid() % 100_000, None

        def poll(self):
            return None

        def wait(self, timeout=None):
            if timeout is None:
                never.wait()
            time.sleep(timeout)
            raise subprocess.TimeoutExpired(self.args, timeout)

    def popen(cmd, *a, **kw):
        if isinstance(cmd, list) and 'worker' in cmd and any(str(x).endswith('confirm_pairs.py') for x in cmd):
            i = next(k for k, x in enumerate(cmd) if str(x).endswith('confirm_pairs.py'))
            cmd = [cmd[0], '-B', str(HERE), '--wrapped', ddir, mode] + cmd[i + 1:]
        elif mode == 'unreapable' and isinstance(cmd, list) and cmd and cmd[0] == 'taskset':
            return Unreapable(cmd, **kw)
        return real_popen(cmd, *a, **kw)
    subprocess.Popen = popen
    if mode.startswith('fsync:') or mode == 'inherit':
        n, count, real_fsync = int(mode.split(':')[1]) if ':' in mode else 3, [0], os.fsync

        def fsync(fd):
            count[0] += 1
            if count[0] == n:
                never.wait()
            return real_fsync(fd)
        os.fsync = fsync
    if mode == 'open-log':
        real_open, hit = builtins.open, [False]

        def stalled_open(file, mode_='r', *a, **kw):
            if not hit[0] and '/logs/' in str(file) and 'w' in mode_:
                hit[0] = True
                never.wait()
            return real_open(file, mode_, *a, **kw)
        builtins.open = stalled_open
    import confirm_pairs as cp
    sys.exit(cp.main())


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def proc_fds_target(pid, path):
    try:
        return [os.readlink(f'/proc/{pid}/fd/{fd}') for fd in os.listdir(f'/proc/{pid}/fd')
                if os.readlink(f'/proc/{pid}/fd/{fd}') == str(path)]
    except OSError:
        return []


def integrated(driver_dir, work, mode, payload_cpus, runner_cpus, budget=20, grace_after=15):
    driver_dir, work = Path(driver_dir).resolve(), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    bins = {}
    for arm in ('main', 'fix'):
        b = work / arm
        b.write_text('#!/bin/sh\nsleep 0.3\nexit 0\n'); b.chmod(b.stat().st_mode | stat.S_IXUSR)
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
    cmd = [sys.executable, '-B', str(HERE), '--wrapped', str(driver_dir), mode, 'run', '--manifest', str(mp),
           '--workload', 'w', '--window', '1', '--out', str(out), '--scratch', str(work / 'scratch'),
           '--dry-run-inputs']
    held = lambda: subprocess.run(['flock', '-n', str(lock), 'true']).returncode != 0
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    acquired = released = None
    inherit = {}
    while time.monotonic() - t0 < budget + grace_after:
        if acquired is None and held():
            acquired = time.monotonic() - t0
            if mode == 'inherit':
                time.sleep(2)                             # the worker is now stalled in its 3rd fsync
                workers = [int(x) for x in subprocess.run(['pgrep', '-f', f'worker --manifest {mp}'],
                                                          capture_output=True, text=True).stdout.split()]
                inherit['workers'] = workers
                inherit['worker_lock_fds'] = {w: proc_fds_target(w, lock) for w in workers}
                os.kill(proc.pid, signal.SIGKILL)         # the holder only
                t_kill = time.monotonic()
                while held() and time.monotonic() - t_kill < 5:
                    time.sleep(0.02)
                inherit['lock_free_after_holder_kill_s'] = None if held() else round(time.monotonic() - t_kill, 3)
                inherit['worker_alive_after'] = any(Path(f'/proc/{w}').exists() for w in workers)
                for w in workers:
                    try:
                        os.killpg(w, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                break
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
    leftover = [x for x in subprocess.run(['pgrep', '-f', str(work)], capture_output=True, text=True).stdout.split()
                if int(x) not in (os.getpid(), os.getppid())]          # never this control itself
    for pid in leftover:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    wd = out / 'w' / 'window1'
    hr = json.loads((wd / 'holder.json').read_text()) if (wd / 'holder.json').is_file() else {}
    mk = json.loads((wd / 'incomplete.json').read_text()) if (wd / 'incomplete.json').is_file() else {}
    no_complete = not (wd / 'complete.json').exists()
    if mode == 'inherit':
        ok = (acquired is not None and inherit.get('workers') and not any(inherit['worker_lock_fds'].values())
              and inherit.get('lock_free_after_holder_kill_s') is not None
              and inherit['lock_free_after_holder_kill_s'] < 1.0 and inherit.get('worker_alive_after') and no_complete)
    else:
        in_budget = acquired is not None and released is not None and released <= budget + 1.0 and no_complete
        if mode == 'unreapable':
            ok = in_budget and bool(mk.get('unreaped_pids')) and hr.get('worker_rc') not in (0, None)
        else:
            ok = in_budget and hr.get('worker_killed_at_deadline') is True and \
                0 <= hr.get('locks_released_after_s', 1e9) <= budget
    detail = {'mode': mode, 'lock_acquired_s': acquired, 'lock_released_s': released, 'budget_s': budget,
              'driver_still_running_after': alive, 'holder_record': hr, 'worker_marker_status': mk.get('status'),
              'unreaped_pids': mk.get('unreaped_pids'), 'inherit': inherit, 'leftover_pids_killed': leftover}
    return bool(ok), detail


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--wrapped':
        return wrapped()
    ap = argparse.ArgumentParser()
    for k in ('driver-dir', 'work', 'mode', 'payload-cpus', 'runner-cpus'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--budget', type=int, default=20)
    o = ap.parse_args()
    ok, detail = integrated(o.driver_dir, o.work, o.mode, o.payload_cpus, o.runner_cpus, o.budget)
    print(('PASS' if ok else 'FAIL'), json.dumps(detail, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
