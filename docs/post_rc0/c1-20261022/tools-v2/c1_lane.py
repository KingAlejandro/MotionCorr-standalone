"""C1 lane helpers, tools v2 (task-local; the shared QF library docs/rc0/qf/tools/qual_lib.py is not edited).

install()      bench lock probed, never waited on (#198 policy: correctness does not wait for it).
run_case_nb()  replacement for qual_lib.run_case on the GPU3 lane with the stop-on-contention rules:
               * the canonical GPU3 lease is taken with LOCK_EX|LOCK_NB; contention stops before launch (rc None, error recorded);
               * a foreign compute process on the lane GPU stops before launch (no 1800 s polling, nothing is touched);
               * pre-run GPU health (c1_health_check.py: identity, ECC, row remap, retired pages, no compute process) runs while the lease is held;
               * post-run GPU health runs while the lease is still held; a failure turns a successful child into rc 37 (child_rc kept);
               * the lease is never nested: callers must not hold it around run_case_nb.
Same child command line, environment handling, GPU sampler and record fields as qual_lib.run_case (rc, wall_s, gpu_witness, ...).
"""
import fcntl, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTH_CMD = [os.environ.get('C1_PY', sys.executable), str(HERE / 'c1_health_check.py')]
TIME_PREFIX = lambda p: ['/usr/bin/time', '-v', '-o', str(p)]      # replaced by host tests only
TASKSET = 'taskset'


def _bench_probe():
    with open('/tmp/motioncorr-bench.lock', 'a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); free = True
        except BlockingIOError:
            free = False
    return {'policy': '#198: correctness does not wait for the bench lock', 'probe_free': free, 'waited_s': 0}


def install():
    import qual_lib
    qual_lib.wait_bench_free = lambda *a, **k: _bench_probe()


def health(label):
    r = subprocess.run([*HEALTH_CMD, label], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr)[-400:]


def run_case_nb(label, binary, args, cwd, logdir, gpu, extra_env=None, witness=None, timeout=7200):
    import qual_lib as q
    logdir = Path(logdir); logdir.mkdir(parents=True, exist_ok=True)
    stdout_p, time_p = logdir / f'{label}.stdout', logdir / f'{label}.time'
    cmd = [*TIME_PREFIX(time_p), TASKSET, '-c', q.CPUS, str(binary), *map(str, args)]
    env = q.base_env(gpu); env.update(extra_env or {})
    rec = {'label': label, 'binary': str(binary), 'binary_sha256': q.sha256_file(binary), 'args': list(map(str, args)), 'cwd': str(cwd),
           'cpu_mask': q.CPUS, 'extra_env': dict(extra_env or {}), 'gpu_run': gpu, 'start_utc': time.strftime('%FT%TZ', time.gmtime()),
           'env': {k: env[k] for k in ('CUDA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LD_LIBRARY_PATH') if k in env}}
    lock_fd = None
    try:
        if gpu:
            lock_fd = os.open(q.LANE_GPU_LOCK, os.O_RDWR)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                rec.update(rc=None, error='GPU3 lease contended; stopped before launch (no wait, no retry)'); return rec
            rec['bench_gate'] = _bench_probe()
            foreign = [r for r in q.smi_rows() if r[0] == q.LANE_GPU_UUID]
            if foreign:
                rec.update(rc=None, error='foreign compute process on the lane GPU; stopped before launch', foreign=foreign); return rec
            pre, msg = health(f'{label}-pre'); rec['health_pre'] = {'rc': pre, 'msg': msg}
            if pre:
                rec.update(rc=None, error=f'pre-run GPU health failed rc={pre}; stopped before launch'); return rec
        t0 = time.monotonic()
        with open(stdout_p, 'wb') as out:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
            sampler = q.GpuSampler(proc.pid) if gpu else None
            if sampler: sampler.start()
            try:
                rec['rc'] = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill(); rec['rc'] = None; rec['error'] = 'timeout; killed (own child)'
            finally:
                if sampler: sampler.stop()
        rec['wall_s'] = round(time.monotonic() - t0, 3)
        if sampler:
            rec['gpu_witness'] = {'uuids_seen_for_pid': sorted(sampler.uuids), 'peak_mib': sampler.peak_mib, 'smi_samples': sampler.samples,
                                  'pid_hits': sampler.hits, 'on_lane_gpu_only': sampler.uuids == {q.LANE_GPU_UUID} if sampler.uuids else None}
        if gpu:      # still holding the lease
            post, msg = health(f'{label}-post'); rec['health_post'] = {'rc': post, 'msg': msg}
            if post:
                rec['child_rc'] = rec.get('rc')
                if rec.get('rc') == 0: rec['rc'] = 37
                rec['error'] = rec.get('error') or f'post-run GPU health failed rc={post}'
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)
    rec.update(q.parse_time_v(time_p)); rec['stdout'] = str(stdout_p); rec['time_log'] = str(time_p)
    if witness and Path(witness).exists(): rec['ingest_witness'] = Path(witness).read_text().splitlines()
    return rec
