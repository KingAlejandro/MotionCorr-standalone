#!/usr/bin/env python3
"""One detached host-only build/check attempt in fresh task-owned scratch.

SPDX-License-Identifier: GPL-2.0-or-later
Invocation: python3 run_remote.py SCRATCH EXPECTED_ARCHIVE_SHA256 SOURCE_COMMIT
No retry, GPU work, installs, shared-tree writes or foreign process control.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import traceback

scratch = Path(sys.argv[1]).resolve()
logs = scratch/'receipts'
logs.mkdir(exist_ok=True)
commands = []
locks = []


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(name, data):
    (logs/name).write_text(json.dumps(data, indent=2)+'\n')


def run(name, argv, expected=0, cwd=None, input=None):
    begin = utc()
    with (logs/(name+'.stdout')).open('w') as out, (logs/(name+'.stderr')).open('w') as err:
        r = subprocess.run([str(x) for x in argv], cwd=cwd, input=input, text=True, stdout=out, stderr=err)
    commands.append(dict(name=name, argv=[str(x) for x in argv], cwd=str(cwd or Path.cwd()),
                         start=begin, end=utc(), exit=r.returncode, expected=expected,
                         affinity=sorted(os.sched_getaffinity(0))))
    save('commands.json', commands)
    if expected is not None and r.returncode != expected:
        raise RuntimeError(f'{name}: exit {r.returncode}, expected {expected}')
    return r.returncode


def acquire(path):
    f = open(path, 'a+')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        run('busy-lock-owners', ['lslocks','--notruncate','-o','PID,COMMAND,PATH'], expected=None)
        save('lock-busy.json', dict(path=path, utc=utc(), status='UNRUN', reason='nonblocking lock busy'))
        f.close()
        raise SystemExit(75)
    locks.append(f)
    save('locks.json', dict(utc=utc(), held=[x.name for x in locks], pid=os.getpid()))
    return f


def main():
    assert os.sched_getaffinity(0) == {8,9}, 'launch must be taskset -c 8-9'
    save('driver-start.json', dict(pid=os.getpid(), ppid=os.getppid(), utc=utc(), argv=sys.argv,
                                   affinity=sorted(os.sched_getaffinity(0))))
    acquire('/tmp/motioncorr-fit-boundary-cpu8-9.lock')
    run('hostname', ['hostname'])
    run('occupancy', ['ps','-u','alex','-o','pid,ppid,psr,pcpu,comm,args','--sort=-pcpu'])
    run('lock-owners', ['lslocks','--notruncate','-o','PID,COMMAND,PATH'])
    run('disk', ['df','-h',str(scratch)])
    # Read-only hardware receipt, no CUDA context or GPU allocation.
    run('gpu-health', ['nvidia-smi','--query-gpu=index,uuid,name,memory.used,ecc.errors.uncorrected.volatile.total','--format=csv'])
    run('gpu-apps', ['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv'])
    run('compiler', ['g++','--version'])
    run('cmake-version', ['cmake','--version'])
    run('python-version', [sys.executable,'-c','import sys,numpy; print(sys.version); print(numpy.__version__)'])
    archive = scratch/'source.tar'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sys.argv[2]
    src=scratch/'source'; src.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(src, filter='data')
    save('source.json', dict(commit=sys.argv[3], archive_sha256=sys.argv[2],
                            files={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(src.rglob('*')) if p.is_file()}))
    build=scratch/'build'
    build_lock=acquire('/tmp/motioncorr-build.lock')
    run('configure', ['cmake','-S',src,'-B',build,'-DCMAKE_BUILD_TYPE=Release','-DCUDA=OFF',
                      '-DUSE_NVCOMP=OFF','-DBUILD_TESTING=ON','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                      '-DPython3_EXECUTABLE='+sys.executable])
    run('build', ['cmake','--build',build,'--parallel','2','--target','runner_numerics','motioncorr'])
    fcntl.flock(build_lock, fcntl.LOCK_UN); build_lock.close(); locks.remove(build_lock)
    save('build-lock-release.json', dict(utc=utc(), pid=os.getpid()))
    os.sched_setaffinity(0,{8})
    binary=build/'runner_numerics'
    save('binaries.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (binary,build/'motioncorr')})
    for name in ['CMakeCache.txt','compile_commands.json','fit_boundary_adapter.cpp']:
        (logs/name).write_bytes((build/name).read_bytes())
    run('linked-libraries', ['ldd',binary])
    run('collection', ['ctest','--test-dir',build,'--show-only=json-v1'])
    run('declared-required-collection', [sys.executable,
        src/'docs/post_rc0/s1/fit_boundary_20261022/check_registration.py',src,build,logs])
    # Check real runnable commands for the four newly required registrations.
    # Unrelated C++ helpers are deliberately unbuilt by this focused lane.
    names=['RunnerFitBoundary','RunnerFitBoundaryMutant_sign',
           'RunnerFitBoundaryMutant_axis-normalization','RunnerFitBoundaryMutant_frame-origin']
    focused=dict(tests=[t for t in json.loads((logs/'collection.stdout').read_text())['tests'] if t['name'] in names])
    run('focused-runnable-collection', [sys.executable,src/'tools/validate_test_collection.py',
        '--min-count','4','--required-tests',*names],input=json.dumps(focused))
    run('focused-ctest', ['ctest','--test-dir',build,'--output-on-failure','-j','1','--output-junit',logs/'focused.xml',
        '-R','^(RunnerFitBoundary.*|RunnerInterpolateRecenter|RunnerInterpolateShifts|MicrographModelBounds|RunnerModelParser)$'])
    run('oracle-direct', [binary,'fit_boundary'])
    for mutation in ['sign','axis-normalization','frame-origin']:
        run('mutant-direct-'+mutation,[binary,'fit_boundary',mutation],expected=1)
        assert (logs/('mutant-direct-'+mutation+'.stdout')).read_text().count('ORACLE REJECT ') == 7
    run('ci-drop-one-controls', [sys.executable,'-m','unittest',
        'tools.test_ci_fail_closed.TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails'],cwd=src)
    save('result.json', dict(status='PASS', utc=utc(), claim='focused native HOST oracle only; no GPU/science/performance qualification'))


exit_code=1
try:
    main()
    exit_code=0
except SystemExit as e:
    exit_code=int(e.code)
except Exception:
    (logs/'exception.txt').write_text(traceback.format_exc())
finally:
    for f in locks:
        fcntl.flock(f, fcntl.LOCK_UN); f.close()
    save('release.json', dict(utc=utc(), pid=os.getpid(), exit=exit_code, locks_released=True))
    (scratch/'driver.exit').write_text(str(exit_code)+'\n')
sys.exit(exit_code)
