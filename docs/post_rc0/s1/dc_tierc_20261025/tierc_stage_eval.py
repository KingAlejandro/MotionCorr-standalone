#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage, hash-verify and evaluate one batch of exit-0 Tier C records on cpu64.

usage: tierc_stage_eval.py {fetch-src|stage|evaluate|cleanup} WORK INVENTORY.json [BATCH]

fetch-src  copy and hash-check the frozen experiment source archive (needed by the evaluator).
stage      stream the batch's pinned files from the campaign host into a NEW ROOT, verify every
           byte against the RUN.json pins/inventory, reject extra/missing/linked files.
evaluate   run the unchanged deployed evaluate.py (SHA-pinned) as `evaluate.py C ROOT` exactly once
           per batch (one-shot marker), under the caller's CPU affinity and flock.
cleanup    keep eval output and the small provenance files, delete the staged payload.

The evaluator is not modified: Tier C reads only ROOT/runs and ROOT/src, so no path amendment is needed.
"""
import hashlib, json, os, resource, subprocess, sys, tarfile, time
from pathlib import Path

REMOTE = 'alex@130.246.80.58'
REMOTE_ROOT = '/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b'
REMOTE_CPUS = '104-107'
SRC_TAR_SHA = 'b7152c0adc2b0ee8c4387169786096b8cc660bfb96c9f880069a5893bb18d49c'
EVALUATOR = Path(__file__).resolve().parent.parent / 'dc_factorial_20261022' / 'tools' / 'evaluate.py'
EVALUATOR_SHA = 'dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d'
SMALL = ('RUN.json', 'runtime.json', 'witness.txt')


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def load(inv_path, batch):
    inv = json.loads(Path(inv_path).read_text())
    cfgs = set(inv['batches'][batch]['configs'])
    return inv, [r for r in inv['records'] if r['config'] in cfgs]


def verify_tree(runs_dir, recs):
    """Exact-set + byte verification. Raises on any extra, missing, linked, resized or rehashed file."""
    expected = {f"{r['id']}/{f['rel']}": f for r in recs for f in r['files']}
    actual = set()
    for p in Path(runs_dir).rglob('*'):
        if p.is_symlink(): raise ValueError(f'symlink in stage: {p}')
        if p.is_file(): actual.add(p.relative_to(runs_dir).as_posix())
    if actual != set(expected):
        raise ValueError(f'file set differs: extra={sorted(actual - set(expected))[:5]} missing={sorted(set(expected) - actual)[:5]}')
    for rel, f in expected.items():
        p = Path(runs_dir) / rel
        if p.stat().st_size != f['bytes']: raise ValueError(f'size mismatch: {rel}')
        if sha256_file(p) != f['sha256']: raise ValueError(f'sha256 mismatch: {rel}')
    for r in recs:
        run = json.loads((Path(runs_dir) / r['id'] / 'RUN.json').read_text())
        if (run['id'], run['tier'], run['exit'], run['source_sha']) != (r['id'], 'C', 0, '3eee0a4b4e367f9b57f950c440c89679a5ec9c93'):
            raise ValueError(f"RUN identity/exit/source mismatch: {r['id']}")
    return len(expected)


def busy_fraction(cpus, seconds=3):
    def snap():
        out = {}
        for line in Path('/proc/stat').read_text().splitlines():
            t = line.split()
            if t[0].startswith('cpu') and t[0] != 'cpu' and int(t[0][3:]) in cpus:
                v = list(map(int, t[1:])); out[int(t[0][3:])] = (sum(v), v[3] + v[4])
        return out
    a = snap(); time.sleep(seconds); b = snap()
    return {c: 1 - (b[c][1] - a[c][1]) / max(b[c][0] - a[c][0], 1) for c in a}


def admission(work, need_bytes):
    aff = sorted(os.sched_getaffinity(0))
    busy = busy_fraction(set(aff))
    st = os.statvfs(work)
    mem = next(int(l.split()[1]) * 1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable'))
    a = dict(captured_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), affinity=aff, max_cpu_busy=max(busy.values()),
             free_bytes=st.f_bavail * st.f_frsize, need_bytes=need_bytes, mem_available_bytes=mem,
             flock_env=os.environ.get('DC_TIERC_FLOCK_HELD'))
    if aff != list(range(32, 48)) or a['flock_env'] != '1': raise SystemExit(f'admission: affinity/flock not as required: {a}')
    if a['max_cpu_busy'] > 0.25: raise SystemExit(f'admission: CPUs 32-47 busy: {a}')
    if a['free_bytes'] < 2 * need_bytes + 20 * 2**30: raise SystemExit(f'admission: not enough free disk: {a}')
    if mem < 32 * 2**30: raise SystemExit(f'admission: low RAM: {a}')
    return a


def cmd_fetch_src(work):
    dst = Path(work) / 'src.tar'
    if not dst.exists():
        with open(dst, 'wb') as out:
            subprocess.run(['ssh', '-o', 'BatchMode=yes', REMOTE, f'taskset -c {REMOTE_CPUS} cat {REMOTE_ROOT}/src.tar'], stdout=out, check=True)
    got = sha256_file(dst)
    if got != SRC_TAR_SHA: raise SystemExit(f'src.tar sha {got} != {SRC_TAR_SHA}')
    print(json.dumps(dict(src_tar=str(dst), sha256=got, bytes=dst.stat().st_size)))


def cmd_stage(work, inv_path, batch):
    inv, recs = load(inv_path, batch)
    root = Path(work) / f'batch{batch}'
    if root.exists(): raise SystemExit(f'{root} exists; stage into a new empty ROOT only')
    adm = admission(work, inv['batches'][batch]['bytes'])
    (root / 'runs').mkdir(parents=True); (root / 'eval').mkdir(); (root / 'src').mkdir()
    names = '\n'.join(f"{r['id']}/{f['rel']}" for r in recs for f in r['files']) + '\n'
    t0 = time.time()
    ssh = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', REMOTE, f'cd {REMOTE_ROOT}/runs && taskset -c {REMOTE_CPUS} tar -cf - --no-recursion -T -'],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    tar = subprocess.Popen(['tar', '-xf', '-', '-C', str(root / 'runs')], stdin=ssh.stdout)
    ssh.stdout.close(); ssh.stdin.write(names.encode()); ssh.stdin.close()
    rc = (ssh.wait(), tar.wait())
    if rc != (0, 0): raise SystemExit(f'transfer failed rc={rc}')
    n = verify_tree(root / 'runs', recs)
    with tarfile.open(Path(work) / 'src.tar') as t: t.extractall(root / 'src', filter='data')
    (root / 'queue-batch-ids.txt').write_text('\n'.join(r['id'] for r in recs) + '\n')
    res = dict(batch=batch, state='STAGED_ALL_HASHES_MATCH', records=len(recs), files=n, bytes=sum(r['stage_bytes'] for r in recs),
               seconds=round(time.time() - t0, 1), admission=adm, src_tar_sha256=SRC_TAR_SHA)
    (Path(work) / f'stage-{batch}.json').write_text(json.dumps(res, indent=1) + '\n')
    print(json.dumps(res))


def cmd_evaluate(work, inv_path, batch):
    inv, recs = load(inv_path, batch)
    root = Path(work) / f'batch{batch}'
    marker = Path(work) / f'evaluate-{batch}.started'
    if marker.exists(): raise SystemExit('one-shot marker exists; this batch was already evaluated')
    if sha256_file(EVALUATOR) != EVALUATOR_SHA: raise SystemExit('evaluator hash drift')
    verify_tree(root / 'runs', recs)  # re-verify immediately before use
    if any((root / 'eval').iterdir()): raise SystemExit('eval dir not empty')
    adm = admission(work, 0 + inv['batches'][batch]['bytes'] // 2)
    marker.write_text(adm['captured_utc'] + '\n')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (16 * 2**30, 16 * 2**30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 2**20, 256 * 2**20))
    t0 = time.time()
    p = subprocess.run(['/usr/bin/python3', '-I', '-B', str(EVALUATOR), 'C', str(root)], capture_output=True, text=True, env=env, preexec_fn=limits)
    out = Path(work) / f'eval-{batch}'; out.mkdir()
    (out / 'stdout.txt').write_text(p.stdout); (out / 'stderr.txt').write_text(p.stderr)
    rows_path = root / 'eval' / 'C-rows.json'
    graded = 0
    if p.returncode == 0 and rows_path.exists():
        (out / 'C-rows.json').write_bytes(rows_path.read_bytes())
        rows = json.loads(rows_path.read_text())
        graded = sum(1 for r in rows for k in r['arms'] if k.split('-')[0] in ('cpu', 'cuda'))
    res = dict(batch=batch, evaluator_sha256=EVALUATOR_SHA, child_exit=p.returncode, seconds=round(time.time() - t0, 1),
               records_expected=len(recs), records_graded=graded, c_rows_sha256=sha256_file(out / 'C-rows.json') if (out / 'C-rows.json').exists() else None,
               python='/usr/bin/python3', admission=adm)
    (Path(work) / f'evaluate-{batch}.json').write_text(json.dumps(res, indent=1) + '\n')
    print(json.dumps(res))


def cmd_cleanup(work, inv_path, batch):
    import shutil
    root = Path(work) / f'batch{batch}'
    keep = Path(work) / f'small-{batch}.tar'
    with tarfile.open(keep, 'w') as t:
        for p in sorted((root / 'runs').rglob('*')):
            if p.is_file() and not p.name.endswith('.mrc'): t.add(p, arcname=p.relative_to(root / 'runs').as_posix())
    shutil.rmtree(root)
    print(json.dumps(dict(batch=batch, removed=str(root), small_tar=str(keep), sha256=sha256_file(keep))))


if __name__ == '__main__':
    c, work = sys.argv[1], sys.argv[2]
    if c == 'fetch-src': cmd_fetch_src(work)
    else: dict(stage=cmd_stage, evaluate=cmd_evaluate, cleanup=cmd_cleanup)[c](work, sys.argv[3], int(sys.argv[4]))
