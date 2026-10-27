"""Fresh admission receipt under the cpu64 lane: leases, CPUs 32-47, no foreign heavy process on the lane mask, memory, disk, scratch cap.
Usage: guard.py ROOT LABEL   (receipts only; derived from the reviewed build/tests guard of the earlier capture campaign)"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
root, label = Path(sys.argv[1]), sys.argv[2]
assert sorted(os.sched_getaffinity(0)) == list(range(32, 48)), 'affinity is not CPUs 32-47'
locks = json.loads(os.environ['MOTIONCORR_HELD_LEASES']); assert '/tmp/motioncorr-cpu64-bench.lock' in locks and len(locks) >= 8, locks
(root / 'receipts').mkdir(exist_ok=True)
out = subprocess.check_output(['ps', '-eo', 'pid,ppid,psr,pcpu,args', '--sort=-pcpu'], text=True)
(root / 'receipts' / f'{label}-occupancy.txt').write_text(out)
rows = [l.split(None, 4) for l in out.splitlines()[1:]]; own = {os.getpid(), os.getppid()}
while True:
    n = len(own); own.update(int(r[0]) for r in rows if len(r) == 5 and int(r[1]) in own)
    if len(own) == n: break
for r in rows:
    if len(r) != 5 or int(r[0]) in own or float(r[3]) < 50: continue
    try: mask = os.sched_getaffinity(int(r[0]))
    except ProcessLookupError: continue
    if mask & set(range(32, 48)): raise SystemExit('foreign heavy process overlapping lane: ' + ' '.join(r))
def size(p):
    return sum(f.stat().st_size for f in Path(p).rglob('*') if f.is_file() and not f.is_symlink())
cap_roots = ['/tmp/motioncorr-b2-native-20261026', '/tmp/motioncorr-b2-factorial-20261026', '/tmp/motioncorr-lfw-v5-20261026', '/tmp/motioncorr-local-ccf-20261026', '/tmp/mc-w8-common-mean-screen-20261026', str(root)]
sizes = {r: size(r) for r in cap_roots if Path(r).exists()}
used = sum(sizes.values()); mem = {l.split(':')[0]: int(l.split()[1]) * 1024 for l in Path('/proc/meminfo').read_text().splitlines()}
free = shutil.disk_usage(root).free
assert used < 25 * 1024 ** 3 and free > 3 * 1024 ** 3 and mem['MemAvailable'] > 4 * 1024 ** 3, (used, free, mem['MemAvailable'])
(root / 'receipts' / f'{label}-admission.json').write_text(json.dumps(dict(
    utc=time.strftime('%FT%TZ', time.gmtime()), label=label, locks=locks, affinity=sorted(os.sched_getaffinity(0)), build_jobs=2, omp_threads=2, blas_threads=1,
    cap_namespace_bytes=sizes, combined_scratch_bytes=used, cap_bytes=25 * 1024 ** 3, disk_free_bytes=free, mem_available_bytes=mem['MemAvailable'],
    assessment='no foreign >=50% process with an overlapping allowed mask at this admission; receipt only, no timing claim'), indent=2) + '\n')
print('guard ok', label, 'scratch', used)
