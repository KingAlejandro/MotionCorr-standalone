#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""#262 GPU worker v2: per-launch admission and owned-session cleanup (PROPOSED, not deployed).

Successor to `campaign.py worker ... cuda`, which checked GPU occupancy only once
at worker start. campaign.py is unchanged; this tool imports its input admission
and hashing helpers. Differences:

- Before EVERY launch: target UUID at the expected index, volatile uncorrected
  ECC 0, and no compute process on the target UUID. Any failure, including an
  unreadable query, stops before launch (exit 75) with a STOP receipt.
- During a job a sampler records every compute process on the target UUID that
  is not an owned descendant. After the job the same checks run again. A foreign
  process or ECC change is recorded in that job's RUN.json `resource` block and
  the worker stops before the next launch. The finished job is not cancelled.
- Each job runs in its own session (start_new_session). Ownership uses
  tools/multi_gpu/process_ownership.py PID/birth identities (Linux
  child-subreaper adoption). Timeout or SIGTERM/SIGINT signals only process
  groups re-verified as owned immediately before each TERM/KILL, never the
  worker's own group and never by name. The job record is written with status
  TIMEOUT or CANCELLED; it is never a success.
- The GPU lease (flock, nonblocking) is released only after owned processes are
  gone and ownership is restored. If that cannot be verified the worker writes
  CLEANUP_FAILED_LEASE_HELD and keeps the lease until an operator stops it.
- Output goes to a fresh --runs-dir. An existing job directory is never touched;
  it is reported as PRESERVED_EXISTING and skipped.

Exit: 0 queue done; 75 admission/resource stop; 3 scratch cap; 4 cancelled;
5 cleanup failure (only after an operator stops the held worker).
"""
import argparse, fcntl, json, os, shlex, signal, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import campaign  # noqa: E402  (admit, sha256, utc, usage helpers; unchanged)

GRACE_S = 10.0
SAMPLE_S = 0.25


def find_ownership():
    for base in [HERE, *HERE.parents]:
        p = base / 'tools' / 'multi_gpu' / 'process_ownership.py'
        if p.exists():
            sys.path.insert(0, str(p.parent))
            from process_ownership import ProcessOwnership
            return ProcessOwnership, str(p)
    raise RuntimeError('tools/multi_gpu/process_ownership.py not found above ' + str(HERE))


ProcessOwnership, OWNERSHIP_PATH = find_ownership()


class Smi:
    def __init__(self, cmd, uuid, index):
        self.cmd, self.uuid, self.index = shlex.split(cmd), uuid, str(index)

    def query(self):
        """Return (state, problems). Problems is non-empty if a launch must not proceed."""
        g = subprocess.run(self.cmd + ['--query-gpu=index,uuid,memory.used,utilization.gpu,ecc.errors.uncorrected.volatile.total',
                                       '--format=csv,noheader'], capture_output=True, text=True, timeout=30)
        a = subprocess.run(self.cmd + ['--query-compute-apps=gpu_uuid,pid,used_memory', '--format=csv,noheader'],
                           capture_output=True, text=True, timeout=30)
        state = dict(utc=campaign.utc(), gpus=g.stdout, apps=a.stdout, exits=[g.returncode, a.returncode])
        problems = []
        if g.returncode or a.returncode: problems.append('nvidia-smi query failed')
        row = [l for l in g.stdout.splitlines() if self.uuid in l]
        if len(row) != 1 or row[0].split(',')[0].strip() != self.index:
            problems.append(f'UUID/index mapping not {self.index}: {row}')
        elif row[0].split(',')[-1].strip() not in ('0', '[N/A]'):
            problems.append('volatile uncorrected ECC nonzero: ' + row[0])
        state['target_pids'] = [int(l.split(',')[1]) for l in a.stdout.splitlines() if l.startswith(self.uuid)]
        return state, problems


def tree_bytes(path):
    """campaign.usage_bytes counts ROOT/runs only; the fresh namespace is added here."""
    total = 0
    for d, _, files in os.walk(path):
        for f in files:
            try: total += os.lstat(os.path.join(d, f)).st_size
            except OSError: pass
    return total


def owned_pids(own):
    """Every PID whose birth identity the helper recorded as ours, live or exited-unreaped."""
    with own._lock:
        return set(own.identities)


def terminate_owned(own, roots, errors):
    """Checked TERM then KILL of owned groups (pattern of run_multi_gpu._terminate_process_groups)."""
    own.refresh()
    groups = {p.pid for p in roots} | {r['pgid'] for r in own.known_live()}
    groups.discard(os.getpgrp())
    signalled = []
    for signum in (signal.SIGTERM, signal.SIGKILL):
        own.refresh()
        groups |= {r['pgid'] for r in own.known_live()} - {os.getpgrp()}
        for g in sorted(groups):
            if not own.table.group_live(g): continue
            if own.errors or not own.verified_group(g):
                errors.append(f'refused signal {signum} to unverified group {g}'); continue
            try: os.killpg(g, signum); signalled.append([int(signum), g, campaign.utc()])
            except ProcessLookupError: pass
        deadline = time.monotonic() + (GRACE_S if signum == signal.SIGTERM else 5.0)
        while time.monotonic() < deadline and own.known_live():
            for p in roots: p.poll()
            time.sleep(0.05)
        if not own.known_live(): break
    for p in roots:
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: errors.append(f'could not reap {p.pid}')
    return signalled


class Worker:
    def __init__(self, a):
        self.a = a
        self.root = Path(a.root).resolve()
        self.runs = Path(a.runs_dir).resolve()
        self.smi = Smi(a.smi, a.uuid, a.gpu_index)
        self.cancel = threading.Event()
        self.log = None

    def note(self, *x):
        print(campaign.utc(), *x, file=self.log, flush=True)

    def receipt(self, name, obj):
        p = self.runs / f'{name}-{int(time.time() * 1000)}.json'
        p.write_text(json.dumps(obj, indent=1) + '\n')
        return p

    def run_job(self, j, binaries, own):
        out = self.runs / j['id']
        out.mkdir()  # caller has proved absence; never reuse
        binary = binaries[j['build']]
        inputs = {p: campaign.admit(self.root, p, s) for p, s in j['inputs'].items()}
        args = [x.replace('{OUT}', str(out)) for x in j['args']]
        env = {k: v for k, v in os.environ.items() if not k.startswith(('MC_EXPERIMENT_', 'MC_DIAG_', 'OMP_', 'CUDA_'))}
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LD_LIBRARY_PATH=campaign.LD)
        extra = {}
        if j['arm'] != 'plain': extra['MC_EXPERIMENT_CCF_DC_ARM'] = j['arm']
        if j.get('model'): extra['MC_DIAG_MODEL_OUT'] = str(out / 'runtime.json')
        extra.update(CUDA_VISIBLE_DEVICES=self.a.uuid, CUDA_DEVICE_ORDER='PCI_BUS_ID')
        if '--gpu' not in args: args += ['--gpu', '0']
        env.update(extra)
        prefix = shlex.split(self.a.prefix.format(cpu=self.a.cpu, out=out))
        cmd = prefix + [binary['path']] + args
        before, problems = self.smi.query()
        rec = dict(id=j['id'], tier=j['tier'], backend=j['backend'], arm=j['arm'], build=j['build'], group=j['group'],
                   worker='gpu_worker_v2', worker_sha256=campaign.sha256(__file__),
                   ownership_helper=OWNERSHIP_PATH, ownership_sha256=campaign.sha256(OWNERSHIP_PATH),
                   source_sha=(self.root / 'SOURCE_SHA').read_text().strip(), binary=binary['path'],
                   binary_sha256=binary['sha256'], argv=cmd, cwd=j['cwd'], env=extra, cpu=str(self.a.cpu),
                   inputs=inputs, start_utc=campaign.utc(), gpu_before=before, ownership_mode=own.mode)
        if problems or before['target_pids']:
            # Re-checked immediately before launch: refuse, keep the empty dir as evidence.
            rec.update(status='NOT_LAUNCHED', reason=problems or ['foreign process on target UUID'])
            (out / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
            return rec, True
        foreign, stop = {}, threading.Event()
        with open(out / 'stdout.log', 'w') as so, open(out / 'stderr.log', 'w') as se:
            p = subprocess.Popen(cmd, cwd=j['cwd'], env=env, stdout=so, stderr=se, start_new_session=True)
            own.watch(p.pid)
            def sampler():
                while not stop.is_set():
                    try:
                        st, _ = self.smi.query()
                        mine = owned_pids(own)
                        for pid in st['target_pids']:
                            if pid not in mine: foreign.setdefault(pid, st['utc'])
                    except Exception as e:
                        foreign.setdefault('sampler_error', str(e))
                    stop.wait(SAMPLE_S)
            th = threading.Thread(target=sampler, daemon=True); th.start()
            t0, status, errors, signalled = time.time(), 'EXITED', [], []
            while p.poll() is None:
                if self.cancel.is_set(): status = 'CANCELLED'
                elif time.time() - t0 > self.a.job_timeout: status = 'TIMEOUT'
                if status != 'EXITED':
                    signalled = terminate_owned(own, [p], errors); break
                time.sleep(0.1)
            p.wait()
            # Descendants that outlive the root (same or new session) are owned work too.
            own.refresh()
            if own.known_live():
                if status == 'EXITED': status = 'EXITED_WITH_OWNED_SURVIVORS'
                signalled += terminate_owned(own, [p], errors)
            stop.set(); th.join(15)
        after, problems_after = self.smi.query()
        rec.update(status=status, exit=p.returncode, wall_s_unqualified=round(time.time() - t0, 2), end_utc=campaign.utc(),
                   gpu_after=after, cleanup=dict(signals=signalled, errors=errors, owned_live_after=own.known_live()),
                   resource=dict(foreign_on_target_during=foreign, foreign_on_target_after=after['target_pids'],
                                 problems_after=problems_after))
        w = [l.strip() for l in open(out / 'stderr.log', errors='replace') if l.startswith('MC_EXPERIMENT_CCF_DC arm=') and '/' in l]
        rec['dc_witness'] = w[-1] if w else None
        rec['outputs'] = {str(f.relative_to(out)): dict(bytes=f.stat().st_size, sha256=campaign.sha256(f))
                          for f in out.rglob('*') if f.is_file() and f.name != 'RUN.json'}
        (out / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
        halt = bool(foreign or after['target_pids'] or problems_after or errors or status != 'EXITED')
        return rec, halt

    def main(self):
        a = self.a
        self.runs.mkdir(parents=True, exist_ok=True)
        self.log = open(self.runs / f'worker-v2-{a.cpu}.log', 'a')
        q = json.loads(Path(a.queue).read_text())
        binaries = json.loads(Path(a.binaries).read_text())
        for b in binaries.values():
            if campaign.sha256(b['path']) != b['sha256']: raise RuntimeError('binary hash changed: ' + b['path'])
        lease = open(a.lock, 'a')
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.receipt('STOP', dict(reason='GPU lease busy', utc=campaign.utc())); return 75
        for s in (signal.SIGTERM, signal.SIGINT): signal.signal(s, lambda *_: self.cancel.set())
        own = ProcessOwnership()
        own.activate(native_required=sys.platform == 'linux')
        own.start()
        code, preserved = 0, []
        try:
            for j in q:
                if self.cancel.is_set(): code = 4; break
                out = self.runs / j['id']
                if out.exists():
                    preserved.append(j['id']); self.note(j['id'], 'PRESERVED_EXISTING'); continue
                if campaign.usage_bytes(self.root) + tree_bytes(self.runs) > campaign.CAP:
                    self.receipt('STOP', dict(reason='scratch cap', before=j['id'], utc=campaign.utc())); code = 3; break
                st, problems = self.smi.query()
                if problems or st['target_pids']:
                    self.receipt('STOP', dict(reason=problems or ['foreign process on target UUID before launch'],
                                              before=j['id'], gpu=st)); code = 75; break
                rec, halt = self.run_job(j, binaries, own)
                self.note(j['id'], rec['status'], rec.get('exit'), rec.get('dc_witness'))
                if rec['status'] in ('CANCELLED',): code = 4; break
                if halt:
                    self.receipt('STOP', dict(reason='post-job resource/ownership check failed', after=j['id'],
                                              status=rec['status'], resource=rec.get('resource'), cleanup=rec.get('cleanup')))
                    code = 75; break
        finally:
            own.stop(); own.join(5)
            try:
                errors = []
                if own.known_live(): terminate_owned(own, [], errors)
                if errors or own.known_live(): raise RuntimeError(f'owned processes remain: {own.known_live()} {errors}')
                own.restore()
                self.receipt('FINAL', dict(code=code, preserved_existing=preserved, gpu=self.smi.query()[0]))
                fcntl.flock(lease, fcntl.LOCK_UN); lease.close()
            except Exception as e:
                self.receipt('CLEANUP_FAILED_LEASE_HELD', dict(error=str(e), utc=campaign.utc()))
                self.note('CLEANUP_FAILED_LEASE_HELD', e)
                while True: signal.pause()  # keep the lease; an operator must inspect and stop this worker
        return code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', required=True); ap.add_argument('--queue', required=True)
    ap.add_argument('--runs-dir', required=True); ap.add_argument('--binaries', required=True)
    ap.add_argument('--cpu', type=int, required=True); ap.add_argument('--uuid', required=True)
    ap.add_argument('--gpu-index', type=int, required=True); ap.add_argument('--lock', required=True)
    ap.add_argument('--job-timeout', type=float, default=3600)
    ap.add_argument('--smi', default='nvidia-smi')
    ap.add_argument('--prefix', default='taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log')
    sys.exit(Worker(ap.parse_args()).main())


if __name__ == '__main__':
    main()
