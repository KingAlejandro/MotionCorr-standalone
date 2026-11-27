"""One bounded remote nonnumerical probe; driver bytes arrive as JSON on stdin.

Run only under the separately frozen intent. Never invoke a RELION executable.
"""
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def inspect(argv):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    return {'argv': argv, 'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}


payload = json.load(sys.stdin)
assert set(os.sched_getaffinity(0)) == {14, 15}
assert os.environ['CUDA_VISIBLE_DEVICES'] == ''
root = Path(tempfile.mkdtemp(prefix='mc-i61-review-isolation-', dir='/mnt/clathrin'))
print('PROBE_SCRATCH', root, flush=True)
for name in ('sources', 'home', 'tmp', 'container_work', 'output'):
    (root/name).mkdir()
driver = root/'sources/run_pilot.py'
driver.write_text(payload['driver'])
assert hashlib.sha256(driver.read_bytes()).hexdigest() == payload['driver_sha256']
fixture = root/'sources/fixture.txt'
fixture.write_text('disposable read-only fixture\n')
spec = importlib.util.spec_from_file_location('pilot', driver)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

result = {'utc': datetime.now(timezone.utc).isoformat(), 'root': str(root),
          'driver_sha256': payload['driver_sha256'], 'status': 'FAIL',
          'affinity': sorted(os.sched_getaffinity(0)), 'numerical_launches': 0}
try:
    with open('/tmp/motioncorr-i61-cpu-14-15.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result['occupancy'] = inspect(['ps', '-eo', 'pid,psr,pcpu,comm', '--sort=-pcpu'])
        result['gpu_processes_readonly'] = inspect(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,process_name', '--format=csv,noheader'])
        result['runtime'] = inspect([str(p.executable('apptainer')), '--version'])
        result['runtime_help'] = inspect([str(p.executable('apptainer')), 'exec', '--help'])
        assert result['runtime']['exit'] == result['runtime_help']['exit'] == 0
        assert result['runtime']['stdout'].strip() == p.RUNTIME_VERSION
        for flag in ('--contain', '--home', '--workdir', '--no-mount', '--pwd'):
            assert flag in result['runtime_help']['stdout']
        result['runtime_identity'] = p.identity(p.executable('apptainer'))
        result['wrapper_sha256'] = p.digest(p.RUNNER)
        result['image_stat'] = {'path': str(p.IMAGE), 'size': p.IMAGE.stat().st_size,
                                'mtime_ns': p.IMAGE.stat().st_mtime_ns}
        result['config'] = Path('/etc/singularity/singularity.conf').read_text()
        script = '''
printf 'ENV_HOME=%s\nENV_TMPDIR=%s\nENV_CUDA=%s\n' "$HOME" "$TMPDIR" "$CUDA_VISIBLE_DEVICES"
test "$CUDA_VISIBLE_DEVICES" = ''
test "$OMP_NUM_THREADS" = 1
test "$OPENBLAS_NUM_THREADS" = 1
test "$MKL_NUM_THREADS" = 1
test "$VECLIB_MAXIMUM_THREADS" = 1
test "$NUMEXPR_NUM_THREADS" = 1
test "$BLIS_NUM_THREADS" = 1
printf 'CWD=%s\n' "$PWD"
grep Cpus_allowed_list /proc/self/status
printf 'MOUNTINFO_BEGIN\n'
cat /proc/self/mountinfo
printf 'MOUNTINFO_END\n'
test -z "$(find /dev -name 'nvidia*' -print -quit)"
printf 'output\n' > "$1/output/write.txt"
printf 'home\n' > "$HOME/write.txt"
printf 'tmpdir\n' > "$TMPDIR/write.txt"
printf 'tmp\n' > /tmp/i61-review-write.txt
printf 'vartmp\n' > /var/tmp/i61-review-write.txt
if (printf 'must not write\n' > "$1/sources/fixture.txt") 2> "$1/output/ro_error.txt"; then
    echo 'READONLY_FIXTURE_WRITABLE'; exit 42
fi
printf 'BINARY_HASHES_BEGIN\n'
/usr/bin/sha256sum /opt/relion/bin/relion_reconstruct /opt/relion/bin/relion_postprocess
printf 'BINARY_HASHES_END\n'
'''
        cmd = p.container_argv(root, p.executable('apptainer'), ['/bin/sh', '-ec', script, 'probe', str(root)])
        env = p.environment(root)
        save(root/'INTENT.json', {'argv': cmd, 'environment': env, 'driver_sha256': payload['driver_sha256'],
                                 'one_container_invocation': True, 'timeout_seconds': 45})
        # Exactly one container subprocess. No retries, reconstruction, postprocess,
        # help/version call to RELION, analyser, GPU binding or historical write.
        r = subprocess.run(cmd, cwd=p.PROJECT, env=env, capture_output=True, text=True, timeout=45)
        result['container'] = {'argv': cmd, 'exit': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
        assert r.returncode == 0 and not r.stderr, result['container']
        assert 'ENV_HOME='+str(root/'home')+'\n' in r.stdout
        assert 'ENV_TMPDIR='+str(root/'tmp')+'\n' in r.stdout
        assert 'CWD='+str(p.PROJECT)+'\n' in r.stdout
        assert 'Cpus_allowed_list:\t14-15\n' in r.stdout
        mounts = r.stdout.split('MOUNTINFO_BEGIN\n', 1)[1].split('MOUNTINFO_END\n', 1)[0].splitlines()
        entries = [line.split() for line in mounts]

        def mount_for(path):
            matches = [e for e in entries if path == Path(e[4]) or path.is_relative_to(Path(e[4]))]
            return max(matches, key=lambda e: len(e[4]))

        for path in (p.HISTORY, p.PROJECT, p.PLAN.parent, root/'sources'):
            entry = mount_for(path)
            assert 'ro' in entry[5].split(','), (path, entry)
        for path in (root/'output', root/'home', Path('/tmp'), Path('/var/tmp')):
            entry = mount_for(path)
            assert 'rw' in entry[5].split(','), (path, entry)
        for path in (Path('/home/alex'), Path('/mnt/clathrin')):
            assert mount_for(path)[4] == '/', (path, mount_for(path))
        assert fixture.read_text() == 'disposable read-only fixture\n'
        assert (root/'output/ro_error.txt').read_text().strip()
        for name in ('output/write.txt', 'home/write.txt', 'tmp/write.txt',
                     'container_work/tmp/i61-review-write.txt', 'container_work/var_tmp/i61-review-write.txt'):
            assert (root/name).is_file(), name
        hashes = r.stdout.split('BINARY_HASHES_BEGIN\n', 1)[1].split('BINARY_HASHES_END\n', 1)[0]
        assert {line.split()[1]: line.split()[0] for line in hashes.splitlines()} == p.INTERNAL_BINARIES
        result['verified_mounts'] = {str(path): mount_for(path) for path in
            (p.HISTORY, p.PROJECT, p.PLAN.parent, root/'sources', root/'output', root/'home', Path('/tmp'), Path('/var/tmp'))}
        result['ro_fixture_error'] = (root/'output/ro_error.txt').read_text()
        result['status'] = 'PASS'
except BaseException as exc:
    result['error'] = repr(exc)
finally:
    result['end_utc'] = datetime.now(timezone.utc).isoformat()
    save(root/'RESULT.json', result)
    print(json.dumps(result), flush=True)
if result['status'] != 'PASS':
    raise SystemExit(1)
