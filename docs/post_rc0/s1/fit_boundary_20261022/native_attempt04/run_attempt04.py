#!/usr/bin/env python3
"""Single fresh Release CPU build and bounded host qualification attempt04.

SPDX-License-Identifier: GPL-2.0-or-later
No GPU query, retry, old-output write or production numerical changes.
"""
import datetime
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import traceback
import xml.etree.ElementTree as ET

scratch = Path(sys.argv[1]).resolve()
logs = scratch/'receipts'
logs.mkdir()
commands, locks = [], []
names = ['RunnerFitBoundary', 'RunnerFitBoundaryMutant_sign',
         'RunnerFitBoundaryMutant_axis-normalization', 'RunnerFitBoundaryMutant_frame-origin',
         'RunnerInterpolateRecenter', 'RunnerInterpolateShifts', 'MicrographModelBounds', 'RunnerModelParser']


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    (logs/name).write_text(json.dumps(data, indent=2)+'\n')


def run(name, argv, expected=0, cwd=None, input=None):
    start = utc()
    with (logs/(name+'.stdout')).open('w') as out, (logs/(name+'.stderr')).open('w') as err:
        result = subprocess.run(list(map(str, argv)), cwd=cwd or scratch, input=input,
                                text=True, stdout=out, stderr=err)
    commands.append(dict(name=name, argv=list(map(str, argv)), cwd=str(cwd or scratch),
                         start=start, end=utc(), exit=result.returncode, expected=expected,
                         affinity=sorted(os.sched_getaffinity(0))))
    save('commands.json', commands)
    if result.returncode != expected:
        raise RuntimeError(f'{name}: exit {result.returncode}, expected {expected}')


def acquire(path):
    file = open(path, 'a+')
    try:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        file.close()
        save('lock-busy.json', dict(path=path, utc=utc(), status='UNRUN'))
        raise SystemExit(75)
    locks.append(file)
    save('locks.json', dict(pid=os.getpid(), utc=utc(), held=[f.name for f in locks]))
    return file


def main():
    assert os.sched_getaffinity(0) == {8, 9}
    save('driver-start.json', dict(pid=os.getpid(), utc=utc(), argv=sys.argv,
                                  affinity=sorted(os.sched_getaffinity(0))))
    acquire('/tmp/motioncorr-fit-boundary-cpu8-9.lock')
    common = acquire('/tmp/motioncorr-build.lock')
    run('hostname', ['hostname'])
    run('occupancy', ['ps', '-u', 'alex', '-o', 'pid,ppid,psr,pcpu,comm,args', '--sort=-pcpu'])
    save('resources.json', dict(utc=utc(), meminfo=Path('/proc/meminfo').read_text(),
                               scratch_bytes=shutil.disk_usage(scratch)._asdict()))
    assert shutil.disk_usage(scratch).free > 5*1024**3
    archive = scratch/'source.tar'
    assert digest(archive) == sys.argv[2]
    src = scratch/'source'
    src.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(src, filter='data')
    source_hashes = {str(p.relative_to(src)): digest(p) for p in sorted(src.rglob('*')) if p.is_file()}
    save('source.json', dict(commit=sys.argv[3], archive_sha256=sys.argv[2], files=source_hashes))
    run('axis-static-control', [sys.executable,
        src/'docs/post_rc0/s1/fit_boundary_20261022/native_attempt04/check_axis_boundary.py',
        src/'tests/test_runner_numerics.cpp'])
    run('compiler', ['g++', '--version'])
    run('cmake-version', ['cmake', '--version'])
    run('python-version', [sys.executable, '-c', 'import sys,numpy; print(sys.version); print(numpy.__version__)'])
    build = scratch/'build'
    run('configure', ['cmake', '-S', src, '-B', build, '-DCMAKE_BUILD_TYPE=Release', '-DCUDA=OFF',
        '-DUSE_NVCOMP=OFF', '-DBUILD_TESTING=ON', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
        '-DPython3_EXECUTABLE='+sys.executable])
    assert digest(build/'fit_boundary_adapter.cpp') == 'd44dbbb1b9ebfc4af20788993466f945201b2c37864de819cbe818163366680f', 'generated adapter changed'
    run('build', ['cmake', '--build', build, '--parallel', '2', '--target', 'runner_numerics', 'motioncorr'])
    save('build-identity.json', dict(status='PASS', utc=utc(), fresh_compile=True,
        source_commit=sys.argv[3], binaries={name: digest(build/name) for name in ['runner_numerics', 'motioncorr']},
        test_source_sha256=digest(src/'tests/test_runner_numerics.cpp'),
        build_file_hashes={str(p.relative_to(build)): digest(p) for p in sorted(build.rglob('*'))
            if p.is_file() and (p.suffix in ['.o', '.a'] or p.name in ['runner_numerics', 'motioncorr',
                'fit_boundary_adapter.cpp', 'compile_commands.json', 'CMakeCache.txt', 'link.txt', 'flags.make'])},
        dependency_files={str(p.relative_to(build)): p.read_text() for p in sorted(build.rglob('*.o.d'))}))
    for name in ['CMakeCache.txt', 'compile_commands.json', 'fit_boundary_adapter.cpp']:
        shutil.copyfile(build/name, logs/name)
    fcntl.flock(common, fcntl.LOCK_UN)
    common.close()
    locks.remove(common)
    save('build-lock-release.json', dict(utc=utc(), pid=os.getpid(), reason='fresh CPU build complete'))
    os.sched_setaffinity(0, {8})
    view = build
    run('linked-libraries', ['ldd', build/'runner_numerics'])
    run('collection', ['ctest', '--test-dir', view, '--show-only=json-v1'])
    run('declared-required-collection', [sys.executable,
        src/'docs/post_rc0/s1/fit_boundary_20261022/check_registration.py', src, view, logs])
    collected = json.loads((logs/'collection.stdout').read_text())
    focused = dict(tests=[t for t in collected['tests'] if t['name'] in names])
    (logs/'focused-collection.json').write_text(json.dumps(focused, indent=2)+'\n')
    validator = src/'tools/validate_test_collection.py'
    run('focused-runnable-collection', [sys.executable, validator, '--min-count', '8',
        '--required-tests', *names], input=json.dumps(focused))
    for missing in names[:4]:
        dropped = dict(tests=[t for t in focused['tests'] if t['name'] != missing])
        label = 'runnable-drop-'+missing
        run(label, [sys.executable, validator, '--min-count', '7', '--required-tests', *names],
            input=json.dumps(dropped), expected=1)
        assert 'Missing required test(s): '+missing in (logs/(label+'.stdout')).read_text()
    run('focused-ctest', ['ctest', '--test-dir', view, '--output-on-failure', '-j', '1',
        '--no-tests=error', '--output-junit', logs/'focused.xml',
        '-R', '^(RunnerFitBoundary.*|RunnerInterpolateRecenter|RunnerInterpolateShifts|MicrographModelBounds|RunnerModelParser)$'])
    cases = ET.parse(logs/'focused.xml').getroot().findall('.//testcase')
    assert len(cases) == 8 and {c.attrib['name'] for c in cases} == set(names)
    assert all(c.find('failure') is None and c.find('skipped') is None and c.find('error') is None for c in cases)
    binary = build/'runner_numerics'
    run('oracle-direct', [binary, 'fit_boundary'])
    assert (logs/'oracle-direct.stdout').read_text().count('PASS ') == 7
    for mutation in ['sign', 'axis-normalization', 'frame-origin']:
        label = 'mutant-direct-'+mutation
        run(label, [binary, 'fit_boundary', mutation], expected=1)
        assert (logs/(label+'.stdout')).read_text().count('ORACLE REJECT ') == 7
        assert not (logs/(label+'.stderr')).read_text(), 'mutant runtime/admission exception'
    # The new query mutant must leave the fitted subject identical. Compare
    # actual native rows, not a second design-matrix/SVD implementation.
    def rows(name, prefix):
        result = {}
        for line in (logs/name).read_text().splitlines():
            if line.startswith(prefix):
                tokens = line.split()
                case = tokens[1 if prefix == 'PASS ' else 2]
                result[case] = dict(re.findall(r'([a-z_]+)=([^ ]+)', line))
        assert len(result) == 7
        return result
    baseline = rows('oracle-direct.stdout', 'PASS ')
    axis = rows('mutant-direct-axis-normalization.stdout', 'ORACLE REJECT ')
    for case in baseline:
        for key in ['n', 'rank', 'condition', 'coefficient_max_abs_px']:
            assert baseline[case][key] == axis[case][key], 'axis changed native fit '+case+' '+key
        assert float(axis[case]['coefficient_max_abs_px']) <= 1e-7
        assert float(axis[case]['field_oracle_max_px']) > 2e-5
    save('axis-fit-invariance.json', dict(status='PASS', cases=7, baseline=baseline, axis=axis,
        scope='identical native observation count/rank/condition/coefficient error; changed query field only'))
    run('ci-drop-one-controls', [sys.executable, '-m', 'unittest',
        'tools.test_ci_fail_closed.TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails'], cwd=src)
    save('result.json', dict(status='PASS', utc=utc(),
        claim='focused native HOST oracle; fresh attempt04 CPU build and query-boundary normalization mutant; no GPU/science/performance qualification'))


exit_code = 1
try:
    main()
    exit_code = 0
except SystemExit as error:
    exit_code = int(error.code)
except Exception:
    (logs/'exception.txt').write_text(traceback.format_exc())
finally:
    for file in locks:
        fcntl.flock(file, fcntl.LOCK_UN)
        file.close()
    save('release.json', dict(utc=utc(), pid=os.getpid(), exit=exit_code, locks_released=True))
    (scratch/'driver.exit').write_text(str(exit_code)+'\n')
sys.exit(exit_code)
