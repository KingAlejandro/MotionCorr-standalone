"""Fake-child tests of run_capture_fw_v2.py (C1, C2, N1, N2, N3, N4) on any POSIX host; no native producer, no truth.
The driver's own code runs with ROOT/EVID redirected to a private temp tree, a fake producer script, the real pinned comparator and a real FullWidthPair capture
made by the actual capture code (gen_fw_capture). Only the Linux-only pre-launch checks (pre_checks, admission, /usr/bin/time wrapper) are replaced here; they are
exercised separately on cpu64. Usage: test_driver_v2.py GENERATOR_BINARY   (run with python -B)"""
import copy, hashlib, json, os, shutil, signal, stat, subprocess, sys, tempfile, textwrap, time
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'scripts')]
import run_capture_fw_v2 as D
import capture_witness as CW
GEN = sys.argv[1]
REPO = Path(os.environ['DRV_TEST_REPO'] if os.environ.get('DRV_TEST_REPO') else HERE.parents[5])
COMPARATOR = REPO / 'docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py'
BUNDLE = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/runs/noisy')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
passed = []
def ok(name): passed.append(name)
def expect_refuse(name, fn, needle):
    try: fn()
    except D.Refuse as e:
        assert needle in str(e), (name, str(e)); ok(name); return
    raise AssertionError('NOT REFUSED: ' + name)

tmp0 = Path(tempfile.mkdtemp(prefix='drv2-')).resolve()
GOOD_CAP = tmp0 / 'good_capture'
subprocess.run([GEN, str(GOOD_CAP)], check=True, env=dict(os.environ, OMP_NUM_THREADS='2'))
ON_LOG = (BUNDLE / 'ON/noisy.log').read_text()

PRODUCTS = ['corrected_micrographs.star', 'corrected_micrographs_all_rlnAccumMotionEarly.eps', 'corrected_micrographs_all_rlnAccumMotionLate.eps', 'corrected_micrographs_all_rlnAccumMotionTotal.eps',
            'logfile.pdf', 'logfile.pdf.lst', 'noisy.log', 'noisy.mrc', 'noisy.star', 'noisy_shifts.eps']
def template(name):
    if name == 'noisy.mrc': return bytes(range(256)) * 5
    if name == 'noisy.log': return ON_LOG.encode()
    if name.endswith('.star') and name != 'noisy.star' or name.endswith('.eps'): return f'{name} root @ROOT@/ end\n'.encode()
    return f'{name} body\n'.encode()
FAKE = textwrap.dedent('''\
    #!%(py)s
    import json, os, shutil, sys, time
    from pathlib import Path
    knobs = json.loads(Path(%(knobs)r).read_text()); a = sys.argv; out = Path(a[a.index('--o') + 1]); out.mkdir(parents=True)
    if knobs.get('sleep'): time.sleep(knobs['sleep'])
    for name, body in json.loads(Path(%(tpl)r).read_text()).items(): (out / name).write_bytes(body.encode('latin1').replace(b'@ROOT@', str(out).encode()))
    Path(os.environ['MC_DIAG_MODEL_OUT']).write_text('{"global":[[0,0]]}\\n')
    if os.environ.get('MC_DIAG_LOCAL_CCF_DIR'): shutil.copytree(%(cap)r, os.environ['MC_DIAG_LOCAL_CCF_DIR'])
    if knobs.get('selfmodify') == os.environ.get('MC_DIAG_LOCAL_CCF_DIR', 'OFF') or (knobs.get('selfmodify') == 'OFF' and not os.environ.get('MC_DIAG_LOCAL_CCF_DIR')):
        open(sys.argv[0], 'ab').write(b'#')
''')

def make_env(name, knobs=None):
    """A private ROOT with baseline, staged-input sources, fake producer, pins and a valid PARENT_RELEASE; returns (root, pins, knobs_path)."""
    root = tmp0 / name; root.mkdir(); D.ROOT = root; D.EVID = root / 'evidence'; (root / 'prep').mkdir()
    base = root / 'base/noisy/ON'; (base / 'output').mkdir(parents=True); (base / 'input').mkdir()
    (base / 'input/noisy.mrcs').write_bytes(b'M' * 300); (base / 'input/noisy.star').write_bytes(b'S' * 40)
    tpl = {n: template(n).decode('latin1') for n in PRODUCTS}
    for n in PRODUCTS: (base / 'output' / n).write_bytes(tpl[n].encode('latin1').replace(b'@ROOT@', str(base / 'output').encode()))
    (base / 'runtime.json').write_text('{"global":[[0,0]]}\n'); (base / 'stdout.log').write_text('log\n')
    knobs_path = root / 'knobs.json'; knobs_path.write_text(json.dumps(knobs or {})); tpl_path = root / 'template.json'; tpl_path.write_text(json.dumps(tpl))
    binary = root / 'fakebin'; binary.write_text(FAKE % dict(py=sys.executable, knobs=str(knobs_path), tpl=str(tpl_path), cap=str(GOOD_CAP))); binary.chmod(0o755)
    argv = ['/orig/motioncorr', '--i', 'noisy.star', '--o', str(base / 'output'), '--use_own', '--j', '2', '--experimental_local_full_width_weight']
    pins = dict(release_id='lfw-capture-v2', source_commit='f' * 40, binary_path=str(binary), binary_sha256=sha(binary), independent_source_review=dict(report_sha256='b' * 64, verdict='CLEAR', source_commit='f' * 40),
                lane_locks=['/tmp/a.lock', '/tmp/b.lock'], comparator=dict(path=str(COMPARATOR), sha256=sha(COMPARATOR)), input_files={'noisy.mrcs': sha(base / 'input/noisy.mrcs'), 'noisy.star': sha(base / 'input/noisy.star')},
                baseline=dict(dir=str(base), argv=argv, environment={'OMP_NUM_THREADS': '2', 'MC_EXPERIMENT_CCF_DC_ARM': 'both', 'PYTHONDONTWRITEBYTECODE': '1'}, products={n: sha(base / 'output' / n) for n in PRODUCTS}, other_files={}))
    (root / D.PINS_NAME).write_text(json.dumps(pins))
    shutil.copy(HERE / 'capture_witness.py', root / 'prep/capture_witness.py')
    D.pre_checks = lambda p: None; D.admission = lambda d, p, label: None; D.TIME_WRAPPER = lambda d: []; D.JOB_TIMEOUT = 60
    write_release(root, pins)
    return root, pins, knobs_path
GRANT = lambda pins: dict(granted_by='parent', utc='2026-10-27T02:00:00Z', cpus='32-47', lane_locks=sorted(pins['lane_locks']), jobs=['OFF', 'ON'], receipt_sha256='c' * 64)
def write_release(root, pins, grant='ok', **over):
    r = dict(release_id=pins['release_id'], pins_sha256=sha(root / D.PINS_NAME), driver_sha256=sha(HERE / D.DRIVER_NAME), witness_sha256=sha(HERE / 'capture_witness.py'), source_commit=pins['source_commit'],
             binary_sha256=pins['binary_sha256'], independent_review_report_sha256='b' * 64, jobs_authorized=['OFF', 'ON'], fresh_resource_grant=GRANT(pins) if grant == 'ok' else grant)
    r.update(over); (root / 'PARENT_RELEASE.json').write_text(json.dumps(r))
def stop_reason(root):
    p = root / 'evidence/STOP.json'; return json.loads(p.read_text())['reason'] if p.exists() else None
def run_main(root):
    D.PINS_SHA0 = None
    try: return D.main()
    except D.Refuse as e: return str(e)

# ---------------- S0 positive full run
root, pins, kp = make_env('s0'); rc = run_main(root)
assert rc == 0, rc
nc = json.loads((root / 'evidence/NATIVE_COMPLETE.json').read_text()); inv = json.loads((root / 'evidence/runs/ON/capture-inventory.json').read_text())
assert nc['capture_inventory_files'] == inv['count'] == 606, (nc['capture_inventory_files'], inv['count'])
assert nc['capture_inventory_sha256'] == sha(root / 'evidence/runs/ON/capture-inventory.json') and not (root / 'evidence/runs/ON/capture/capture-inventory.json').exists(); ok('S0 positive: both jobs, witnesses, 606-file sealed inventory outside the capture tree bound in NATIVE_COMPLETE')
run_on = json.loads((root / 'evidence/runs/ON/RUN.json').read_text())
assert run_on['binary_sha256_before_launch'] == run_on['binary_sha256_after_run'] == run_on['binary_sha256_pinned'] and run_on['sampling']['state'] in ('UNOBSERVED', 'PARTIAL', 'OBSERVED'); ok('S0 RUN receipt records the binary hash before/after and an explicit sampling state (%s)' % run_on['sampling']['state'])
assert not (root / 'evidence/STOP.json').exists() and not (root / 'evidence/runs/OFF/capture').exists(); ok('S0 no STOP, no capture directory in OFF')

# ---------------- C1 negatives (each must STOP before the ON launch and leave no ON RUN receipt)
def hooked(name, after_off, knobs=None):
    root, pins, kp = make_env(name, knobs); orig = D.identity
    def ident(a, b, d, p, tag):
        orig(a, b, d, p, tag)
        if tag.startswith('OFF'): after_off(root, pins)
    D.identity = ident
    try: res = run_main(root)
    finally: D.identity = orig
    return root, res
def swap_binary(root, pins): open(pins['binary_path'], 'ab').write(b'#')
root, res = hooked('c1_binary_swap', swap_binary)
assert 'binary differs from the pins at launch' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists() and not (root / 'evidence/runs/ON/capture').exists() and 'binary differs' in stop_reason(root); ok('C1 binary swapped between OFF and ON: STOP before the ON launch')
root, res = hooked('c1_input_swap', lambda r, p: (r / 'native-input/noisy.star').write_bytes(b'X' * 40))
assert 'staged input differs from the pins at launch' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists() and 'staged input differs' in stop_reason(root); ok('C1 staged input swapped after OFF: STOP before the ON launch')
root, res = hooked('c1_extra_file', lambda r, p: (r / 'native-input/extra').write_bytes(b'x'))
assert 'scope differs' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists(); ok('C1 extra staged file: STOP before ON')
def symlink_in(root, pins):
    q = root / 'native-input/noisy.star'; q.unlink(); q.symlink_to(root / 'base/noisy/ON/input/noisy.star')
root, res = hooked('c1_symlink', symlink_in)
assert 'staged input differs from the pins at launch' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists(); ok('C1 staged input replaced by a symlink to the right bytes: STOP before ON')
root, res = hooked('c1_pins_changed', lambda r, p: (r / D.PINS_NAME).write_text((r / D.PINS_NAME).read_text() + ' '))
assert 'pins file changed' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists(); ok('C1 pins file changed after start: STOP before ON')
root, res = hooked('c1_source_changed', lambda r, p: (r / 'base/noisy/ON/input/noisy.mrcs').write_bytes(b'Z' * 300))
assert 'staging source' in str(res) and not (root / 'evidence/runs/ON/RUN.json').exists(); ok('C1 staging source (baseline input) changed: STOP before ON')
root, pins, kp = make_env('c1_postrun', {'selfmodify': 'OFF'}); res = run_main(root)
assert 'binary changed around the run' in str(res) and (root / 'evidence/runs/OFF/INVALID.json').exists() and (root / 'evidence/runs/OFF/RUN.json').exists() and not (root / 'evidence/runs/ON').exists(); ok('C1 binary changed during OFF: run retained and marked INVALID, ON never launched')
rr = json.loads((root / 'evidence/runs/OFF/RUN.json').read_text()); assert rr['binary_sha256_after_run'] != rr['binary_sha256_pinned']; ok('C1 retained RUN.json carries the differing post-run hash')
root, pins, kp = make_env('c1_pre'); D.PINS_SHA0 = sha(root / D.PINS_NAME); (root / 'native-input').mkdir(exist_ok=True)
expect_refuse('C1 launch_checks with no staged input', lambda: D.launch_checks(pins), 'staged native-input scope differs')

# ---------------- C2 negatives
def prep_on(name):
    root, pins, kp = make_env(name); on = root / 'evidence/runs/ON'; on.mkdir(parents=True); shutil.copytree(GOOD_CAP, on / 'capture'); (on / 'output').mkdir(); (on / 'output/noisy.log').write_text(ON_LOG)
    return root, on
root, on = prep_on('c2_a'); cov = CW.run_all(on / 'capture', ON_LOG, D.WO.weight_map(42), D.WO.weight_map(22))['coverage']
assert D.expected_capture_files(cov) == 606 == 2 + sum(c['files'] for c in cov.values()); ok('C2 closed-form file count (2 root files + 34 + 134n per patch) equals the coverage count: 606 (604 in the two patches)')
D.EVID.mkdir(exist_ok=True); sha_, n = D.seal_capture(on, dict(coverage=cov)); assert n == 606 and not list((on / 'capture').glob('capture-inventory*')); ok('C2 seal writes the inventory outside the capture tree')
bad = copy.deepcopy(cov); bad['104,15']['executed_iterations'] = 3; root, on = prep_on('c2_b')
expect_refuse('C2 count crosscheck fails when coverage claims another iteration count', lambda: D.seal_capture(on, dict(coverage=bad)), 'capture file count')
root, on = prep_on('c2_c'); (on / 'capture/patch-62-79/iter1-frame0-real-map.bin').unlink()
expect_refuse('C2 a missing capture file is a count mismatch', lambda: D.seal_capture(on, dict(coverage=cov)), 'capture file count')
root, on = prep_on('c2_d'); (on / 'capture/link').symlink_to(on / 'capture/session.json')
expect_refuse('C2 a symlink inside the capture tree', lambda: D.inventory(on / 'capture'), 'symlink or non-regular')
root, on = prep_on('c2_e'); os.mkfifo(on / 'capture/fifo')
expect_refuse('C2 a non-regular entry (FIFO) inside the capture tree', lambda: D.inventory(on / 'capture'), 'symlink or non-regular')
root, on = prep_on('c2_f'); D.EVID.mkdir(exist_ok=True); orig_write = D.write
def tamper_write(p, x):
    orig_write(p, x)
    if Path(p).name == 'capture-inventory.json': b = bytearray((on / 'capture/patch-62-79/weights.bin').read_bytes()); b[0] ^= 1; (on / 'capture/patch-62-79/weights.bin').write_bytes(bytes(b))
D.write = tamper_write
try: expect_refuse('C2 a capture file altered while it is being inventoried', lambda: D.seal_capture(on, dict(coverage=cov)), 'changed while it was being inventoried')
finally: D.write = orig_write
# alteration after the seal, before completion: the final check in main
root, pins, kp = make_env('c2_g'); orig_seal = D.seal_capture
def seal_then_tamper(on, w):
    r = orig_seal(on, w); (on / 'capture/session.json').write_text((on / 'capture/session.json').read_text().replace('witness-test-movie', 'xxxxxxxxxxxxxxxxx')); return r
D.seal_capture = seal_then_tamper
try: res = run_main(root)
finally: D.seal_capture = orig_seal
assert 'differs from its sealed inventory at completion' in str(res) and not (root / 'evidence/NATIVE_COMPLETE.json').exists(); ok('C2 capture altered after the seal: no NATIVE_COMPLETE')

# ---------------- N1 malformed witness inputs become STOP records
def malformed(name, mutate):
    root, on = prep_on('n1_' + name); D.EVID.mkdir(exist_ok=True); mutate(on / 'capture')
    expect_refuse('N1 ' + name, lambda: D.run_witness_stage(on, D.WO.weight_map(42), D.WO.weight_map(22)), 'WITNESS')
    assert stop_reason(root).startswith('WITNESS') and not (on / 'capture-witnesses.json').exists()
def jedit(p, fn):
    j = json.loads(p.read_text()); j = fn(j); p.write_text(json.dumps(j))
malformed('COMPLETE bytes null', lambda c: jedit(c / 'COMPLETE.json', lambda j: {**j, 'bytes_before_complete': None}))
malformed('patch-files without files', lambda c: jedit(c / 'patch-104-15/patch-files.json', lambda j: {}))
malformed('session as list', lambda c: jedit(c / 'session.json', lambda j: [j]))
malformed('weights.json as list', lambda c: jedit(c / 'patch-62-79/weights.json', lambda j: [j]))
malformed('peak.json as list', lambda c: jedit(c / 'patch-104-15/iter1-frame2-peak.json', lambda j: [j]))
malformed('patch.json as list', lambda c: jedit(c / 'patch-62-79/patch.json', lambda j: [j]))
malformed('alignment-complete as list', lambda c: jedit(c / 'patch-62-79/alignment-complete.json', lambda j: [j]))
malformed('fft-config as list', lambda c: jedit(c / 'patch-104-15/fft-config.json', lambda j: [j]))
malformed('stop file iterations string', lambda c: jedit(c / 'patch-104-15/alignment-complete.json', lambda j: {**j, 'iterations': 'two'}))
root, on = prep_on('n1_log_missing'); D.EVID.mkdir(exist_ok=True); (on / 'output/noisy.log').unlink()
expect_refuse('N1 missing noisy.log', lambda: D.run_witness_stage(on, D.WO.weight_map(42), D.WO.weight_map(22)), 'WITNESS')
root, pins, kp = make_env('n1_unexpected'); orig_ws = D.run_witness_stage; D.run_witness_stage = lambda *a: (_ for _ in ()).throw(AttributeError('boom'))
try: res = run_main(root)
finally: D.run_witness_stage = orig_ws
assert 'UNEXPECTED AttributeError' in str(res) and 'UNEXPECTED' in stop_reason(root) and not (root / 'evidence/NATIVE_COMPLETE.json').exists(); ok('N1 an unexpected exception in the campaign becomes a STOP record, no completion')

# ---------------- N2 grant format and release binding
root, pins, kp = make_env('n2'); g = GRANT(pins)
assert D.grant_format_ok(g, pins); ok('N2 well-formed grant accepted')
for label, bad in [('truthy string', 'stale grant'), ('integer 1', 1), ('only cpus 0-63', {'cpus': '0-63'}), ('bad utc', {**g, 'utc': 'yesterday'}), ('wrong cpus', {**g, 'cpus': '0-63'}), ('wrong locks', {**g, 'lane_locks': ['/tmp/a.lock']}),
                   ('no receipt', {k: v for k, v in g.items() if k != 'receipt_sha256'}), ('short receipt', {**g, 'receipt_sha256': 'abc'}), ('jobs ON only', {**g, 'jobs': ['ON']}), ('empty granted_by', {**g, 'granted_by': ' '}), ('null', None)]:
    write_release(root, pins, grant=bad); expect_refuse('N2 grant ' + label, lambda: D.parent_release(pins), 'structured fresh_resource_grant')
write_release(root, pins); D.parent_release(pins); ok('N2 release with a structured grant accepted by the format check (the actual grant is bound externally by the parent)')
for key, val in [('driver_sha256', '0' * 64), ('pins_sha256', '0' * 64), ('binary_sha256', '0' * 64), ('independent_review_report_sha256', '0' * 64), ('jobs_authorized', ['ON']), ('release_id', 'lfw-capture-v1'), ('witness_sha256', '0' * 64), ('source_commit', '0' * 40)]:
    write_release(root, pins, **{key: val}); expect_refuse('N2 release binding ' + key, lambda: D.parent_release(pins), 'does not bind')
(root / 'PARENT_RELEASE.json').unlink(); expect_refuse('N2 no PARENT_RELEASE: HELD', lambda: D.parent_release(pins), 'HELD')
root, pins, kp = make_env('n2_main_held'); (root / 'PARENT_RELEASE.json').unlink(); res = run_main(root)
assert 'HELD' in str(res) and not D.EVID.exists() and not (root / 'native-input').exists(); ok('N2 main without a release launches nothing and creates no evidence directory')

# ---------------- N3 sampling summary
def samples(lines):
    p = tmp0 / 'samples.jsonl'; p.write_text(''.join(json.dumps(x) + '\n' for x in lines)); return D.sampling_summary(p)
prod = lambda allowed, th: dict(pid=1, name='motioncorr', allowed=allowed, threads=th, rss='1 kB')
assert samples([])['state'] == 'UNOBSERVED' and D.sampling_summary(tmp0 / 'nonexistent')['state'] == 'UNOBSERVED'; ok('N3 no samples: UNOBSERVED, no assertion')
s = samples([dict(monotonic=0, processes=[]), dict(monotonic=1, processes=[prod('32-47', 1)])]); assert s['state'] == 'PARTIAL' and s['n_samples'] == 2 and s['n_samples_naming_producer'] == 1 and s['n_empty_samples'] == 1; ok('N3 one empty and one producer sample: PARTIAL with explicit counts')
s = samples([dict(monotonic=0, processes=[prod('32-47', 1)]), dict(monotonic=1, processes=[prod('32-47', 3)])]); assert s['state'] == 'OBSERVED' and s['max_threads_of_producer'] == 3 and s['distinct_allowed_cpu_lists_of_producer'] == ['32-47']; ok('N3 all samples name the producer: OBSERVED, values recorded without a universal assertion')
s = samples([dict(monotonic=0, processes=[dict(pid=2, name='time', allowed='32-47', threads=1, rss='')])]); assert s['state'] == 'UNOBSERVED' and s['n_samples'] == 1; ok('N3 only the wrapper observed: UNOBSERVED')

# ---------------- N4 timeout and SIGTERM cleanup (fake sleeping children)
root, pins, kp = make_env('n4_timeout', {'sleep': 30}); D.JOB_TIMEOUT = 1; t0 = time.time(); res = run_main(root)
assert 'timed out' in str(res) and time.time() - t0 < 20 and json.loads((root / 'evidence/runs/OFF/RUN.json').read_text())['timed_out'] is True and not (root / 'evidence/runs/ON').exists(); ok('N4 a producer over the timeout is killed (owned group), retained as timed_out, and ON is not launched')
D.JOB_TIMEOUT = 60
child = tmp0 / 'n4_child.py'; child.write_text('import time, os, sys\nopen(sys.argv[1], "w").write(str(os.getpid()))\ntime.sleep(60)\n')
runner = tmp0 / 'n4_runner.py'
runner.write_text(textwrap.dedent(f'''\
    import sys, signal; sys.dont_write_bytecode = True; sys.path[:0] = [{str(HERE)!r}, {str(HERE.parent / 'scripts')!r}]
    from pathlib import Path
    import run_capture_fw_v2 as D
    D.TIME_WRAPPER = lambda d: []
    def on_term(s, f): raise D.Terminated('SIGTERM')
    signal.signal(signal.SIGTERM, on_term)
    d = Path(sys.argv[1]); print('ready', flush=True)
    D.launch([sys.executable, {str(child)!r}, str(d / 'child.pid')], str(d), dict(), d, 60)
'''))
w = tmp0 / 'n4w'; w.mkdir()
p = subprocess.Popen([sys.executable, '-B', str(runner), str(w)], stdout=subprocess.PIPE, text=True, start_new_session=True); p.stdout.readline()
for _ in range(100):
    if (w / 'child.pid').exists() and (w / 'child.pid').read_text(): break
    time.sleep(.05)
cpid = int((w / 'child.pid').read_text()); os.kill(cpid, 0); p.send_signal(signal.SIGTERM); p.wait(timeout=20)
time.sleep(.5)
try: os.kill(cpid, 0); alive = True
except ProcessLookupError: alive = False
assert not alive and p.returncode != 0; ok('N4 SIGTERM to the driver kills and reaps the owned producer process group')
# the group kill reaches a grandchild too (the time wrapper case)
gc = tmp0 / 'n4_gc.py'; gc.write_text('import subprocess, sys, time, os\nq = subprocess.Popen([sys.executable, "-c", "import os,time,sys; open(sys.argv[1],\\"w\\").write(str(os.getpid())); time.sleep(60)", sys.argv[1]])\ntime.sleep(60)\n')
runner2 = tmp0 / 'n4_runner2.py'; runner2.write_text(runner.read_text().replace(str(child), str(gc)))
w2 = tmp0 / 'n4w2'; w2.mkdir(); p = subprocess.Popen([sys.executable, '-B', str(runner2), str(w2)], stdout=subprocess.PIPE, text=True, start_new_session=True); p.stdout.readline()
for _ in range(100):
    if (w2 / 'child.pid').exists() and (w2 / 'child.pid').read_text(): break
    time.sleep(.05)
gpid = int((w2 / 'child.pid').read_text()); p.send_signal(signal.SIGTERM); p.wait(timeout=20); time.sleep(.5)
try: os.kill(gpid, 0); alive = True
except ProcessLookupError: alive = False
assert not alive; ok('N4 the grandchild of the producer wrapper dies with the group')

shutil.rmtree(tmp0)
print('PASS %d checks' % len(passed)); [print(' -', x) for x in passed]
