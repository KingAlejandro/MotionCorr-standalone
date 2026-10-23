#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""#262 four-arm campaign on 4GPUs (FREEZE.md). NumPy-free; stdlib only.

  campaign.py queue  ROOT            write ROOT/queue.json in the frozen order
  campaign.py worker ROOT cpu  CPU   run CPU jobs on one pinned CPU
  campaign.py worker ROOT cuda CPU   run CUDA jobs on GPU2 (lock held for the worker's life)

A job directory is claimed by mkdir and is never reused: a failed process keeps
its RUN.json with the nonzero exit; an orphaned directory without RUN.json is
reported and skipped. Inputs are hash-admitted against the recorded manifests
before their first use. No process starts above the 115 GiB scratch cap.
"""
import fcntl, hashlib, json, os, re, socket, subprocess, sys, threading, time
from pathlib import Path

UUID = 'GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598'
GPU_LOCK = '/tmp/motioncorr-gpu2-correctness.lock'
BENCH_LOCK = '/tmp/motioncorr-bench.lock'
CAP = 115 * 2**30
ARMS = ['none', 'global', 'local', 'both']
LD = '/usr/local/cuda-12.8/lib64'
TIER_B_ORDER = ['pedestal32', 'pedestal0', 'contrast025', 'contrast4', 'dose1', 'dose05', 'dose2', 'dose4', 'outmodel', 'nonsquare']
V2_CASES = ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']
CONTROLS = ['tutorial-00', 'tutorial-01', 'e10028-00', 'e10028-01', 'e10361-00', 'e10361-01',
            'e10441-00', 'e10441-01', 'e10474f4-00', 'e10474f4-01', 'e10164-00']
KM = Path('/mnt/clathrin/alex-motioncorr-km-truth/fixtures')
SWEEP = Path('/mnt/clathrin/alex-motioncorr-s1/sweep')


def utc(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()


def job(id, tier, backend, arm, cwd, args, inputs, build=None, model=False, group=None):
    build = build or (backend + '-exp')
    return dict(id=id, tier=tier, backend=backend, arm=arm, build=build, cwd=str(cwd), args=args,
                inputs=inputs, model=model, group=group)


def build_queue(root):
    tools = root / 'tools'
    q = []
    # Tier A (+ plain controls): #273 run_v2_cases argv with --j 1.
    v2 = json.loads((root / 'v2fixtures' / 'MANIFEST.json').read_text())
    for backend in ['cpu', 'cuda']:
        for arm in ARMS + ['plain']:
            for case in V2_CASES:
                p = '3' if case in ('affine', 'pedestal', 'noisy') else '1'
                files = v2['cases'][case]['files']
                inputs = {str(root / 'v2fixtures' / n): s for n, s in files.items() if n.endswith(('.mrcs', '.star'))}
                args = ['--i', case + '.star', '--o', '{OUT}/' + case, '--use_own', '--j', '1', '--patch_x', p, '--patch_y', p,
                        '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW', '--first_frame_sum', '1',
                        '--last_frame_sum', '5', '--skip_logfile']
                build = backend + ('-plain' if arm == 'plain' else '-exp')
                q.append(job(f'A-{case}-{backend}-{arm}', 'A', backend, arm, root / 'v2fixtures', args, inputs, build,
                             model=arm != 'plain', group=case))
    # Tier B: #269 argv with --j 1; plain controls on two movies.
    index = {r['name']: r for r in json.loads((tools / 'FIXTURE_INDEX.json').read_text())}
    def tier_b(name, backend, arm):
        r = index[name]
        args = ['--i', 'input.star', '--o', '{OUT}/output', '--use_own', '--j', '1', '--patch_x', '5', '--patch_y', '5',
                '--group_frames', '1', '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW',
                '--first_frame_sum', '1', '--last_frame_sum', str(r['frames']), '--skip_logfile', '--ingest', 'float',
                '--ingest_witness', '{OUT}/ingest.txt']
        build = backend + ('-plain' if arm == 'plain' else '-exp')
        return job(f'B-{name}-{backend}-{arm}', 'B', backend, arm, KM / name, args,
                   {str(KM / name / 'movie.mrcs'): r['movie_sha256'], str(KM / name / 'RECEIPT.json'): r['receipt_sha256']},
                   build, model=arm != 'plain', group=name)
    for c in TIER_B_ORDER:
        for s in range(10):
            for backend in ['cpu', 'cuda']:
                for arm in ARMS: q.append(tier_b(f'{c}-s{s:02d}', backend, arm))
    for name in ['pedestal32-s00', 'dose1-s00']:
        for backend in ['cpu', 'cuda']: q.append(tier_b(name, backend, 'plain'))
    # Tier C: #271 GPU-ledger argv/inputs for the 60 configs; S1.1 sweep argv for the rest.
    manifest = {m['movie']: m for m in json.loads((tools / 'dc_oracle-input-manifest.json').read_text())}
    ledger = {r['label']: r for r in json.loads((tools / 'dc_oracle-run-ledger.json').read_text())}
    def strip(argv, drop_gpu):
        i = next(k for k, x in enumerate(argv) if x.endswith('/motioncorr'))
        opts, out, k = argv[i + 1:], [], 0
        while k < len(opts):
            x = opts[k]
            if x == '--o': out += [x, '{OUT}/']; k += 2; continue
            if x == '--ingest_witness': out += [x, '{OUT}/witness.txt']; k += 2; continue
            if x == '--j': out += [x, '1']; k += 2; continue
            if x in ('--gpu', '--ingest'): k += 2; continue
            out.append(x); k += 1
        return out
    def tier_c(movie, grid, backend, arm, cwd, argv, inputs):
        args = strip(argv, True)
        if backend == 'cuda': args += ['--gpu', '0', '--ingest', 'auto']
        return job(f'C-{movie}-{grid}-{backend}-{arm}', 'C', backend, arm, cwd, args, inputs, model=True, group=movie)
    families = [('e10216', [f'e10216-{i:02d}' for i in range(10)]), ('e12963', [f'e12963-{i:02d}' for i in range(10)]),
                ('e10474f3', [f'e10474f3-{i:02d}' for i in range(10)])]
    for _, movies in families:
        for movie in movies:
            m = manifest[movie]
            for grid in ['p5', 'p3']:
                rec = ledger[f'{movie}-{grid}-G_none']
                cwd = Path(rec['sweep_cwd'])
                inputs = {str(cwd / 'movies.star'): m['input_star']['sha256'], m['movie_file']['path']: m['movie_file']['sha256']}
                argv = rec['argv']
                if '--gainref' in argv: inputs[str(cwd / argv[argv.index('--gainref') + 1])] = None
                for backend in ['cpu', 'cuda']:
                    for arm in ARMS: q.append(tier_c(movie, grid, backend, arm, cwd, rec['argv'], inputs))
    for movie in [f'e10641-{i:02d}' for i in range(10)] + CONTROLS:
        cwd = SWEEP / 'inputs' / movie
        for grid in ['p5', 'p3']:
            rec = json.loads((SWEEP / 'runs' / f'{movie}-{grid}-F-cuda' / 'run.json').read_text())
            # Sweep inputs carry no committed hash manifest; admission records first-use hashes.
            inputs = {str(cwd / 'movies.star'): None}
            if (cwd / 'gain.mrc').exists(): inputs[str(cwd / 'gain.mrc')] = None
            for f in sorted((cwd / 'Movies').iterdir()) if (cwd / 'Movies').is_dir() else []: inputs[str(f)] = None
            for backend in ['cpu', 'cuda']:
                for arm in ARMS: q.append(tier_c(movie, grid, backend, arm, cwd, rec['argv'], inputs))
    ids = [j['id'] for j in q]
    assert len(ids) == len(set(ids))
    (root / 'queue.json').write_text(json.dumps(q, indent=1) + '\n')
    counts = {}
    for j in q: counts[j['tier'] + '-' + j['backend']] = counts.get(j['tier'] + '-' + j['backend'], 0) + 1
    print(json.dumps(dict(jobs=len(q), counts=counts)))


def usage_bytes(root):
    total = 0
    for d, _, files in os.walk(root / 'runs'):
        for f in files:
            try: total += os.lstat(os.path.join(d, f)).st_size
            except OSError: pass
    return total


def admit(root, path, expected):
    """Hash an input once (cached by path, size and mtime); compare with the manifest if any."""
    adm = root / 'admission'; adm.mkdir(exist_ok=True)
    st = os.stat(path)
    key = hashlib.sha256(f'{path}|{st.st_size}|{st.st_mtime_ns}'.encode()).hexdigest()[:24]
    rec_path = adm / (key + '.json')
    with open(adm / (key + '.lock'), 'a') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if rec_path.exists(): rec = json.loads(rec_path.read_text())
        else:
            rec = dict(path=path, bytes=st.st_size, mtime_ns=st.st_mtime_ns, sha256=sha256(path), utc=utc())
            rec_path.write_text(json.dumps(rec) + '\n')
    if expected and rec['sha256'] != expected:
        raise RuntimeError(f'input hash mismatch {path}: {rec["sha256"]} != {expected}')
    return rec['sha256']


def gpu_state():
    q = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu,ecc.errors.uncorrected.volatile.total',
                        '--format=csv,noheader'], capture_output=True, text=True, timeout=30).stdout
    apps = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory', '--format=csv,noheader'],
                          capture_output=True, text=True, timeout=30).stdout
    return dict(utc=utc(), gpus=q, apps=apps)


def bench_status():
    try: fd = os.open(BENCH_LOCK, os.O_RDONLY)
    except FileNotFoundError: return 'absent'
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN); return 'no-exclusive-holder'
    except BlockingIOError: return 'exclusive-holder-present'
    finally: os.close(fd)


def descendants(root_pid):
    fam, fr = {root_pid}, [root_pid]
    while fr:
        nxt = []
        for pid in fr:
            try: nxt += [int(c) for c in open(f'/proc/{pid}/task/{pid}/children').read().split()]
            except OSError: pass
        fam |= set(nxt); fr = nxt
    return fam


def run_job(root, j, cpu, binaries):
    out = root / 'runs' / j['id']
    try: out.mkdir(parents=True)
    except FileExistsError: return None
    binary = binaries[j['build']]
    inputs = {p: admit(root, p, s) for p, s in j['inputs'].items()}
    args = [a.replace('{OUT}', str(out)) for a in j['args']]
    env = {k: v for k, v in os.environ.items() if not k.startswith(('MC_EXPERIMENT_', 'MC_DIAG_', 'OMP_', 'CUDA_'))}
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LD_LIBRARY_PATH=LD)
    extra = {}
    if j['arm'] != 'plain': extra['MC_EXPERIMENT_CCF_DC_ARM'] = j['arm']
    if j['model']: extra['MC_DIAG_MODEL_OUT'] = str(out / 'runtime.json')
    if j['backend'] == 'cuda':
        extra.update(CUDA_VISIBLE_DEVICES=UUID, CUDA_DEVICE_ORDER='PCI_BUS_ID'); args += [] if '--gpu' in args else ['--gpu', '0']
    else: extra['CUDA_VISIBLE_DEVICES'] = ''
    env.update(extra)
    cmd = ['taskset', '-c', str(cpu), '/usr/bin/time', '-v', '-o', str(out / 'time-v.log'), binary['path']] + args
    rec = dict(id=j['id'], tier=j['tier'], backend=j['backend'], arm=j['arm'], build=j['build'], group=j['group'],
               source_sha=(root / 'SOURCE_SHA').read_text().strip(), binary=binary['path'], binary_sha256=binary['sha256'],
               argv=cmd, cwd=j['cwd'], env=extra, cpu=str(cpu), host=socket.gethostname(), inputs=inputs,
               bench_lock=bench_status(), start_utc=utc())
    if j['backend'] == 'cuda': rec['gpu_before'] = gpu_state()
    uuids, stop = set(), threading.Event()
    def sampler(pid):
        while not stop.is_set():
            try:
                apps = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader'],
                                      capture_output=True, text=True, timeout=10).stdout
                fam = descendants(pid)
                for line in apps.splitlines():
                    u, p = [x.strip() for x in line.split(',')]
                    if int(p) in fam: uuids.add(u)
            except Exception: pass
            stop.wait(0.25)
    t0 = time.time()
    with open(out / 'stdout.log', 'w') as so, open(out / 'stderr.log', 'w') as se:
        p = subprocess.Popen(cmd, cwd=j['cwd'], env=env, stdout=so, stderr=se)
        th = threading.Thread(target=sampler, args=(p.pid,), daemon=True) if j['backend'] == 'cuda' else None
        if th: th.start()
        p.wait(); stop.set()
        if th: th.join(15)
    rec.update(exit=p.returncode, wall_s_unqualified=round(time.time() - t0, 2), end_utc=utc(), gpu_witness_uuids=sorted(uuids))
    if j['backend'] == 'cuda': rec['gpu_after'] = gpu_state()
    witness = [l.strip() for l in open(out / 'stderr.log', errors='replace') if l.startswith('MC_EXPERIMENT_CCF_DC arm=') and '=' in l.split('arm=', 1)[1]]
    rec['dc_witness'] = witness[-1] if witness else None
    files = {}
    for d, _, fs in os.walk(out):
        for f in fs:
            fp = Path(d) / f
            if fp.name in ('RUN.json',): continue
            files[str(fp.relative_to(out))] = dict(bytes=fp.stat().st_size, sha256=sha256(fp))
    rec['outputs'] = files
    (out / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
    return rec


def worker(root, kind, cpu):
    q = [j for j in json.loads((root / 'queue.json').read_text()) if j['backend'] == kind]
    binaries = json.loads((root / 'binaries.json').read_text())
    for b in binaries.values():
        if sha256(b['path']) != b['sha256']: raise RuntimeError('binary hash changed: ' + b['path'])
    log = open(root / f'worker-{kind}-{cpu}.log', 'a')
    lock = None
    if kind == 'cuda':
        lock = open(GPU_LOCK, 'a')
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(utc(), 'GPU2 correctness lock busy; stopping', file=log, flush=True); return 75
        st = gpu_state()
        (root / f'gpu-admission-{int(time.time())}.json').write_text(json.dumps(st, indent=1) + '\n')
        if UUID in st['apps']:
            print(utc(), 'GPU2 has a compute process; stopping', file=log, flush=True); return 75
        row = [l for l in st['gpus'].splitlines() if UUID in l]
        if not row or row[0].split(',')[0].strip() != '2' or row[0].split(',')[-1].strip() not in ('0', '[N/A]'):
            print(utc(), 'GPU2 UUID/ECC admission failed:', row, file=log, flush=True); return 75
    try:
        for j in q:
            out = root / 'runs' / j['id']
            if out.exists():
                if not (out / 'RUN.json').exists() and not (out / 'ORPHAN').exists():
                    pass  # in progress by another worker, or orphaned: reconciled by `status`
                continue
            if usage_bytes(root) > CAP:
                print(utc(), 'scratch cap reached; stopping before', j['id'], file=log, flush=True); return 3
            try: rec = run_job(root, j, cpu, binaries)
            except RuntimeError as e:
                (out / 'ADMISSION_FAILED').write_text(str(e) + '\n')
                print(utc(), j['id'], 'ADMISSION FAILED', e, file=log, flush=True); continue
            if rec: print(utc(), j['id'], 'exit', rec['exit'], rec['wall_s_unqualified'], rec['dc_witness'], file=log, flush=True)
        return 0
    finally:
        if lock:
            (root / f'gpu-final-{int(time.time())}.json').write_text(json.dumps(gpu_state(), indent=1) + '\n')
            lock.close()


if __name__ == '__main__':
    cmd, root = sys.argv[1], Path(sys.argv[2]).resolve()
    if cmd == 'queue': build_queue(root)
    elif cmd == 'worker': sys.exit(worker(root, sys.argv[3], int(sys.argv[4])))
