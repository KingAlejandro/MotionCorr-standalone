#!/usr/bin/env python3
"""Shared helpers for the W-QUAL native qualification (issue #198, lane GPU1 + CPUs 104-111).

Every run takes the GPU1 correctness flock per run, waits while a foreign compute process
is on GPU1, samples nvidia-smi for the child's physical GPU UUID, and records rc, wall,
peak RSS (/usr/bin/time -v) and the --ingest_witness lines. The driver itself is started
under `taskset -c 104-111`, so every child inherits that mask.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

W = Path('/mnt/clathrin/alex-motioncorr-rc0/W-QUAL')
SRC = W / 'src'
CPUS = '104-111'
GPU1_UUID = 'GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d'
GPU1_LOCK = '/tmp/motioncorr-gpu1-correctness.lock'
NVCOMP_LIB = '/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib'
BIN = {
    'cpu': W / 'build-cpu' / 'motioncorr',
    'cuda': W / 'build-cuda' / 'motioncorr',
    'nvcomp': W / 'build-nvcomp' / 'motioncorr',
    'pre178': W / 'build-pre178-nvcomp' / 'motioncorr',
}
COMPARE_TREES = SRC / 'docs/issue85_laneC/compare_output_trees.py'
COMPARE_MC = SRC / 'tools/compare_motioncorr.py'
PY = '/home/alex/.mc-venv/bin/python3'


def sha256_file(path, chunk=8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def base_env(gpu: bool) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('OMP_', 'MC_', 'GLIBC_'))}
    env['LD_LIBRARY_PATH'] = f'/usr/local/cuda-12.8/lib64:{NVCOMP_LIB}'
    env['OMP_NUM_THREADS'] = '8'
    env['OPENBLAS_NUM_THREADS'] = '1'
    if gpu:
        env['CUDA_VISIBLE_DEVICES'] = GPU1_UUID
        env['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
    return env


def smi_rows(query='gpu_uuid,pid,used_memory'):
    out = subprocess.run(['nvidia-smi', f'--query-compute-apps={query}', '--format=csv,noheader,nounits'],
                         capture_output=True, text=True, timeout=30)
    rows = []
    for line in out.stdout.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) == 3:
            rows.append(parts)
    return rows


class GpuSampler(threading.Thread):
    """Poll nvidia-smi; keep the (uuid, MiB) rows whose pid is the child's."""
    def __init__(self, pid, interval=0.1):
        super().__init__(daemon=True)
        self.root, self.interval = int(pid), interval
        self.pid = str(pid)
        self.stop_evt = threading.Event()
        self.uuids, self.peak_mib, self.samples, self.hits = set(), 0, 0, 0

    def descendants(self):
        """root pid plus all its live descendants (/usr/bin/time forks the payload, so the CUDA pid is a child)."""
        parent = {}
        for d in os.listdir('/proc'):
            if d.isdigit():
                try:
                    stat = open(f'/proc/{d}/stat').read()
                    parent[int(d)] = int(stat.rsplit(')', 1)[1].split()[1])
                except (OSError, ValueError, IndexError):
                    pass
        fam = {self.root}
        grew = True
        while grew:
            grew = False
            for p, pp in parent.items():
                if pp in fam and p not in fam:
                    fam.add(p)
                    grew = True
        return fam

    def run(self):
        while not self.stop_evt.is_set():
            try:
                rows = smi_rows()
                self.samples += 1
                family = self.descendants()
                for uuid, pid, mem in rows:
                    if int(pid) in family:
                        self.hits += 1
                        self.uuids.add(uuid)
                        self.peak_mib = max(self.peak_mib, int(mem))
            except Exception:
                pass
            self.stop_evt.wait(self.interval)

    def stop(self):
        self.stop_evt.set()
        self.join(timeout=10)


BENCH_LOCK = '/tmp/motioncorr-bench.lock'


def wait_bench_free(poll=60, max_wait=6 * 3600):
    """Coordinator rule: before a heavy GPU run or build, `flock -n bench true`; if held, poll.

    Only probes (non-blocking, released at once); never holds the lock and never touches its owner.
    """
    start = time.time()
    polls = 0
    while True:
        fd = os.open(BENCH_LOCK, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return {'bench_polls_held': polls, 'bench_waited_s': round(time.time() - start, 1)}
        except OSError:
            polls += 1
        finally:
            os.close(fd)
        if time.time() - start > max_wait:
            return {'bench_polls_held': polls, 'bench_waited_s': round(time.time() - start, 1), 'timed_out': True}
        time.sleep(poll)


def wait_gpu1_free(max_wait=1800):
    """Called with the GPU1 lock held. Foreign process on GPU1 -> wait, never touch it."""
    start = time.time()
    while True:
        foreign = [r for r in smi_rows() if r[0] == GPU1_UUID]
        if not foreign:
            return {'waited_s': round(time.time() - start, 1), 'foreign': []}
        if time.time() - start > max_wait:
            return {'waited_s': round(time.time() - start, 1), 'foreign': foreign, 'timed_out': True}
        time.sleep(10)


def parse_time_v(path):
    info = {}
    try:
        text = Path(path).read_text()
    except OSError:
        return info
    m = re.search(r'Maximum resident set size \(kbytes\): (\d+)', text)
    if m:
        info['max_rss_kib'] = int(m.group(1))
    m = re.search(r'Exit status: (\d+)', text)
    if m:
        info['time_exit_status'] = int(m.group(1))
    m = re.search(r'Elapsed \(wall clock\) time.*: ([\d:.]+)', text)
    if m:
        info['elapsed'] = m.group(1)
    return info


def run_case(label, binary, args, cwd, logdir, gpu, extra_env=None, witness=None, timeout=7200):
    """Run one motioncorr invocation. `args` exclude the binary. Returns a record dict.

    gpu=True -> holds the GPU1 flock for the duration, checks for a foreign GPU1 process
    first, and samples the GPU UUID. CPU-only runs are only CPU-pinned.
    """
    logdir = Path(logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    stdout_p, time_p = logdir / f'{label}.stdout', logdir / f'{label}.time'
    cmd = ['/usr/bin/time', '-v', '-o', str(time_p), 'taskset', '-c', CPUS, str(binary), *map(str, args)]
    env = base_env(gpu)
    env.update(extra_env or {})
    rec = {'label': label, 'binary': str(binary), 'binary_sha256': sha256_file(binary),
           'args': list(map(str, args)), 'cwd': str(cwd), 'cpu_mask': CPUS,
           'env': {k: env[k] for k in ('CUDA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER', 'OMP_NUM_THREADS',
                                       'OPENBLAS_NUM_THREADS', 'LD_LIBRARY_PATH') if k in env},
           'extra_env': dict(extra_env or {}), 'gpu_run': gpu, 'start_utc': time.strftime('%FT%TZ', time.gmtime())}
    lock_fd = None
    try:
        if gpu:
            lock_fd = os.open(GPU1_LOCK, os.O_RDWR)
            t0 = time.time()
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            rec['lock_wait_s'] = round(time.time() - t0, 1)
            rec['bench_gate'] = wait_bench_free()
            if rec['bench_gate'].get('timed_out'):
                rec['rc'] = None
                rec['error'] = 'bench lock never free; run not started'
                return rec
            rec['gpu1_precheck'] = wait_gpu1_free()
            if rec['gpu1_precheck'].get('timed_out'):
                rec['rc'] = None
                rec['error'] = 'foreign process on GPU1 for the whole wait; run not started'
                return rec
        t0 = time.monotonic()
        with open(stdout_p, 'wb') as out:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
            sampler = GpuSampler(proc.pid) if gpu else None
            if sampler:
                sampler.start()
            try:
                rec['rc'] = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                rec['rc'] = None
                rec['error'] = 'timeout; killed (own child)'
            finally:
                if sampler:
                    sampler.stop()
        rec['wall_s'] = round(time.monotonic() - t0, 3)
        if sampler:
            rec['gpu_witness'] = {'uuids_seen_for_pid': sorted(sampler.uuids), 'peak_mib': sampler.peak_mib,
                                  'smi_samples': sampler.samples, 'pid_hits': sampler.hits,
                                  'on_gpu1_only': sampler.uuids == {GPU1_UUID} if sampler.uuids else None}
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    rec.update(parse_time_v(time_p))
    rec['stdout'] = str(stdout_p)
    rec['time_log'] = str(time_p)
    if witness and Path(witness).exists():
        rec['ingest_witness'] = Path(witness).read_text().splitlines()
    return rec


def run_tool(argv, **kw):
    r = subprocess.run(argv, capture_output=True, text=True, **kw)
    return {'argv': list(map(str, argv)), 'rc': r.returncode, 'stdout': r.stdout[-6000:], 'stderr': r.stderr[-3000:]}


def dump(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=False) + '\n')
