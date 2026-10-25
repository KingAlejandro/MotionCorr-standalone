#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Once-only cpu64 runner for w4-matched-native/v1. Copied from the W4 protocol runner r3
(sha256 6c36b38f…89b3): same locks, occupancy, caps and fail-stop/no-retry rule; one job.

usage (input tar on stdin): taskset -c 62 python3 -I -B run_matched_once.py NEW_NAMESPACE INPUT_TAR_SHA256
"""
import fcntl, hashlib, json, os, pathlib, resource, subprocess, sys, tarfile, time

phase, n, pin = 'M', pathlib.Path(sys.argv[1]), sys.argv[2]
fds = []
for s in ['/tmp/motioncorr-cpu64-bench.lock', '/tmp/motioncorr-w4-analysis-cpu62.lock']:
    f = os.open(s, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o666)
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); fds.append(f)
aff = os.sched_getaffinity(0)
assert aff == {62}, aff
cpu = f'cpu{next(iter(aff))} '


def sample():
    a = next(x for x in pathlib.Path('/proc/stat').read_text().splitlines() if x.startswith(cpu))
    v = list(map(int, a.split()[1:]))[:8]
    return sum(v), v[3] + v[4]


a = sample(); time.sleep(3); b = sample(); busy = 1 - (b[1] - a[1]) / (b[0] - a[0]); assert busy < .5, busy
m = {x.split(':')[0]: x.split(':')[1].strip() for x in pathlib.Path('/proc/meminfo').read_text().splitlines()}
assert int(m['MemAvailable'].split()[0]) > 2 * 1024 * 1024
assert os.statvfs('/tmp').f_bavail * os.statvfs('/tmp').f_frsize > 100 << 20
n.mkdir()  # must not exist
data = sys.stdin.buffer.read(); assert hashlib.sha256(data).hexdigest() == pin
p = n / 'input.tar'; p.write_bytes(data)
with tarfile.open(p) as t:
    assert all(x.isfile() and '..' not in pathlib.PurePosixPath(x.name).parts and not pathlib.PurePosixPath(x.name).is_absolute()
               and not pathlib.PurePosixPath(x.name).name.startswith('._') for x in t.getmembers())
    t.extractall(n, filter='data')
(n / 'out').mkdir()
env = os.environ.copy()
env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30)); resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))
S, O = n / 'scripts', n / 'out'
jobs = [('w4_matched_native', [S / 'w4_matched_native.py', n, O / 'w4_matched_native.json'])]
r = dict(phase=phase, affinity=sorted(aff), cpu_busy_fraction=busy, mem_available=m['MemAvailable'], allocated_ram_cap_bytes=2 << 30,
         disk_cap_bytes=64 << 20, input_sha256=pin, python_exe='/usr/bin/python3', jobs=[], state='RUNNING')
for name, argv in jobs:
    cmd = ['/usr/bin/time', '-v', '-o', str(O / f'{name}.time'), '/usr/bin/python3', '-I', '-B'] + [str(x) for x in argv]
    t0 = time.time(); q = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    r['jobs'].append(dict(name=name, argv=cmd, exit=q.returncode, wall_s=time.time() - t0, stdout=q.stdout[-20000:], stderr=q.stderr[-20000:]))
    (n / 'RESULT.json').write_text(json.dumps(r, indent=2) + '\n')
    if q.returncode:
        r['state'] = 'FAIL_STOP_NO_RETRY'; break
else:
    r['state'] = 'COMPLETE_EXIT0_NEEDS_REVIEW'
r['output_bytes'] = sum(x.stat().st_size for x in n.rglob('*') if x.is_file()); assert r['output_bytes'] < 64 << 20
r['outputs_sha256'] = {str(x.relative_to(n)): hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(O.rglob('*')) if x.is_file()}
(n / 'RESULT.json').write_text(json.dumps(r, indent=2) + '\n'); print(json.dumps(r))
raise SystemExit(0 if r['state'].startswith('COMPLETE') else 1)
