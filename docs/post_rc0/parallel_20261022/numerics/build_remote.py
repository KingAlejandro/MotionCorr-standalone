#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded build driver; launch under taskset -c 10-13 in fresh task scratch."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
logs = root / 'logs'
logs.mkdir(exist_ok=True)
records = []


def run(label, argv, required=True):
    print(label, flush=True)
    with (logs / (label + '.log')).open('w') as out:
        p = subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT)
    (logs / (label + '.exit')).write_text(str(p.returncode) + '\n')
    records.append(dict(label=label, argv=argv, exit=p.returncode,
                        utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    (logs / 'build-commands.json').write_text(json.dumps(records, indent=2) + '\n')
    if required and p.returncode:
        raise RuntimeError(label + ' failed')


def main():
    assert os.sched_getaffinity(0) == {10, 11, 12, 13}
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                      MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    python = Path('/home/alex/.mc-venv/bin/python3')
    nvcc = Path('/usr/local/cuda-12.8/bin/nvcc')
    assert python.is_file() and os.access(python, os.X_OK)
    assert nvcc.is_file() and os.access(nvcc, os.X_OK)
    nvcomp = sorted(Path('/home/alex/nvcomp53').glob('*/include/nvcomp/deflate.h'))
    identity = dict(python=str(python), nvcc=str(nvcc),
                    nvcomp_candidates=[str(p.parents[2]) for p in nvcomp],
                    NVCOMP_ROOT_env=os.environ.get('NVCOMP_ROOT'),
                    affinity=sorted(os.sched_getaffinity(0)),
                    source_archive_sha256=hashlib.sha256((root/'source.tar.gz').read_bytes()).hexdigest(),
                    driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (logs/'discovery.json').write_text(json.dumps(identity, indent=2)+'\n')
    run('python-discovery', [str(python), '-c',
        'import sys,numpy,os,importlib.util;print(sys.executable);print(numpy.__version__);print("scipy_available="+str(importlib.util.find_spec("scipy") is not None));print(os.sched_getaffinity(0))'])
    run('nvcc-discovery', [str(nvcc), '--version'])
    run('disk', ['df', '-h', str(root)])
    # A blocking shared compilation lock is intentional; no GPU is held here.
    print('waiting for /tmp/motioncorr-build.lock', flush=True)
    with open('/tmp/motioncorr-build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        (logs/'build-lock.json').write_text(json.dumps(dict(
            lock=lock.name, acquired_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            pid=os.getpid(), affinity=sorted(os.sched_getaffinity(0)), parallel=2), indent=2)+'\n')
        host = ['hermitian_projection_oracle', 'peak_fit_arithmetic', 'realspace_border_validation']
        native = ['cuda_hermitian_inverse', 'cuda_hermitian_ccf', 'cuda_peak_fit',
                  'cuda_realspace_border_branch',
                  'cuda_hermitian_inverse_no_projection',
                  'cuda_hermitian_inverse_wrapper_no_projection',
                  'cuda_hermitian_inverse_dose_no_projection',
                  'cuda_hermitian_inverse_oracle_session_no_projection',
                  'cuda_hermitian_inverse_oracle_session_zero_boundary',
                  'cuda_hermitian_inverse_oracle_wrapper_zero_boundary',
                  'cuda_hermitian_inverse_oracle_dose_zero_boundary',
                  'cuda_patch_batch_ccf_perpatch_no_projection',
                  'cuda_patch_batch_ccf_batched_no_projection',
                  'cuda_peak_fit_float_denominator',
                  'cuda_realspace_border_branch_x_float',
                  'cuda_realspace_border_branch_y_float']
        for kind in ['cpu', 'cuda']:
            build = root/('build-'+kind)
            opts = ['-DCUDA=OFF'] if kind == 'cpu' else [
                '-DCUDA=ON', '-DUSE_NVCOMP=OFF', '-DCMAKE_CUDA_ARCHITECTURES=80',
                '-DCMAKE_CUDA_COMPILER='+str(nvcc), '-DCUDAToolkit_ROOT=/usr/local/cuda-12.8']
            run('configure-'+kind, ['cmake','-S',str(root/'src'),'-B',str(build),
                '-DCMAKE_BUILD_TYPE=Release','-DBUILD_TESTING=ON',
                '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE='+str(python)] + opts)
            run('build-'+kind, ['cmake','--build',str(build),'--parallel','2',
                '--target','motioncorr'] + host + (native if kind == 'cuda' else []))
            run('ldd-'+kind, ['ldd',str(build/'motioncorr')])
        hashes = {}
        for kind, names in [('cpu', ['motioncorr']+host), ('cuda',['motioncorr']+host+native)]:
            for name in names:
                p=root/('build-'+kind)/name
                hashes[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
        (logs/'binary-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    (root/'build.done').write_text('0\n')


if __name__ == '__main__':
    rc = 0
    try:
        main()
    except Exception as e:
        print(repr(e), flush=True)
        rc = 1
    (root/'build.exit').write_text(str(rc)+'\n')
    sys.exit(rc)
