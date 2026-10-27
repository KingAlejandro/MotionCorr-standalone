"""Focused local fake tests of the frozen capture driver/witness (no movie, pixels, SSH, build or producer).
Usage: review_tests.py PACKAGE_DIR GENERATED_CAPTURE_DIR RESULT_JSON
Imports byte-identical copies of the pinned driver/witness/oracle from a private dir; ROOT/EVID are redirected to a private temp dir."""
import ast, copy, hashlib, json, shutil, sys, tempfile
from pathlib import Path
pkg, gen, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
work = Path(tempfile.mkdtemp(prefix='rv-')); mod = work / 'mod'; mod.mkdir()
for src in (pkg / 'driver/run_capture_fw.py', pkg / 'driver/capture_witness.py', pkg / 'scripts/weight_oracle.py'): shutil.copyfile(src, mod / src.name)
pins = json.loads((pkg / 'driver/CAPTURE_RUN_PINS.json').read_text())
assert all(sha(mod / n) == pins['prep_files'][n] for n in ('run_capture_fw.py', 'capture_witness.py', 'weight_oracle.py'))
sys.dont_write_bytecode = True; sys.path.insert(0, str(mod))
import run_capture_fw as D, capture_witness as C, weight_oracle as O
res = {}

# T1 commands derived exactly as run() derives them equal the frozen COMMANDS_CAPTURE.json (both jobs)
cmds = json.loads((pkg / 'driver/COMMANDS_CAPTURE.json').read_text())
for job in cmds['jobs']:
    d = D.EVID / 'runs' / job['label']; cmd = list(pins['baseline']['argv']); cmd[0] = pins['binary_path']; cmd[cmd.index('--o') + 1] = str(d / 'output')
    env = dict(pins['baseline']['environment']); env.pop('MC_DIAG_MODEL_OUT', None); env.update(MC_DIAG_MODEL_OUT=str(d / 'runtime.json'), PATH='/usr/bin:/bin')
    if job['label'] == 'ON': env['MC_DIAG_LOCAL_CCF_DIR'] = str(d / 'capture')
    res[f'T1_commands_{job["label"]}_equal_frozen'] = (cmd == job['argv'] and env == job['environment'])

# T2 parent_release: any truthy fresh_resource_grant is accepted (no type/freshness/lane binding)
root = work / 'root'; root.mkdir(); D.ROOT = root; D.EVID = root / 'evidence'
(root / 'RUN_PINS.json').write_bytes((pkg / 'driver/CAPTURE_RUN_PINS.json').read_bytes())
D.HERE = mod
base = dict(release_id=pins['release_id'], pins_sha256=sha(root / 'RUN_PINS.json'), driver_sha256=sha(mod / 'run_capture_fw.py'), witness_sha256=sha(mod / 'capture_witness.py'),
            source_commit=pins['source_commit'], binary_sha256=pins['binary_sha256'], independent_review_report_sha256=pins['independent_source_review']['report_sha256'], jobs_authorized=['OFF', 'ON'])
def pr(grant):
    r = dict(base); r['fresh_resource_grant'] = grant; (root / 'PARENT_RELEASE.json').write_text(json.dumps(r))
    try: D.parent_release(pins); return 'ACCEPTED'
    except D.Refuse as e: return 'REFUSED: ' + str(e)[:60]
res['T2_grant_absent'] = pr(None); res['T2_grant_false'] = pr(False)
res['T2_grant_string_stale'] = pr('stale grant from 2026-10-20'); res['T2_grant_int_1'] = pr(1); res['T2_grant_wrong_cpus'] = pr({'cpus': '0-63'})
r = dict(base, fresh_resource_grant={'utc': 'x'}, jobs_authorized=['ON', 'OFF']); (root / 'PARENT_RELEASE.json').write_text(json.dumps(r))
try: D.parent_release(pins); res['T2_jobs_reordered'] = 'ACCEPTED'
except D.Refuse: res['T2_jobs_reordered'] = 'REFUSED'
(root / 'PARENT_RELEASE.json').unlink()

# T3 witness failures that are not Stop escape main()'s `except CW.Stop` (traceback, no STOP.json); real generated capture mutated
o42, o22 = O.weight_map(42), O.weight_map(22)
def esc(name, mutate, fn):
    d = work / name; shutil.copytree(gen, d); mutate(d)
    try: fn(d); res['T3_' + name] = 'PASSED (no stop)'
    except C.Stop as e: res['T3_' + name] = 'Stop ' + e.name
    except Exception as e: res['T3_' + name] = 'ESCAPES as ' + type(e).__name__
def setj(p, k, v):
    j = json.loads(p.read_text()); j[k] = v; p.write_text(json.dumps(j))
esc('positive', lambda d: None, lambda d: C.check_coverage(d))
esc('complete_bytes_null', lambda d: setj(d / 'COMPLETE.json', 'bytes_before_complete', None), C.check_coverage)
esc('patch_files_no_key', lambda d: (d / 'patch-104-15/patch-files.json').write_text('{"names": []}'), C.check_coverage)
esc('session_is_list', lambda d: (d / 'session.json').write_text('[]'), C.check_session)
esc('weights_json_is_list', lambda d: (d / 'patch-104-15/weights.json').write_text('[]'), lambda d: C.check_weights(d, o42, o22))
esc('peak_json_is_list', lambda d: (d / 'patch-104-15/iter1-frame0-peak.json').write_text('[]'), C.check_coverage)

# T4 static: per-job admission no longer re-hashes binary/inputs (the reviewed run_capture.py admission did); run() records but never checks the binary hash
tree = ast.parse((mod / 'run_capture_fw.py').read_text()); fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
calls = lambda f: sorted({c.func.id for c in ast.walk(fns[f]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)})
old = (pkg.parents[1] / 'local_ccf_capture_20261026/scripts/run_capture.py').read_text()
res['T4_old_admission_rehashed_binary_and_inputs'] = "check(sha(pins['binary_path'])==pins['binary_sha256'],'binary changed')" in old and "'input changed: '" in old
res['T4_new_admission_calls_sha'] = 'sha' in calls('admission')
res['T4_new_run_checks_binary_against_pins'] = "pins['binary_sha256']" in ast.get_source_segment((mod / 'run_capture_fw.py').read_text(), fns['run'])
res['T4_main_rehashes_staged_input_before_ON'] = ast.get_source_segment((mod / 'run_capture_fw.py').read_text(), fns['main']).count("sha(ROOT / 'native-input'") > 1

# T5 static: no capture per-file hash inventory and no check of the monitor receipt
src = (mod / 'run_capture_fw.py').read_text()
res['T5_driver_hashes_capture_files'] = any(s in src for s in ("(on / 'capture').rglob", "capture').rglob", 'capture-inventory'))
res['T5_writer_records_hashes'] = any('sha256' in p.read_text() for p in [gen / 'COMPLETE.json', gen / 'session.json', gen / 'patch-104-15/patch-files.json'])
res['T5_driver_reads_actual_resources_after_run'] = src.count('actual-resources.jsonl') > 1

# T6 negative-control count vs the README claim of 18
neg = (pkg / 'receipts/negctl_precheck.txt').read_text().count('REFUSED as required'); res['T6_negctl_refused_count'] = neg
res['T6_readme_claims_18'] = '18 negative controls' in (pkg / 'README.md').read_text()
shutil.rmtree(work)
out.write_text(json.dumps(res, indent=1) + '\n'); print(json.dumps(res, indent=1))
