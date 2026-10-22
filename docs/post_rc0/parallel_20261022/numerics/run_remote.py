#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded native correctness run on GPU3 / CPUs10-13; no timing claims."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
src = root/'src'
logs = root/'validation'
logs.mkdir(exist_ok=False)
uuid = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
python = '/home/alex/.mc-venv/bin/python3'
records = []


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(label, argv, expected=0, cwd=None, diagnostic=None):
    print(label, flush=True)
    p = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (logs/(label+'.log')).write_text(p.stdout)
    (logs/(label+'.exit')).write_text(str(p.returncode)+'\n')
    record = dict(label=label, argv=argv, cwd=str(cwd or Path.cwd()), exit=p.returncode,
        expected=expected, utc=stamp(), affinity=sorted(os.sched_getaffinity(0)),
        diagnostic=diagnostic, diagnostic_found=diagnostic is None or diagnostic in p.stdout)
    records.append(record)
    (logs/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    if p.returncode != expected or not record['diagnostic_found']:
        raise RuntimeError(label+' failed')
    return p.stdout


def health(label, require_idle=True):
    g = run(label+'-mapping', ['nvidia-smi','--query-gpu=index,uuid,name,memory.used,utilization.gpu',
        '--format=csv,noheader,nounits'])
    assigned = [r.split(', ') for r in g.strip().splitlines() if uuid in r]
    assert len(assigned)==1 and assigned[0][0]=='3', 'assigned UUID/index changed'
    apps = run(label+'-apps', ['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory',
        '--format=csv,noheader'])
    assert uuid not in apps, 'existing compute app on assigned GPU'
    ecc = run(label+'-ecc',['nvidia-smi','-i',uuid,
        '--query-gpu=ecc.errors.uncorrected.volatile.total','--format=csv,noheader,nounits'])
    assert ecc.strip() == '0', 'nonzero/unavailable uncorrected volatile ECC'
    run(label+'-full',['nvidia-smi','-i',uuid,'-q'])
    if require_idle:
        assert int(assigned[0][4])==0, 'assigned GPU not idle'


def main():
    assert os.sched_getaffinity(0) == {10,11,12,13}
    assert (root/'build.exit').read_text().strip()=='0'
    source_files=json.loads((root/'source-files.json').read_text())
    for name, sha in source_files.items():
        assert digest(src/name)==sha, 'unpacked source hash mismatch: '+name
    (logs/'source-verification.json').write_text(json.dumps(dict(
        utc=stamp(),count=len(source_files),status='PASS',
        manifest_sha256=digest(root/'source-files.json')),indent=2)+'\n')
    binaries=json.loads((root/'logs/binary-hashes.json').read_text())
    for name, sha in binaries.items():
        assert digest(root/name)==sha, 'binary hash mismatch: '+name
    for key in list(os.environ):
        if key.startswith('MC_DIAG_'):
            del os.environ[key]
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
        NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES=uuid, CUDA_DEVICE_ORDER='PCI_BUS_ID')
    os.environ['LD_LIBRARY_PATH']='/usr/local/cuda-12.8/lib64'
    (logs/'environment.json').write_text(json.dumps(dict(
        utc=stamp(),pid=os.getpid(),gpu_uuid=uuid,affinity=sorted(os.sched_getaffinity(0)),
        env={k:v for k,v in os.environ.items() if k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
             'CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER','LD_LIBRARY_PATH'] or k.startswith('MC_DIAG_')},
        driver_sha256=digest(Path(__file__)),source_archive_sha256=digest(root/'source.tar.gz')),indent=2)+'\n')
    run('host-identity',['uname','-a'])
    run('compiler-identity',['c++','--version'])
    run('cmake-identity',['cmake','--version'])
    nvcomp=Path('/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive')
    assert (nvcomp/'include/nvcomp/deflate.h').is_file() and (nvcomp/'lib/libnvcomp.so').is_file()
    (logs/'nvcomp-discovery.json').write_text(json.dumps(dict(
        NVCOMP_ROOT=str(nvcomp),enabled_in_build=False,
        header_sha256=digest(nvcomp/'include/nvcomp/deflate.h'),
        library=str((nvcomp/'lib/libnvcomp.so').resolve()),
        library_sha256=digest(nvcomp/'lib/libnvcomp.so')),indent=2)+'\n')
    host_re = '^(HermitianProjectionOracle|PeakFitArithmetic.*|RealspaceBorderValidation)$'
    native_re = '^Cuda(Hermitian(Inverse|Oracle|CCF).*|PeakFit.*|RealspaceBorderBranch.*)$'
    expected_native = {
        'CudaHermitianInverse','CudaHermitianInverseMutant_no_projection',
        'CudaHermitianInverseMutant_wrapper_no_projection','CudaHermitianInverseMutant_dose_no_projection',
        'CudaHermitianOracleMutant_oracle_session_no_projection',
        'CudaHermitianOracleMutant_oracle_session_zero_boundary',
        'CudaHermitianOracleMutant_oracle_wrapper_zero_boundary',
        'CudaHermitianOracleMutant_oracle_dose_zero_boundary',
        'CudaHermitianCCF','CudaHermitianCCFMutant_ccf_perpatch_no_projection',
        'CudaHermitianCCFMutant_ccf_batched_no_projection','CudaPeakFit',
        'CudaPeakFitMutant_float_denominator','CudaRealspaceBorderBranch',
        'CudaRealspaceBorderBranchMutant_x_float','CudaRealspaceBorderBranchMutant_y_float'}
    for kind in ['cpu','cuda']:
        b=root/('build-'+kind)
        inventory=json.loads(run('inventory-'+kind,['ctest','--test-dir',str(b),'--show-only=json-v1',
                            '-R', host_re if kind=='cpu' else native_re]))
        selected={t['name'] for t in inventory['tests']}
        if kind=='cuda':
            assert selected==expected_native, (selected^expected_native)
        else:
            assert len(selected)==6
        for t in inventory['tests']:
            assert t.get('command') and Path(t['command'][0]).is_file(), t
    run('host-ctest',['ctest','--test-dir',str(root/'build-cpu'),'-R',host_re,'-j','1','-V',
        '--output-on-failure','--output-junit',str(logs/'host-junit.xml')])
    run('generate-fixtures',[python,str(src/'test-data/generate_motion_diagnostics.py'),
                            '--outdir',str(root/'v2fixtures')])
    manifest=json.loads((root/'v2fixtures/MANIFEST.json').read_text())
    for case in manifest['cases'].values():
        for name, sha in case['files'].items():
            assert digest(root/'v2fixtures'/name)==sha
    # Nonblocking canonical correctness lock; probe and release benchmark lock.
    with open('/tmp/motioncorr-gpu3-correctness.lock','a') as gpu_lock:
        fcntl.flock(gpu_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with open('/tmp/motioncorr-bench.lock','a') as bench_lock:
            fcntl.flock(bench_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(bench_lock,fcntl.LOCK_UN)
        (logs/'locks.json').write_text(json.dumps(dict(utc=stamp(),pid=os.getpid(),
            canonical_gpu_lock=gpu_lock.name,canonical_gpu_lock_mode='exclusive nonblocking held across run and healthcheck',
            benchmark_lock_probe='/tmp/motioncorr-bench.lock: exclusive nonblocking acquired then released',
            no_timing_claim=True),indent=2)+'\n')
        health('preflight')
        try:
            run('native-ctest',['ctest','--test-dir',str(root/'build-cuda'),'-R',native_re,
                '-j','1','-V','--output-on-failure','--output-junit',str(logs/'native-junit.xml')])
            health('after-ctest',require_idle=False)
            raw = [('cuda_hermitian_inverse_no_projection','INVARIANT FAIL'),
                   ('cuda_hermitian_inverse_wrapper_no_projection','INVARIANT FAIL'),
                   ('cuda_hermitian_inverse_dose_no_projection','INVARIANT FAIL'),
                   ('cuda_patch_batch_ccf_perpatch_no_projection','INVARIANT FAIL'),
                   ('cuda_patch_batch_ccf_batched_no_projection','INVARIANT FAIL'),
                   ('cuda_peak_fit_float_denominator','exact-rounded-zero'),
                   ('cuda_realspace_border_branch_x_float','FAIL:'),
                   ('cuda_realspace_border_branch_y_float','FAIL:')]
            for name, diagnostic in raw:
                run('raw-'+name,[str(root/'build-cuda'/name)],expected=1,diagnostic=diagnostic)
                health('after-'+name,require_idle=False)
            # Match the documented #267 argv, with only --j reduced to 1 for the
            # assigned allocation. Existing max_iter=5, ROI and gates stay fixed.
            for backend in ['cpu','cuda']:
                out=root/('cases-'+backend);out.mkdir(exist_ok=False)
                rows=[]
                for case in manifest['cases']:
                    for info in manifest['cases'].values():
                        for name, sha in info['files'].items():
                            assert digest(root/'v2fixtures'/name)==sha
                    p=3 if case in ['affine','pedestal','noisy'] else 1
                    binary=root/('build-'+backend)/'motioncorr'
                    argv=['taskset','-c','10-13',str(binary),'--i',case+'.star','--o',str(out/case),
                        '--use_own','--j','1','--patch_x',str(p),'--patch_y',str(p),'--bin_factor','1',
                        '--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1',
                        '--last_frame_sum','5','--skip_logfile']
                    if backend=='cuda':
                        health('before-case-'+case,require_idle=False)
                        argv+=['--gpu','0']
                    run('case-'+backend+'-'+case,argv,cwd=root/'v2fixtures')
                    row=dict(case=case,backend=backend,dc='unset',patches=p,argv=argv,exit=0,
                        gpu_uuid=uuid if backend=='cuda' else None,binary_sha256=digest(binary),
                        utc=stamp(),runtime_threads=1)
                    rows.append(row)
                    (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
                    if backend=='cuda':
                        health('after-case-'+case,require_idle=False)
                run('evaluate-'+backend,[python,str(src/'docs/post_rc0/s1/synth_combined/eval_v2.py'),
                    str(root/'v2fixtures'),str(out),str(logs/('evaluation-'+backend+'.json'))])
        finally:
            health('final-health',require_idle=False)
    (root/'validation.done').write_text('0\n')


rc=0
try:
    main()
except Exception as exc:
    print(repr(exc),flush=True)
    rc=1
(root/'validation.exit').write_text(str(rc)+'\n')
sys.exit(rc)
