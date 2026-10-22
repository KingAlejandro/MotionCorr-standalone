#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""#262 GPU worker v4 (PROPOSED, not deployed). Supersedes v3 after review R2 (v3 and v2 stay frozen).

Changes from v3 (review R2): every nvidia-smi query runs in the worker's own
process group, so the ownership helper (which, on Linux, adopts direct children
outside the worker's group) can never own it; the sampler is stopped and joined
before the job's cleanup classification; any query identity seen among owned
processes is an ownership inconsistency and fails closed. An observer/restore
failure releases the lease only when no job was launched by this worker, no
owned identity was ever recorded and every query process is reaped; otherwise
the lease is held as before. A job is OK only with at least one successful
sample and the route witness equal to the target UUID. Errors before the lease
print a typed receipt to stdout (exit 74).

Binding (checked before the lease or any output is created; exit 64 on failure):
the queue file's SHA-256 and entry count must equal --queue-sha256 and
--expected-jobs; ids are unique; every entry is backend cuda with build
cuda-exp; binaries.json SHA-256 equals --binaries-sha256 and every binary
matches its recorded hash; --runs-dir is absent or empty; the lease file is
derived from the GPU index (<lock-dir>/motioncorr-gpu<index>-correctness.lock).

Admission before EVERY launch: the target UUID is at --gpu-index, volatile
uncorrected ECC is exactly 0 ("[N/A]" or unreadable fails closed), no compute
process is on the target UUID, the ownership observer is alive with no errors,
and no cancellation is pending. Queries run as direct children in the worker's
own process group with a bounded wait; a timeout SIGKILLs the still-unreaped
query by its Popen handle (PID-safe until reaped). A query process that cannot
be reaped (e.g. uninterruptible sleep) is reported QUERY_HUNG; the worker cannot
force it and stops. A grandchild that a query might leave behind would stay in
the worker's group and is not cleaned up by the worker (real nvidia-smi does
not fork such helpers; not tested).

During a job a sampler counts successful and failed queries, records the target
UUID for every owned process it sees (gpu_witness_uuids) and records any process
on the target that is not a live, birth-matched owned descendant. A failed
sample, a foreign process, a timeout, owned survivors or a failed post-job
query stops the worker before the next launch.

Cleanup signals only process groups re-verified as owned by
tools/multi_gpu/process_ownership.py immediately before each TERM/KILL, never the
worker's own group. All waits are bounded. If owned processes cannot be shown to
be gone, the job's RUN.json gets status CLEANUP_FAILED, a
CLEANUP_FAILED_LEASE_HELD receipt is written, and only then does the worker hold
the lease indefinitely; an operator inspects it and stops it with SIGKILL.

Every exit path after the lease writes a typed receipt; errors before the lease
(runs-dir creation, log or lease open) print a typed JSON receipt to stdout only.
FINAL carries an exact census of all expected queue ids. "Complete" means every
id reached a RUN.json with status EXITED, whatever the native exit code; FINAL
also reports how many of those exited nonzero. Exit 0 requires completeness;
nonzero native exits are retained as data, not as worker failures.

Exit codes: 0 complete census; 3 scratch cap; 4 cancelled; 64 invalid binding;
65 input admission failed; 74 error before the lease; 70 job/worker stage error or directory collision;
75 resource/admission/query/observer stop; 76 final health failed after clean
completion; 77 census incomplete; 78 job timeout. CLEANUP_FAILED never exits.

Namespace-aware evaluation and matrix generation are NOT implemented: evaluate.py
and matrix.py read ROOT/runs only, so a v3 namespace must not be evaluated until
a reviewed reader exists.
"""
import argparse, fcntl, hashlib, json, os, shlex, signal, socket, subprocess, sys, threading, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import campaign  # noqa: E402  (admit, sha256, utc, usage_bytes, bench_status, LD, CAP; unchanged)

SAMPLE_S = 0.25
EXIT = dict(OK=0, CAP=3, CANCELLED=4, INVALID=64, INPUT_ADMISSION=65, PRELEASE_IO=74, JOB_STAGE=70, RESOURCE=75,
            FINAL_HEALTH=76, INCOMPLETE=77, TIMEOUT=78)


def find_ownership():
    for base in [HERE, *HERE.parents]:
        p = base / 'tools' / 'multi_gpu' / 'process_ownership.py'
        if p.exists():
            sys.path.insert(0, str(p.parent))
            import process_ownership
            return process_ownership, str(p)
    raise RuntimeError('tools/multi_gpu/process_ownership.py not found above ' + str(HERE))


_po, OWNERSHIP_PATH = find_ownership()
ProcessOwnership, ProcessTable = _po.ProcessOwnership, _po.ProcessTable


class QueryError(Exception):
    def __init__(self, kind, detail):
        super().__init__(f'{kind}: {detail}')
        self.kind, self.detail = kind, detail


class Smi:
    def __init__(self, cmd, uuid, index, timeout, table):
        self.cmd, self.uuid, self.index, self.timeout, self.table = shlex.split(cmd), uuid, str(index), timeout, table
        self.lock = threading.Lock()
        self.identities = {}   # every query process this worker started: pid -> birth
        self.unreaped = set()  # query PIDs not yet reaped

    def _run(self, args):
        # Same process group as the worker: the ownership helper never adopts it (R2-M1).
        p = subprocess.Popen(self.cmd + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        birth = self.table.read(p.pid)
        with self.lock:
            self.unreaped.add(p.pid)
            if birth: self.identities[p.pid] = birth['start']
        try:
            try:
                out, err = p.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                p.kill()  # unreaped Popen child: its PID cannot have been reused
                try: p.communicate(timeout=5)
                except subprocess.TimeoutExpired: raise QueryError('QUERY_HUNG', f'query PID {p.pid} not reaped after SIGKILL')
                raise QueryError('QUERY_TIMEOUT', f'{args[0]} exceeded {self.timeout} s')
        finally:
            if p.returncode is not None:
                with self.lock: self.unreaped.discard(p.pid)
        if p.returncode:
            raise QueryError('QUERY_FAILED', f'{args[0]} exit {p.returncode}: {err.strip()[-300:]}')
        return out

    def query(self):
        """State with parsed rows; raises QueryError on any failure or malformed output."""
        g = self._run(['--query-gpu=index,uuid,memory.used,utilization.gpu,ecc.errors.uncorrected.volatile.total',
                       '--format=csv,noheader'])
        a = self._run(['--query-compute-apps=gpu_uuid,pid,used_memory', '--format=csv,noheader'])
        gpus, apps = [], []
        for line in g.splitlines():
            if not line.strip(): continue
            f = [x.strip() for x in line.split(',')]
            if len(f) != 5: raise QueryError('QUERY_MALFORMED', 'gpu row: ' + line)
            gpus.append(f)
        for line in a.splitlines():
            if not line.strip(): continue
            f = [x.strip() for x in line.split(',')]
            if len(f) != 3 or not f[1].isdigit(): raise QueryError('QUERY_MALFORMED', 'compute-app row: ' + line)
            apps.append((f[0], int(f[1])))
        return dict(utc=campaign.utc(), gpus=g, apps=a, gpu_rows=gpus,
                    target_pids=[pid for u, pid in apps if u == self.uuid])

    def admission_problems(self, st):
        rows = [r for r in st['gpu_rows'] if r[1] == self.uuid]
        if len(rows) != 1: return [f'target UUID rows: {len(rows)}']
        problems = []
        if rows[0][0] != self.index: problems.append(f'target UUID at index {rows[0][0]}, expected {self.index}')
        if rows[0][4] != '0': problems.append(f'volatile uncorrected ECC is {rows[0][4]!r}, not 0')
        return problems


def live_owned(own):
    """Live, birth-matched owned identities only (known_live re-reads each PID's birth)."""
    return {r['pid']: r['start'] for r in own.known_live()}


def classify(target_pids, pre, post):
    """Split target PIDs into (owned, foreign) using owned identities live before and after the query."""
    owned = [p for p in target_pids if p in pre or p in post]
    return owned, [p for p in target_pids if p not in pre and p not in post]


def query_identities_owned(own, smi):
    """Query processes must never be owned; any overlap is an ownership inconsistency."""
    with smi.lock: q = dict(smi.identities)
    return [r['pid'] for r in own.known_live() if q.get(r['pid']) == r['start']]


def observer_ok(own):
    return own.is_alive() and not own.errors


def terminate_owned(own, root, grace):
    """Checked TERM then KILL of owned groups; refuses everything if the observer is unhealthy."""
    signalled, errors = [], []
    if own.errors:
        # Descendants cannot be verified, but the unreaped Popen root is PID-safe to signal.
        for signum in (signal.SIGTERM, signal.SIGKILL):
            if root.poll() is None:
                root.send_signal(signum); signalled.append([int(signum), 'root', root.pid, campaign.utc()])
                try: root.wait(timeout=grace)
                except subprocess.TimeoutExpired: pass
        return signalled, ['observer errors: ' + '; '.join(own.errors)]
    try:
        own.refresh()
        groups = {root.pid} | {r['pgid'] for r in own.known_live()}
    except Exception as e:
        return signalled, [f'ownership refresh failed: {e}']
    groups.discard(os.getpgrp())
    for signum in (signal.SIGTERM, signal.SIGKILL):
        try:
            own.refresh()
            groups |= {r['pgid'] for r in own.known_live()} - {os.getpgrp()}
            for g in sorted(groups):
                if not own.table.group_live(g): continue
                if own.errors or not own.verified_group(g):
                    errors.append(f'refused signal {int(signum)} to unverified group {g}'); continue
                try: os.killpg(g, signum); signalled.append([int(signum), g, campaign.utc()])
                except ProcessLookupError: pass
        except Exception as e:
            errors.append(f'ownership check failed during signal {int(signum)}: {e}'); break
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and (root.poll() is None or own.known_live()):
            time.sleep(0.05)
        if root.poll() is not None and not own.known_live(): break
    return signalled, errors


class Worker:
    def __init__(self, a):
        self.a = a
        self.root = Path(a.root).resolve()
        self.runs = Path(a.runs_dir).resolve()
        self.table = ProcessTable()
        self.smi = Smi(a.smi, a.uuid, a.gpu_index, a.query_timeout, self.table)
        self.lock_path = Path(a.lock_dir) / f'motioncorr-gpu{a.gpu_index}-correctness.lock'
        self.cancel = threading.Event()
        self.log = None
        self.binding = None
        self.launched = 0

    # ---- receipts -------------------------------------------------------
    def note(self, *x):
        if self.log: print(campaign.utc(), *x, file=self.log, flush=True)

    def receipt(self, kind, **obj):
        obj.update(kind=kind, utc=campaign.utc(), binding=self.binding)
        p = self.runs / f'{kind}-{time.time_ns()}.json'
        p.write_text(json.dumps(obj, indent=1, default=str) + '\n')
        self.note(kind, obj.get('reason', ''))
        return p

    def hold_lease(self, reason, **detail):
        """Write the receipt first; then keep the lease until an operator SIGKILLs this worker."""
        self.receipt('CLEANUP_FAILED_LEASE_HELD', reason=reason, pid=os.getpid(), lease=str(self.lock_path), **detail)
        for s in (signal.SIGTERM, signal.SIGINT): signal.signal(s, signal.SIG_IGN)
        while True: signal.pause()

    # ---- binding --------------------------------------------------------
    def bind(self):
        a = self.a
        problems = []
        qbytes = Path(a.queue).read_bytes()
        qsha = hashlib.sha256(qbytes).hexdigest()
        q = json.loads(qbytes)
        if qsha != a.queue_sha256: problems.append(f'queue SHA-256 {qsha} != {a.queue_sha256}')
        if len(q) != a.expected_jobs: problems.append(f'queue has {len(q)} entries, expected {a.expected_jobs}')
        ids = [j['id'] for j in q]
        if len(set(ids)) != len(ids): problems.append('duplicate queue ids')
        bad = [j['id'] for j in q if j.get('backend') != 'cuda' or j.get('build') != 'cuda-exp']
        if bad: problems.append(f'{len(bad)} entries are not backend cuda / build cuda-exp, e.g. {bad[:3]}')
        bbytes = Path(a.binaries).read_bytes()
        bsha = hashlib.sha256(bbytes).hexdigest()
        if bsha != a.binaries_sha256: problems.append(f'binaries.json SHA-256 {bsha} != {a.binaries_sha256}')
        binaries = json.loads(bbytes)
        if 'cuda-exp' not in binaries: problems.append('binaries.json has no cuda-exp')
        else:
            got = campaign.sha256(binaries['cuda-exp']['path'])
            if got != binaries['cuda-exp']['sha256']: problems.append(f'cuda-exp binary hash {got} != recorded')
        if self.runs.exists() and any(self.runs.iterdir()): problems.append(f'runs dir {self.runs} is not empty')
        self.binding = dict(queue=str(Path(a.queue).resolve()), queue_sha256=qsha, expected_jobs=a.expected_jobs,
                            binaries=str(Path(a.binaries).resolve()), binaries_sha256=bsha, uuid=a.uuid,
                            gpu_index=a.gpu_index, lease=str(self.lock_path), runs_dir=str(self.runs),
                            worker_sha256=campaign.sha256(__file__), ownership_sha256=campaign.sha256(OWNERSHIP_PATH),
                            source_sha=(self.root / 'SOURCE_SHA').read_text().strip())
        return q, binaries, problems

    def census(self, q):
        rows, counts = {}, {}
        for j in q:
            d = self.runs / j['id']
            if not d.exists(): s = 'ABSENT'
            elif not (d / 'RUN.json').exists(): s = 'NO_RUN_JSON'
            else:
                r = json.loads((d / 'RUN.json').read_text())
                s = r['status'] if r['status'] != 'EXITED' else ('EXITED' if r['exit'] == 0 else 'EXITED_NONZERO')
            rows[j['id']] = s
            counts[s] = counts.get(s, 0) + 1
        complete = all(s in ('EXITED', 'EXITED_NONZERO') for s in rows.values()) and len(rows) == self.a.expected_jobs
        return dict(expected=self.a.expected_jobs, counts=counts, complete=complete,
                    complete_means='every id has RUN.json status EXITED (any native exit code)',
                    exited_nonzero=counts.get('EXITED_NONZERO', 0),
                    not_complete=[i for i, s in rows.items() if s not in ('EXITED', 'EXITED_NONZERO')])

    # ---- one job ----------------------------------------------------------
    def base_record(self, j, binary, out):
        args = [x.replace('{OUT}', str(out)) for x in j['args']]
        if '--gpu' not in args: args += ['--gpu', '0']
        extra = {}
        if j['arm'] != 'plain': extra['MC_EXPERIMENT_CCF_DC_ARM'] = j['arm']
        if j.get('model'): extra['MC_DIAG_MODEL_OUT'] = str(out / 'runtime.json')
        extra.update(CUDA_VISIBLE_DEVICES=self.a.uuid, CUDA_DEVICE_ORDER='PCI_BUS_ID')
        prefix = shlex.split(self.a.prefix.format(cpu=self.a.cpu, out=out))
        rec = dict(schema='dc262-run/v3', id=j['id'], tier=j['tier'], backend=j['backend'], arm=j['arm'], build=j['build'],
                   group=j['group'], source_sha=self.binding['source_sha'], binary=binary['path'],
                   binary_sha256=binary['sha256'], argv=prefix + [binary['path']] + args, cwd=j['cwd'], env=extra,
                   cpu=str(self.a.cpu), host=socket.gethostname(), inputs={}, bench_lock=campaign.bench_status(),
                   start_utc=campaign.utc(), status=None, exit=None, gpu_witness_uuids=[], worker='gpu_worker_v3',
                   binding=self.binding, ownership_mode=None)
        return rec

    def write(self, out, rec):
        (out / 'RUN.json').write_text(json.dumps(rec, indent=1, default=str) + '\n')

    def run_job(self, j, binary, own):
        out = self.runs / j['id']
        out.mkdir()  # FileExistsError is a collision, handled by the caller
        try:
            rec = self.base_record(j, binary, out)
        except Exception:
            self.write(out, dict(schema='dc262-run/v3', id=j['id'], status='JOB_STAGE_ERROR', exit=None,
                                 gpu_witness_uuids=[], stage_error=traceback.format_exc(), binding=self.binding))
            return dict(status='JOB_STAGE_ERROR'), 'JOB_STAGE'
        rec['ownership_mode'] = own.mode
        try:
            rec['inputs'] = {p: campaign.admit(self.root, p, s) for p, s in j['inputs'].items()}
        except Exception as e:
            rec.update(status='INPUT_ADMISSION_FAILED', error=repr(e)); self.write(out, rec)
            return rec, 'INPUT_ADMISSION'
        try:
            before = self.smi.query(); rec['gpu_before'] = before
        except QueryError as e:
            rec.update(status='NOT_LAUNCHED', reason=[e.kind, e.detail]); self.write(out, rec)
            return rec, 'RESOURCE'
        problems = self.smi.admission_problems(before)
        if before['target_pids']: problems.append(f'process on target UUID: {before["target_pids"]}')
        if not observer_ok(own): problems.append(f'ownership observer unhealthy: alive={own.is_alive()} errors={own.errors}')
        if problems:
            rec.update(status='NOT_LAUNCHED', reason=problems); self.write(out, rec)
            return rec, 'RESOURCE'
        if self.cancel.is_set():  # last check immediately before Popen
            rec.update(status='CANCELLED_BEFORE_LAUNCH'); self.write(out, rec)
            return rec, 'CANCELLED'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('MC_EXPERIMENT_', 'MC_DIAG_', 'OMP_', 'CUDA_'))}
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LD_LIBRARY_PATH=campaign.LD, **rec['env'])
        lock = threading.Lock()
        sampler = dict(ok=0, failed=0, errors=[], foreign={}, witness=set())
        stop = threading.Event()
        status, stage_error, t0 = 'EXITED', None, time.time()
        signals, cleanup_errors = [], []
        with open(out / 'stdout.log', 'w') as so, open(out / 'stderr.log', 'w') as se:
            try:
                p = subprocess.Popen(rec['argv'], cwd=j['cwd'], env=env, stdout=so, stderr=se, start_new_session=True)
                self.launched += 1
            except Exception:
                rec.update(status='JOB_STAGE_ERROR', stage_error=traceback.format_exc()); self.write(out, rec)
                return rec, 'JOB_STAGE'
            th = None
            try:
                own.watch(p.pid)
                def sample():
                    while not stop.is_set():
                        try:
                            own.refresh(); pre = live_owned(own)
                            st = self.smi.query()
                            own.refresh(); post = live_owned(own)
                            mine, foreign = classify(st['target_pids'], pre, post)
                            with lock:
                                sampler['ok'] += 1
                                if mine: sampler['witness'].add(self.a.uuid)
                                for pid in foreign: sampler['foreign'].setdefault(pid, st['utc'])
                        except Exception as e:
                            with lock:
                                pass
                                if len(sampler['errors']) < 20: sampler['errors'].append(repr(e))
                        stop.wait(SAMPLE_S)
                th = threading.Thread(target=sample, daemon=True); th.start()
                while p.poll() is None:
                    if self.cancel.is_set(): status = 'CANCELLED'; break
                    if time.time() - t0 > self.a.job_timeout: status = 'TIMEOUT'; break
                    time.sleep(0.1)
            except Exception as e:
                stage_error = traceback.format_exc()
                status = 'JOB_STAGE_ERROR'
            # Settle the sampler (and with it every in-flight query) before ownership is classified (R2-M1).
            stop.set()
            if th: th.join(self.a.query_timeout * 2 + 10)
            sampler_unjoined = bool(th and th.is_alive())
            # Bounded cleanup on every path: the root and every owned descendant must be gone.
            try:
                own.refresh()
                live = own.known_live()
            except Exception as e:
                live, cleanup_errors = None, [f'ownership refresh failed: {e}']
            if p.poll() is None or live or live is None:
                if status == 'EXITED' and p.poll() is not None: status = 'EXITED_WITH_OWNED_SURVIVORS'
                s, e = terminate_owned(own, p, self.a.cleanup_grace)
                signals += s; cleanup_errors += e
            try: p.wait(timeout=self.a.cleanup_grace)
            except subprocess.TimeoutExpired: cleanup_errors.append(f'job root {p.pid} not reaped')
            try:
                own.refresh(); remaining = own.known_live()
            except Exception as e:
                remaining = None; cleanup_errors.append(f'final ownership refresh failed: {e}')
            try:
                q_owned = query_identities_owned(own, self.smi)
            except Exception as e:
                q_owned = None; cleanup_errors.append(f'query/ownership check failed: {e}')
            if q_owned: cleanup_errors.append(f'query processes appear owned: {q_owned}')
        with lock:
            samp = dict(ok=sampler['ok'], failed=sampler['failed'], errors=list(sampler['errors']),
                        foreign_on_target_during={str(k): v for k, v in sampler['foreign'].items()},
                        unjoined=sampler_unjoined, interval_s=SAMPLE_S)
            rec['gpu_witness_uuids'] = sorted(sampler['witness'])
        cleanup_failed = bool(cleanup_errors) or remaining is None or bool(remaining) or p.poll() is None
        after, after_error = None, None
        try: after = self.smi.query()
        except QueryError as e: after_error = [e.kind, e.detail]
        after_problems = (self.smi.admission_problems(after) + ([f'process on target UUID: {after["target_pids"]}']
                          if after['target_pids'] else [])) if after else []
        if cleanup_failed: status = 'CLEANUP_FAILED'
        rec.update(status=status, exit=p.returncode, wall_s_unqualified=round(time.time() - t0, 2), end_utc=campaign.utc(),
                   gpu_after=after, stage_error=stage_error,
                   cleanup=dict(signals=signals, errors=cleanup_errors, owned_live_after=remaining,
                                sampler_settled_before_classification=not sampler_unjoined),
                   resource=dict(sampler=samp, after_error=after_error, problems_after=after_problems))
        w = [l.strip() for l in open(out / 'stderr.log', errors='replace') if l.startswith('MC_EXPERIMENT_CCF_DC arm=') and '/' in l]
        rec['dc_witness'] = w[-1] if w else None
        rec['outputs'] = {str(f.relative_to(out)): dict(bytes=f.stat().st_size, sha256=campaign.sha256(f))
                          for f in out.rglob('*') if f.is_file() and f.name != 'RUN.json'}
        self.write(out, rec)
        if cleanup_failed: return rec, 'CLEANUP_FAILED'
        if status == 'JOB_STAGE_ERROR': return rec, 'JOB_STAGE'
        if status == 'CANCELLED': return rec, 'CANCELLED'
        if status == 'TIMEOUT': return rec, 'TIMEOUT'
        if (status != 'EXITED' or samp['failed'] or samp['unjoined'] or samp['foreign_on_target_during']
                or after_error or after_problems):
            return rec, 'RESOURCE'
        if samp['ok'] == 0 or rec['gpu_witness_uuids'] != [self.a.uuid]:
            rec['route_witness_problem'] = dict(samples_ok=samp['ok'], witness=rec['gpu_witness_uuids'])
            self.write(out, rec)
            return rec, 'RESOURCE'
        return rec, 'OK'

    # ---- main -------------------------------------------------------------
    def main(self):
        a = self.a
        try:
            q, binaries, problems = self.bind()
        except Exception as e:
            problems, q = [f'binding failed: {e!r}'], None
        if problems:
            print(json.dumps(dict(kind='INVALID_BINDING', utc=campaign.utc(), problems=problems, binding=self.binding)))
            return EXIT['INVALID']
        try:
            self.runs.mkdir(parents=True, exist_ok=True)
            self.log = open(self.runs / f'worker-v4-{a.cpu}.log', 'a')
            lease = open(self.lock_path, 'a')
        except OSError as e:
            print(json.dumps(dict(kind='PRELEASE_IO_ERROR', utc=campaign.utc(), error=repr(e), binding=self.binding)))
            return EXIT['PRELEASE_IO']
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.receipt('STOP', reason='LEASE_BUSY'); return EXIT['RESOURCE']
        for s in (signal.SIGTERM, signal.SIGINT): signal.signal(s, lambda *_: self.cancel.set())
        own = ProcessOwnership()
        try:
            own.activate(native_required=sys.platform == 'linux')
            own.start()
        except Exception as e:
            self.receipt('STOP', reason='OBSERVER_UNHEALTHY', error=repr(e))
            fcntl.flock(lease, fcntl.LOCK_UN); return EXIT['RESOURCE']
        code = None
        try:
            for j in q:
                if self.cancel.is_set():
                    self.receipt('STOP', reason='CANCELLED', before=j['id']); code = EXIT['CANCELLED']; break
                if campaign.usage_bytes(self.root) + tree_bytes(self.runs) > campaign.CAP:
                    self.receipt('STOP', reason='SCRATCH_CAP', before=j['id']); code = EXIT['CAP']; break
                if not observer_ok(own):
                    self.receipt('STOP', reason='OBSERVER_UNHEALTHY', before=j['id'], alive=own.is_alive(), errors=own.errors)
                    code = EXIT['RESOURCE']; break
                try: st = self.smi.query()
                except QueryError as e:
                    self.receipt('STOP', reason=e.kind, detail=e.detail, before=j['id']); code = EXIT['RESOURCE']; break
                problems = self.smi.admission_problems(st) + ([f'process on target UUID: {st["target_pids"]}'] if st['target_pids'] else [])
                if problems:
                    self.receipt('STOP', reason='ADMISSION_REFUSED', problems=problems, before=j['id'], gpu=st)
                    code = EXIT['RESOURCE']; break
                if self.cancel.is_set():
                    self.receipt('STOP', reason='CANCELLED', before=j['id']); code = EXIT['CANCELLED']; break
                try:
                    rec, outcome = self.run_job(j, binaries[j['build']], own)
                except FileExistsError:
                    self.receipt('STOP', reason='DIRECTORY_COLLISION', job=j['id']); code = EXIT['JOB_STAGE']; break
                self.note(j['id'], rec['status'], rec.get('exit'), rec.get('dc_witness'))
                if outcome == 'CLEANUP_FAILED':
                    self.hold_lease('job cleanup not verified', job=j['id'], cleanup=rec.get('cleanup'))
                if outcome != 'OK':
                    self.receipt('STOP', reason=outcome, job=j['id'], status=rec['status'],
                                 resource=rec.get('resource'), cleanup=rec.get('cleanup'))
                    code = EXIT[outcome]; break
        except Exception:
            self.receipt('STOP', reason='WORKER_STAGE_ERROR', error=traceback.format_exc()); code = EXIT['JOB_STAGE']
        # Every path: observer stop, owned-process check, restore, census, final health, then release.
        own.stop(); own.join(5)
        try:
            leftover = own.known_live()
            if leftover or own.is_alive(): raise RuntimeError(f'owned live={leftover} observer alive={own.is_alive()}')
            own.restore()
        except Exception as e:
            # Release only when nothing could have been owned: no job launched, no owned identity ever
            # recorded, every query reaped. Any other uncertainty keeps the lease (R2-m1 policy).
            with self.smi.lock: unreaped = sorted(self.smi.unreaped)
            if self.launched == 0 and not own.identities and not unreaped:
                self.receipt('STOP', reason='OBSERVER_FAILED_ZERO_JOBS', error=repr(e), launched=0, owned_identities=0,
                             queries_unreaped=0)
                if code in (None, EXIT['OK']): code = EXIT['RESOURCE']
            else:
                self.hold_lease('worker-level cleanup or ownership restore not verified', error=repr(e),
                                launched=self.launched, owned_identities=len(own.identities), queries_unreaped=unreaped)
        census = self.census(q)
        if code is None: code = EXIT['OK'] if census['complete'] else EXIT['INCOMPLETE']
        final, final_error, final_problems = None, None, []
        try:
            final = self.smi.query()
            final_problems = self.smi.admission_problems(final) + ([f'process on target UUID: {final["target_pids"]}'] if final['target_pids'] else [])
        except QueryError as e:
            final_error = [e.kind, e.detail]
        if code == EXIT['OK'] and (final_error or final_problems): code = EXIT['FINAL_HEALTH']
        self.receipt('FINAL', code=code, census=census, final_gpu=final, final_error=final_error, final_problems=final_problems)
        fcntl.flock(lease, fcntl.LOCK_UN); lease.close()
        return code


def tree_bytes(path):
    total = 0
    for d, _, files in os.walk(path):
        for f in files:
            try: total += os.lstat(os.path.join(d, f)).st_size
            except OSError: pass
    return total


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ['root', 'queue', 'queue-sha256', 'runs-dir', 'binaries', 'binaries-sha256', 'uuid']:
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--expected-jobs', type=int, required=True)
    ap.add_argument('--cpu', type=int, required=True); ap.add_argument('--gpu-index', type=int, required=True)
    ap.add_argument('--lock-dir', default='/tmp')
    ap.add_argument('--job-timeout', type=float, default=3600); ap.add_argument('--query-timeout', type=float, default=30)
    ap.add_argument('--cleanup-grace', type=float, default=10)
    ap.add_argument('--smi', default='nvidia-smi')
    ap.add_argument('--prefix', default='taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log')
    return ap.parse_args(argv)


def main(argv=None):
    return Worker(parse(argv)).main()


if __name__ == '__main__':
    sys.exit(main())
