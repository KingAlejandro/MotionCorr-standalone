#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W4 frozen native campaign; launch under taskset -c 14,15 after remote_build.py.

Runs exactly the arms in campaign-manifest.json, sequentially, then the
unchanged checker on each. GPU1 correctness lock is nonblocking and is held
from admission through the final healthcheck. Any stop condition ends the
campaign with its receipts; nothing is retried.
"""
import datetime, fcntl, hashlib, json, os, pathlib, shutil, subprocess, sys

root = pathlib.Path(sys.argv[1]).resolve()
M = json.loads((root/'campaign-manifest.json').read_text())
U = M['resources']['gpu_uuid']; PY = '/home/alex/.mc-venv/bin/python3'
L = root/'run-logs'; L.mkdir(exist_ok=True)
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p, d): pathlib.Path(p).write_text(json.dumps(d, indent=2)+'\n')
rows = []
def run(label, argv, env=None, cwd=None, expected=(0,)):
    start = now()
    with (L/(label+'.log')).open('w') as log:
        p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=cwd, env=env)
        write(L/(label+'.started.json'), dict(pid=p.pid, start=start, argv=argv, cwd=str(cwd or os.getcwd()),
              env={k: v for k, v in (env or {}).items() if k.startswith(('MC_', 'CUDA_', 'OMP_', 'OPENBLAS_', 'MKL_', 'NUMEXPR_')) or k == 'LD_LIBRARY_PATH'},
              affinity=sorted(os.sched_getaffinity(p.pid))))
        rc = p.wait()
    (L/(label+'.exit')).write_text(f'{rc}\n')
    row = dict(label=label, argv=argv, start=start, end=now(), pid=p.pid, exit=rc, expected=list(expected))
    rows.append(row); write(L/'commands.json', rows)
    if rc not in expected: raise RuntimeError(f'{label} exit {rc}')
    return (L/(label+'.log')).read_text()

def health(tag):
    m = run(f'health-{tag}-mapping', ['nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu', '--format=csv,noheader'])
    line = [l for l in m.splitlines() if U in l]
    assert len(line) == 1 and line[0].split(',')[0].strip() == '1', m
    apps = run(f'health-{tag}-apps', ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name', '--format=csv,noheader'])
    assert U not in apps, apps
    ecc = run(f'health-{tag}-ecc', ['nvidia-smi', '-i', U, '--query-gpu=ecc.errors.uncorrected.volatile.total,ecc.errors.corrected.volatile.total', '--format=csv,noheader'])
    assert ecc.split(',')[0].strip() in ('0', '[N/A]'), ecc
    return dict(tag=tag, utc=now(), mapping=line[0], apps=apps.strip(), ecc=ecc.strip())

def main():
    assert os.sched_getaffinity(0) == {14, 15}
    assert M['frozen_before_launch'] and len(M['arms']) == M['native_processes_planned'] <= M['native_process_cap']
    assert sha(root/'campaign-manifest.json') == (root/'campaign-manifest.sha256').read_text().split()[0]
    build = json.loads((root/'logs/binary-hashes.json').read_text())
    binaries = {k: root/f'build-{k}/motioncorr' for k in ['cpu', 'cuda']}
    for k, b in binaries.items(): assert sha(b) == build[k], k
    # Fixtures: copy read-only originals, then verify against the pinned MANIFEST.
    fx = root/'fixtures'; fx.mkdir()
    srcdir = pathlib.Path(M['fixtures']['source_dir'])
    shutil.copyfile(srcdir/'MANIFEST.json', fx/'MANIFEST.json')
    assert sha(fx/'MANIFEST.json') == M['fixtures']['manifest_sha256']
    man = json.loads((fx/'MANIFEST.json').read_text())
    truth = {}
    for case in M['fixtures']['cases']:
        for name, h in man['cases'][case]['files'].items():
            shutil.copyfile(srcdir/name, fx/name); assert sha(fx/name) == h, name
        out = subprocess.run([PY, '-I', '-c', 'import numpy as np,sys;f=np.load(sys.argv[1]);t=f[:,0,0,:];assert (f==t[:,None,None,:]).all();print("\\n".join("%r %r"%(float(a),float(b)) for a,b in t))', str(fx/f'{case}_field.npy')],
                             capture_output=True, text=True, check=True).stdout
        truth[case] = [tuple(float(v) for v in l.split()) for l in out.splitlines()]
    files = {'truth-integer.txt': truth['integer'], 'truth-fractional.txt': truth['fractional'],
             'truth-integer-perturbed.txt': [(x+1.0, y) if i == 4 else (x, y) for i, (x, y) in enumerate(truth['integer'])]}
    for n, t in files.items(): (root/n).write_text(''.join(f'{x!r} {y!r}\n' for x, y in t))
    write(L/'inputs.json', dict(utc=now(), fixtures={p.name: sha(p) for p in sorted(fx.iterdir())},
          shift_files={n: dict(sha256=sha(root/n), values=t) for n, t in files.items()}, binaries=build))
    base = {k: v for k, v in os.environ.items() if not k.startswith(('MC_DIAG_', 'MC_CCF_', 'MC_W4_'))}
    base.update(PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES=U, CUDA_DEVICE_ORDER='PCI_BUS_ID', LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64')
    with open('/tmp/motioncorr-gpu1-correctness.lock', 'a') as gpu_lock:
        try:
            fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            write(L/'gpu-lock-busy.json', dict(utc=now())); return 75
        bench = 'free'
        with open('/tmp/motioncorr-bench.lock', 'a') as b:
            try: fcntl.flock(b, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(b, fcntl.LOCK_UN)
            except BlockingIOError: bench = 'held by another process (recorded; correctness does not wait)'
        healths = [health('pre')]
        write(L/'locks.json', dict(utc=now(), pid=os.getpid(), gpu_lock=gpu_lock.name, bench_probe=bench))
        try:
            for arm in M['arms']:
                d = root/'runs'/arm['label']; (d/'state').mkdir(parents=True)
                env = dict(base, MC_W4_STATE=str(d/'state'))
                for k, v in arm['env'].items(): env[k] = str(root/v) if k == 'MC_W4_GLOBAL_SHIFTS' else v
                argv = [str(binaries[arm['backend']]), '--i', arm['case']+'.star', '--o', str(d/'out'), '--use_own', '--j', '1',
                        '--patch_x', '1', '--patch_y', '1', '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW',
                        '--first_frame_sum', '1', '--last_frame_sum', '5', '--skip_logfile']
                if arm['backend'] == 'cuda': argv += ['--gpu', '0']
                run(arm['label'], argv, env=env, cwd=fx)
                if arm['backend'] == 'cuda': healths.append(health('after-'+arm['label']))
                run('check-'+arm['label'], [PY, str(root/'src/tools/check_motion_diagnostics.py'), '--fixtures', str(fx), '--case', arm['case'],
                    '--candidate', str(d/'out'/f"{arm['case']}.star"), '--summed-image', str(d/'out'/f"{arm['case']}.mrc"), '--json', str(d/'checker.json')],
                    env=base, expected=(0, 1))
        finally:
            write(L/'health.json', healths)
            healths.append(health('final'))
            write(L/'health.json', healths)
            write(L/'locks.json', dict(json.loads((L/'locks.json').read_text()), released_utc=now()))
    return 0

if __name__ == '__main__':
    try:
        rc = main()
    except Exception as e:
        (L/'driver-error.txt').write_text(repr(e)+'\n'); rc = 1
    (root/'run.exit').write_text(f'{rc}\n')
    sys.exit(rc)
