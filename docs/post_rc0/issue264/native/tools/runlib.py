# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared run helper for the #264 native lane (GPU1 by UUID, CPUs 14-15, one numeric thread).

GPU runs are made by the caller while it holds the GPU1 correctness lock. A foreign compute
process on GPU1 stops the run (no waiting loop). The child's physical GPU is witnessed by
sampling nvidia-smi compute apps for the child's process family.
"""
import hashlib, os, subprocess, threading, time
from pathlib import Path

SCR = Path(os.environ['G_SCR']); CPUS = os.environ['G_CPUS']; UUID = os.environ['G_GPU_UUID']


def sha256_file(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def compute_apps():
    out = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader'],
                         capture_output=True, text=True, timeout=30).stdout
    return [tuple(p.strip() for p in line.split(',')) for line in out.splitlines() if line.count(',') == 1]


def family(root):
    parent = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                parent[int(d)] = int(open(f'/proc/{d}/stat').read().rsplit(')', 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                pass
    fam, grew = {root}, True
    while grew:
        grew = False
        for p, pp in parent.items():
            if pp in fam and p not in fam:
                fam.add(p); grew = True
    return fam


def run(label, argv, cwd, logdir, gpu, extra_env=None, timeout=7200):
    logdir = Path(logdir); logdir.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('OMP_', 'MC_'))}
    env['OMP_NUM_THREADS'] = '1'
    env.pop('CUDA_VISIBLE_DEVICES', None)
    if gpu:
        foreign = [a for a in compute_apps() if a[0] == UUID]
        if foreign:
            raise SystemExit(f'foreign compute process on GPU1 {foreign}; stopping without waiting')
        env['CUDA_VISIBLE_DEVICES'] = UUID; env['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
    env.update(extra_env or {})
    cmd = ['taskset', '-c', CPUS, *map(str, argv)]
    t0 = time.time()
    with open(logdir / f'{label}.stdout', 'w') as so, open(logdir / f'{label}.stderr', 'w') as se:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=so, stderr=se)
        seen, hits, stop = set(), 0, threading.Event()

        def sample():
            nonlocal hits
            while not stop.is_set():
                try:
                    fam = family(p.pid)
                    for uuid, pid in compute_apps():
                        if int(pid) in fam:
                            seen.add(uuid); hits += 1
                except Exception:
                    pass
                stop.wait(0.2)
        th = threading.Thread(target=sample, daemon=True)
        if gpu:
            th.start()
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill(); rc = p.wait()
        stop.set()
        if gpu:
            th.join(timeout=10)
    return {'label': label, 'argv': cmd, 'cwd': str(cwd), 'rc': rc, 'wall_s': round(time.time() - t0, 2),
            'gpu': gpu, 'gpu_uuids_witnessed': sorted(seen), 'gpu_samples_hit': hits,
            'env': {k: env[k] for k in ('OMP_NUM_THREADS', 'CUDA_VISIBLE_DEVICES', 'MC264_N3_COEFFS') if k in env},
            'stdout': str(logdir / f'{label}.stdout'), 'stderr': str(logdir / f'{label}.stderr')}
