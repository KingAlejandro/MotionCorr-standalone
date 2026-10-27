"""VERSION 2 (response to the driver execution review; v1 `run_capture_fw.py` is kept unchanged). Two authorized capture producers only (HELD until the parent
writes PARENT_RELEASE.json); never retry or overwrite an existing namespace. v2 adds: C1 per-launch and post-run binary/staged-input checks, C2 sealed capture
inventory, N1 normalised unexpected errors, N2 structured grant format check, N3 explicit sampling summary, N4 owned process group with timeout and SIGTERM cleanup.

Derived from the reviewed local_ccf_capture_20261026/scripts/run_capture.py (see DRIVER_DIFF.patch). Sequence: OFF = capture off, local full-width ON, compared with the
sealed full-width ON noisy baseline of the native pilot; then ON = capture on, compared with the new OFF, and the four capture witnesses plus full coverage.
Run under the cpu64 lane with the interpreter pinned in the pins:  python3 -B prep/lane.py /home/ubuntu/.mc-venv/bin/python3 -B prep/run_capture_fw_v2.py [--check-only]
--check-only performs every pre-launch check (pins, source, binary, libraries, tools, baseline, root audit, inputs, admission) and creates no evidence directory.
"""
import hashlib, json, os, re, signal, stat, subprocess, sys, time, threading, shutil
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path('/tmp/motioncorr-lfw-capture-20261027'); EVID = ROOT / 'evidence'
PINS_NAME = 'RUN_PINS_v2.json'; DRIVER_NAME = 'run_capture_fw_v2.py'
JOB_TIMEOUT = 600          # seconds per producer (the baseline producer took 0.13 s)
TIME_WRAPPER = lambda d: ['/usr/bin/time', '-v', '-o', str(d / 'time.txt')]   # tests replace it (BSD time has no -o/-v)
PINS_SHA0 = None           # sha256 of the pins file at driver start; every launch re-checks it
class Terminated(BaseException): pass
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture_witness as CW                          # noqa: E402  (hash-pinned)
import weight_oracle as WO                            # noqa: E402  (hash-pinned)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, x): Path(p).write_text(json.dumps(x, indent=2, allow_nan=False) + '\n')
class Refuse(Exception): pass
HEX64 = re.compile(r'^[0-9a-f]{64}$'); UTC = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
def check(v, s):
    if not v:
        if EVID.exists() and not (EVID / 'STOP.json').exists(): write(EVID / 'STOP.json', dict(reason=s, utc=time.strftime('%FT%TZ', time.gmtime())))
        raise Refuse(s)

def root_audit(baseline_dir):
    """The comparator normalises the root it is given: it must be the root the pinned baseline files embed (the r1 pilot STOP was a durable path over original-root files)."""
    bd = Path(baseline_dir); root = str(bd.resolve() / 'output')
    check(bd.name == 'ON' and bd.parent.name == 'noisy', 'ROOT_AUDIT: baseline path must end noisy/ON: ' + str(bd))
    try: argv = json.loads((bd / 'RUN.json').read_text())['argv']; star = (bd / 'output' / 'corrected_micrographs.star').read_text()
    except (OSError, ValueError, KeyError, TypeError) as e: check(False, 'ROOT_AUDIT: baseline RUN.json/STAR unreadable: ' + str(e))
    idx = [i for i, a in enumerate(argv) if a == '--o']
    check(len(idx) == 1 and idx[0] + 1 < len(argv) and argv[idx[0] + 1] == root, 'ROOT_AUDIT: baseline RUN.json --o does not equal the baseline path ' + root)
    check(set(re.findall(r'(/[^\s]*?/output)/', star)) == {root}, 'ROOT_AUDIT: corrected_micrographs.star embeds a different root than ' + root)

def grant_format_ok(g, pins):
    """Format check only: the actual grant and its receipt/index are bound externally by the parent; a well-formed forged grant is not detectable here."""
    return (isinstance(g, dict) and isinstance(g.get('granted_by'), str) and g['granted_by'].strip() != '' and isinstance(g.get('utc'), str) and bool(UTC.match(g['utc']))
            and g.get('cpus') == '32-47' and g.get('lane_locks') == sorted(pins['lane_locks']) and g.get('jobs') == ['OFF', 'ON']
            and isinstance(g.get('receipt_sha256'), str) and bool(HEX64.match(g['receipt_sha256'])))

def parent_release(pins):
    p = ROOT / 'PARENT_RELEASE.json'
    check(p.is_file(), 'HELD: no PARENT_RELEASE.json (only the parent writes it)')
    r = json.loads(p.read_text())
    want = dict(release_id=pins['release_id'], pins_sha256=sha(ROOT / PINS_NAME), driver_sha256=sha(HERE / DRIVER_NAME), witness_sha256=sha(HERE / 'capture_witness.py'),
                source_commit=pins['source_commit'], binary_sha256=pins['binary_sha256'], independent_review_report_sha256=pins['independent_source_review']['report_sha256'], jobs_authorized=['OFF', 'ON'])
    check(all(r.get(k) == v for k, v in want.items()), 'PARENT_RELEASE does not bind the exact pins/driver/witness/source/binary/review/jobs')
    check(grant_format_ok(r.get('fresh_resource_grant'), pins), 'PARENT_RELEASE lacks a structured fresh_resource_grant (granted_by, utc, cpus 32-47, the pinned lane locks, jobs OFF/ON, receipt_sha256)')

def pre_checks(pins):
    """Everything that can be checked before a producer exists. Raises Refuse on the first failure."""
    check(sys.executable == pins['interpreter']['path'] and sys.version.split()[0] == pins['interpreter']['version'], 'interpreter differs from the pins')
    import numpy as np
    check(np.__version__ == pins['interpreter']['numpy'] and sha(np.__file__) == pins['interpreter']['numpy_init_sha256'], 'NumPy identity differs from the pins')
    check(pins['independent_source_review']['verdict'] == 'CLEAR' and pins['independent_source_review']['source_commit'] == pins['source_commit'], 'independent source review is not CLEAR for the pinned source')
    for f, h in pins['prep_files'].items(): check(sha(ROOT / 'prep' / f) == h, 'prep file changed: ' + f)
    check(sha(HERE / DRIVER_NAME) == pins['prep_files'][DRIVER_NAME], 'driver differs from the pins')
    cp = subprocess.run([sys.executable, '-B', str(ROOT / 'prep/verify_source.py'), str(ROOT / 'source'), str(ROOT / 'prep/source.blobs')], capture_output=True, text=True)
    check(cp.returncode == 0 and sha(ROOT / 'prep/source.blobs') == pins['blob_list_sha256'], 'source tree differs from the pinned git blob list: ' + cp.stdout[-300:])
    check(sha(pins['binary_path']) == pins['binary_sha256'], 'binary changed')
    ldd = subprocess.check_output(['ldd', pins['binary_path']], text=True)
    libs = {os.path.realpath(l.split()[2]): None for l in ldd.splitlines() if '=>' in l and l.split()[2].startswith('/')}
    check(set(libs) == set(pins['libs']) and all(sha(p) == h for p, h in pins['libs'].items()), 'shared libraries differ from the pins')
    check(sha(os.path.realpath('/lib64/ld-linux-x86-64.so.2')) == pins['loader_sha256'], 'loader changed')
    check(sha(pins['comparator']['path']) == pins['comparator']['sha256'], 'comparator changed')
    base = Path(pins['baseline']['dir']); root_audit(base)
    check(sha(base / 'RUN.json') == pins['baseline']['run_json_sha256'], 'baseline RUN.json changed')
    old = json.loads((base / 'RUN.json').read_text())
    check(old['argv'] == pins['baseline']['argv'] and old['exit'] == 0 and old['arm'] == 'ON' and old['case'] == 'noisy', 'baseline RUN.json argv/exit/arm differ from the pins')
    check(sorted(old['publication']) == sorted(pins['baseline']['products']), 'baseline product set differs from the pins')
    for rel, h in pins['baseline']['products'].items():
        check(old['publication'][rel]['sha256'] == h and sha(base / 'output' / rel) == h, 'baseline product changed: ' + rel)
    check(sorted(p.relative_to(base / 'output').as_posix() for p in (base / 'output').rglob('*') if p.is_file()) == sorted(pins['baseline']['products']), 'baseline output has extra files')
    for rel, h in pins['baseline']['other_files'].items(): check(sha(base / rel) == h, 'baseline file changed: ' + rel)
    for name, h in pins['input_files'].items(): check(sha(base / 'input' / name) == h, 'input fixture changed: ' + name)
    check(sorted(p.name for p in (base / 'input').iterdir()) == sorted(pins['input_files']), 'baseline input scope differs')
    # the oracle must discriminate and the witness code must be the pinned one
    check(not (WO.weight_map(42) == WO.weight_map(22)).all(), 'weight oracle cannot discriminate x_norm 42 from 22')

def admission(d, pins, label):
    locks = json.loads(os.environ['MOTIONCORR_HELD_LEASES']); cpus = sorted(os.sched_getaffinity(0))
    check(sorted(locks) == sorted(pins['lane_locks']) and cpus == list(range(32, 48)), 'leases/affinity differ from the pins')
    ps = subprocess.check_output(['ps', '-eo', 'pid,ppid,psr,pcpu,args', '--sort=-pcpu'], text=True); (d / f'{label}-occupancy-before.txt').write_text(ps)
    rows = [s.split(None, 4) for s in ps.splitlines()[1:]]; own = {os.getpid(), os.getppid()}
    while True:
        prior = len(own); own.update(int(r[0]) for r in rows if len(r) == 5 and int(r[1]) in own)
        if len(own) == prior: break
    for r in rows:
        if len(r) != 5 or int(r[0]) in own or float(r[3]) < 50: continue
        try: mask = sorted(os.sched_getaffinity(int(r[0])))
        except ProcessLookupError: continue
        check(not set(mask) & set(cpus), 'foreign heavy process overlapping allowed CPU mask: ' + str((r, mask)))
    used = 0
    for r in pins['scratch_cap_roots']:
        if Path(r).exists(): used += sum(p.stat().st_size for p in Path(r).rglob('*') if p.is_file() and not p.is_symlink())
    mem = {l.split(':')[0]: int(l.split()[1]) * 1024 for l in Path('/proc/meminfo').read_text().splitlines()}
    check(used < 25 * 1024 ** 3 and shutil.disk_usage(ROOT).free > 3 * 1024 ** 3 and mem['MemAvailable'] > 4 * 1024 ** 3, 'scratch/disk/memory admission failed')
    write(d / f'{label}-admission.json', dict(utc=time.strftime('%FT%TZ', time.gmtime()), label=label, locks=locks, whole_chain_affinity=cpus, requested_native_threads=2, OMP_NUM_THREADS='2', BLAS_threads=1,
                                             combined_scratch_bytes=used, limit_bytes=25 * 1024 ** 3, mem_available_bytes=mem['MemAvailable'], disk_free_bytes=shutil.disk_usage(ROOT).free,
                                             assessment='no foreign >=50% process whose allowed mask overlaps the lane at fresh admission; receipt only, no timing claim'))

def monitor(pid, path, done):
    with path.open('w') as out:
        while not done.is_set():
            # Whole process tree actual masks/threads/RSS; no payload inspection.
            ps = subprocess.check_output(['ps', '-eo', 'pid,ppid'], text=True); pairs = [tuple(map(int, l.split())) for l in ps.splitlines()[1:] if len(l.split()) == 2]; own = {pid}
            while True:
                n = len(own); own.update(p for p, pp in pairs if pp in own)
                if n == len(own): break
            records = []
            for p in sorted(own):
                try:
                    fields = dict(l.split(':', 1) for l in Path(f'/proc/{p}/status').read_text().splitlines() if ':' in l)
                    records.append(dict(pid=p, name=fields['Name'].strip(), allowed=fields['Cpus_allowed_list'].strip(), threads=int(fields['Threads']), rss=fields.get('VmRSS', '').strip()))
                except FileNotFoundError: pass
            out.write(json.dumps(dict(monotonic=time.monotonic(), processes=records)) + '\n'); out.flush(); done.wait(.05)

def identity(a, b, d, pins, tag):
    check((a / 'runtime.json').read_bytes() == (b / 'runtime.json').read_bytes(), f'{tag}: runtime bytes differ')
    check((a / 'output/noisy.star').read_bytes() == (b / 'output/noisy.star').read_bytes(), f'{tag}: raw case STAR bytes differ')
    cp = subprocess.run([sys.executable, '-B', pins['comparator']['path'], str(a / 'output'), str(b / 'output'), str(d / f'{tag}-products.json')], capture_output=True, text=True)
    (d / f'{tag}-products.stdout').write_text(cp.stdout + cp.stderr); check(cp.returncode == 0, f'{tag}: product identity failed')
    j = json.loads((d / f'{tag}-products.json').read_text())
    check(j['verdict'] == 'IDENTICAL' and j['n_files'] == 10 and j['n_gated'] == 7 and j['n_gated_differing'] == 0, f'{tag}: comparator verdict {j["verdict"]} gated {j["n_gated"]}/{j["n_gated_differing"]}')
    write(d / f'{tag}-identity.json', dict(runtime_byte_equal=True, case_STAR_byte_equal=True, product_comparator='IDENTICAL', n_files=j['n_files'], n_gated=j['n_gated'], runtime_sha256=sha(a / 'runtime.json'), case_STAR_sha256=sha(a / 'output/noisy.star'),
                                           MRC='header0-223+size+pixels exact; labels inventoried', logs_PDF='inventory only'))

def sampling_summary(path):
    """N3: explicit counts of what the monitor actually saw. OBSERVED, PARTIAL and UNOBSERVED are all legal; nothing here asserts a thread count or a mask."""
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()] if Path(path).exists() else []
    prod = [[q for q in r['processes'] if q['name'].startswith('motioncorr')] for r in rows]
    withp = [x for x in prod if x]
    state = 'UNOBSERVED' if not withp else ('OBSERVED' if len(withp) == len(rows) else 'PARTIAL')
    return dict(state=state, n_samples=len(rows), n_samples_naming_producer=len(withp), n_empty_samples=sum(1 for r in rows if not r['processes']),
                distinct_allowed_cpu_lists_of_producer=sorted({q['allowed'] for x in withp for q in x}), max_threads_of_producer=max([q['threads'] for x in withp for q in x], default=None),
                note='receipt only; no universal thread or mask claim')

def _kill_group(p):
    """Terminate and reap only our own child's process group (the child is its own session/group leader); never a group we do not own."""
    if p.poll() is not None: return
    try:
        pgid = os.getpgid(p.pid)
        if pgid != p.pid or pgid == os.getpgrp(): p.kill(); p.wait(); return
        os.killpg(pgid, signal.SIGTERM)
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(pgid, signal.SIGKILL); p.wait()
    except ProcessLookupError: p.wait()

def _pdeathsig():
    if not sys.platform.startswith('linux'): return None
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    return lambda: libc.prctl(1, int(signal.SIGKILL), 0, 0, 0)   # PR_SET_PDEATHSIG for the direct child only; its children die with the group kill

def launch(cmd, cwd, env, d, timeout):
    """N4: the producer runs in its own session/process group with a timeout; any exception or SIGTERM in the driver kills and reaps the owned group first."""
    done = threading.Event(); timed_out = False; start = time.monotonic()
    with (d / 'stdout.log').open('w') as out:
        p = subprocess.Popen([*TIME_WRAPPER(d), *cmd], cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=_pdeathsig())
        t = threading.Thread(target=monitor, args=(p.pid, d / 'actual-resources.jsonl', done)); t.start()
        try:
            try: rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired: timed_out = True; _kill_group(p); rc = p.returncode
        except BaseException: _kill_group(p); raise
        finally: done.set(); t.join()
    return rc, timed_out, time.monotonic() - start

def launch_checks(pins):
    """C1: before EVERY Popen, the pinned binary, the immutable pins and the staged inputs (and their staging sources) are re-verified."""
    b = Path(pins['binary_path']); check(b.is_file() and not b.is_symlink() and sha(b) == pins['binary_sha256'], 'binary differs from the pins at launch')
    check(PINS_SHA0 is not None and sha(ROOT / PINS_NAME) == PINS_SHA0, 'the pins file changed since the driver started')
    ni = ROOT / 'native-input'; names = sorted(q.name for q in ni.iterdir()) if ni.is_dir() else None
    check(names == sorted(pins['input_files']), f'staged native-input scope differs: {names}')
    for name, h in pins['input_files'].items():
        q = ni / name; check(stat.S_ISREG(os.lstat(q).st_mode) and sha(q) == h, 'staged input differs from the pins at launch: ' + name)
        check(sha(Path(pins['baseline']['dir']) / 'input' / name) == h, 'staging source (baseline input) differs from the pins: ' + name)

def run(label, pins):
    d = EVID / 'runs' / label; d.mkdir(parents=True, exist_ok=False); admission(d, pins, label); launch_checks(pins)
    base = Path(pins['baseline']['dir']); cmd = list(pins['baseline']['argv']); cmd[0] = pins['binary_path']; cmd[cmd.index('--o') + 1] = str(d / 'output')
    env = dict(pins['baseline']['environment']); env.pop('MC_DIAG_MODEL_OUT', None); env.update(MC_DIAG_MODEL_OUT=str(d / 'runtime.json'), PATH='/usr/bin:/bin')
    check(not any(k.startswith('MC_DIAG_LOCAL') for k in env), 'capture variable in the base environment')
    if label == 'ON': env['MC_DIAG_LOCAL_CCF_DIR'] = str(d / 'capture')
    check(cmd.count('--experimental_local_full_width_weight') == 1, 'full-width flag missing from the pinned argv')
    before = sha(pins['binary_path'])
    rc, timed_out, wall = launch(cmd, ROOT / 'native-input', env, d, JOB_TIMEOUT)
    after = sha(pins['binary_path'])
    receipt = dict(label=label, exit=rc, timed_out=timed_out, argv=cmd, cwd=str(ROOT / 'native-input'), binary_sha256=before, binary_sha256_before_launch=before, binary_sha256_after_run=after, binary_sha256_pinned=pins['binary_sha256'],
                   wall_receipt_only=wall, environment=env, device='CPU; GPU not applicable', sampling=sampling_summary(d / 'actual-resources.jsonl'),
                   products={str(q.relative_to(d / 'output')): dict(bytes=q.stat().st_size, sha256=sha(q)) for q in (d / 'output').rglob('*') if q.is_file()} if (d / 'output').exists() else {})
    write(d / 'RUN.json', receipt)
    if after != pins['binary_sha256'] or before != pins['binary_sha256']:
        write(d / 'INVALID.json', dict(reason='binary hash differs from the pin around the run', before=before, after=after, pinned=pins['binary_sha256'])); check(False, f'{label}: binary changed around the run; run retained as invalid')
    check(not timed_out, f'{label}: producer timed out after {JOB_TIMEOUT} s'); check(rc == 0, 'producer exit ' + str((label, rc)))
    check(sorted(receipt['products']) == sorted(pins['baseline']['products']), 'publication differs from the baseline file set')
    return d

def run_witness_stage(on, oracle42, oracle22):
    """N1: every failure of the witness stage, expected or not, becomes a STOP; no pass is recorded unless all witnesses returned."""
    try: return CW.run_all(on / 'capture', (on / 'output/noisy.log').read_text(), oracle42, oracle22)
    except CW.Stop as e: check(False, f'WITNESS {e.name}: {e.why}')
    except Refuse: raise
    except Exception as e: check(False, f'WITNESS_MALFORMED {type(e).__name__}: {e}')

def inventory(cap):
    """C2: relative path, size, sha256 of every file under the capture tree; any symlink or non-regular entry is a STOP."""
    inv = {}
    for q in sorted(Path(cap).rglob('*')):
        m = os.lstat(q).st_mode
        check(not stat.S_ISLNK(m) and (stat.S_ISREG(m) or stat.S_ISDIR(m)), f'capture contains a symlink or non-regular entry: {q}')
        if stat.S_ISREG(m): inv[q.relative_to(cap).as_posix()] = dict(bytes=q.stat().st_size, sha256=sha(q))
    return inv

def expected_capture_files(coverage):
    """Independent closed form of the writer's file counts (not the witness's list): 2 root files + per patch 34 + 134 per executed iteration (302 for 2 iterations)."""
    return 2 + sum(34 + 134 * c['executed_iterations'] for c in coverage.values())

def seal_capture(on, witnesses):
    cap = on / 'capture'; inv = inventory(cap); n = len(inv)
    check(n == expected_capture_files(witnesses['coverage']) == 2 + sum(c['files'] for c in witnesses['coverage'].values()), f'capture file count {n} differs from the coverage-derived counts')
    write(on / 'capture-inventory.json', dict(count=n, bytes_total=sum(v['bytes'] for v in inv.values()), files=inv))     # outside the capture tree: no self-hash
    check(inventory(cap) == inv, 'capture changed while it was being inventoried')
    return sha(on / 'capture-inventory.json'), n

def main():
    global PINS_SHA0
    check_only = '--check-only' in sys.argv
    pins = json.loads((ROOT / PINS_NAME).read_text()); PINS_SHA0 = sha(ROOT / PINS_NAME)
    pre_checks(pins)
    if check_only:
        d = ROOT / 'receipts'; d.mkdir(exist_ok=True); admission(d, pins, 'checkonly_v2')
        released = (ROOT / 'PARENT_RELEASE.json').is_file()
        if released: parent_release(pins)
        write(d / 'checkonly_v2.json', dict(utc=time.strftime('%FT%TZ', time.gmtime()), driver=DRIVER_NAME, status='PRE_CHECKS_PASS', parent_release='PRESENT_AND_BOUND' if released else 'ABSENT: HELD', producers_launched=0, evidence_created=EVID.exists()))
        print('check-only: pre-launch checks pass; parent release', 'bound' if released else 'ABSENT (held); nothing launched'); return 0
    parent_release(pins)
    def on_term(signum, frame): raise Terminated('SIGTERM')
    old_term = signal.signal(signal.SIGTERM, on_term)
    EVID.mkdir(exist_ok=False)
    try:
        check(not (ROOT / 'native-input').exists(), 'native-input already exists')
        (ROOT / 'native-input').mkdir()
        base = Path(pins['baseline']['dir'])
        for name, h in pins['input_files'].items():
            shutil.copyfile(base / 'input' / name, ROOT / 'native-input' / name); check(sha(ROOT / 'native-input' / name) == h, 'staged input differs: ' + name)
        check(sorted(p.name for p in (ROOT / 'native-input').iterdir()) == ['noisy.mrcs', 'noisy.star'], 'native input directory scope differs')
        oracle42, oracle22 = WO.weight_map(42), WO.weight_map(22)
        off = run('OFF', pins); identity(base, off, off, pins, 'OFF_vs_sealed_baseline')
        write(off / 'log-witness.json', CW.check_log((off / 'output/noisy.log').read_text())); check(not (off / 'capture').exists(), 'capture directory exists in the capture-OFF run')
        on = run('ON', pins); identity(off, on, on, pins, 'ON_vs_new_OFF')
        check((on / 'capture/COMPLETE.json').is_file(), 'capture incomplete')
        witnesses = run_witness_stage(on, oracle42, oracle22)
        write(on / 'capture-witnesses.json', witnesses)
        inv_sha, n = seal_capture(on, witnesses)
        check(sha(on / 'capture-inventory.json') == inv_sha and inventory(on / 'capture') == json.loads((on / 'capture-inventory.json').read_text())['files'], 'capture differs from its sealed inventory at completion')
        write(EVID / 'NATIVE_COMPLETE.json', dict(producers=2, identity='PASS both comparisons', witnesses='PASS W1-W4 and coverage', source_commit=pins['source_commit'], binary_sha256=pins['binary_sha256'],
                                                 capture_inventory_sha256=inv_sha, capture_inventory_files=n, no_timing_claim=True, truth_and_analysis='UNRUN until the capture record is sealed'))
    except (Refuse, Terminated): raise
    except Exception as e: check(False, f'UNEXPECTED {type(e).__name__}: {e}')
    finally: signal.signal(signal.SIGTERM, old_term)
    return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Refuse as e:
        print('REFUSED/STOP:', e, file=sys.stderr); sys.exit(3)
    except Terminated:
        if EVID.exists() and not (EVID / 'STOP.json').exists(): write(EVID / 'STOP.json', dict(reason='terminated by SIGTERM; owned process group cleaned up', utc=time.strftime('%FT%TZ', time.gmtime())))
        print('TERMINATED', file=sys.stderr); sys.exit(143)
