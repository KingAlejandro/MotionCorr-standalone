#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W4 overlay build; launch under taskset -c 14,15 in fresh task scratch ROOT.

ROOT contains source.tar.gz (git archive of 805d9de2), make_overlay.py and
w4_inject.h. The shared build lock is taken nonblocking; busy exits 75.
"""
import datetime, fcntl, hashlib, json, os, pathlib, subprocess, sys, tarfile

root = pathlib.Path(sys.argv[1]).resolve()
logs = root/'logs'; logs.mkdir(exist_ok=True)
records = []
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def run(label, argv, cwd=None):
    with (logs/(label+'.log')).open('w') as out:
        p = subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, cwd=cwd)
    records.append(dict(label=label, argv=argv, exit=p.returncode, utc=now()))
    (logs/'build-commands.json').write_text(json.dumps(records, indent=2)+'\n')
    if p.returncode: raise RuntimeError(label+' failed')

def main():
    assert os.sched_getaffinity(0) == {14, 15}, os.sched_getaffinity(0)
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    python = '/home/alex/.mc-venv/bin/python3'; nvcc = '/usr/local/cuda-12.8/bin/nvcc'
    src = root/'src'
    src.mkdir()
    with tarfile.open(root/'source.tar.gz') as t: t.extractall(src, filter='data')
    original = {str(p.relative_to(src)): sha(p) for p in sorted(src.rglob('*')) if p.is_file()}
    run('overlay', [python, str(root/'make_overlay.py'), str(src)])
    changed = {str(p.relative_to(src)): sha(p) for p in sorted(src.rglob('*')) if p.is_file()}
    diff = {k: dict(before=original.get(k), after=v) for k, v in changed.items() if original.get(k) != v}
    assert set(diff) == {'src/motioncorr_runner.cpp', 'src/acc/cuda/cuda_alignpatch.cu', 'src/w4_inject.h'}, sorted(diff)
    identity = dict(utc=now(), host=os.uname().nodename, affinity=sorted(os.sched_getaffinity(0)),
                    source_archive_sha256=sha(root/'source.tar.gz'), make_overlay_sha256=sha(root/'make_overlay.py'),
                    w4_inject_sha256=sha(root/'w4_inject.h'), driver_sha256=sha(__file__), overlay_changed_files=diff,
                    archived_files=len(original))
    (logs/'source-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    run('overlay-diff', ['bash', '-c', f'cd {root} && mkdir -p pristine && tar xzf source.tar.gz -C pristine src/motioncorr_runner.cpp src/acc/cuda/cuda_alignpatch.cu && '
        f'diff -u pristine/src/motioncorr_runner.cpp src/src/motioncorr_runner.cpp > logs/overlay.diff; diff -u pristine/src/acc/cuda/cuda_alignpatch.cu src/src/acc/cuda/cuda_alignpatch.cu >> logs/overlay.diff; test -s logs/overlay.diff'])
    run('nvcc-version', [nvcc, '--version'])
    lock = open('/tmp/motioncorr-build.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owners = subprocess.run(['bash', '-c', 'ps -eo pid,user,psr,etime,args | grep -E "cmake|make|nvcc|cc1plus" | grep -v grep'], capture_output=True, text=True).stdout
        (logs/'build-lock-busy.json').write_text(json.dumps(dict(utc=now(), lock=lock.name, owners=owners), indent=2)+'\n')
        return 75
    (logs/'build-lock.json').write_text(json.dumps(dict(utc=now(), pid=os.getpid(), mode='exclusive nonblocking', parallel=2), indent=2)+'\n')
    for kind in ['cpu', 'cuda']:
        build = root/('build-'+kind)
        opts = ['-DCUDA=OFF'] if kind == 'cpu' else ['-DCUDA=ON', '-DUSE_NVCOMP=OFF', '-DCMAKE_CUDA_ARCHITECTURES=80',
                '-DCMAKE_CUDA_COMPILER='+nvcc, '-DCUDAToolkit_ROOT=/usr/local/cuda-12.8']
        run('configure-'+kind, ['cmake', '-S', str(src), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=ON',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DPython3_EXECUTABLE='+python] + opts)
        run('build-'+kind, ['cmake', '--build', str(build), '--parallel', '2', '--target', 'motioncorr'])
        run('ldd-'+kind, ['ldd', str(build/'motioncorr')])
    fcntl.flock(lock, fcntl.LOCK_UN)
    (logs/'build-lock.json').write_text(json.dumps(dict(json.loads((logs/'build-lock.json').read_text()), released_utc=now()), indent=2)+'\n')
    (logs/'binary-hashes.json').write_text(json.dumps({k: sha(root/f'build-{k}/motioncorr') for k in ['cpu', 'cuda']}, indent=2)+'\n')
    return 0

if __name__ == '__main__':
    try:
        rc = main()
    except Exception as e:
        print(repr(e), flush=True); rc = 1
    (root/'build.exit').write_text(f'{rc}\n')
    sys.exit(rc)
