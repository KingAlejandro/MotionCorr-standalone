"""Guard-removal controls: weaken one v3 guard in a scratch copy and require the intended tests to fail (scratch only)."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(__file__).resolve().parent.parent
PY = sys.executable
MUT = {
 'arm_check': ("    if r.get('arm') != arm:", "    if False:", ['missing arm', 'ON receipt in OFF slot', 'OFF receipt in ON slot', 'swapped dirs: OFF slot holds ON', 'swapped dirs: ON slot holds OFF']),
 'flag_count': ("    if argv.count(FLAG) != (1 if arm == 'ON' else 0):", "    if False:", ['missing flag on ON', 'flag on OFF', 'duplicate flag on ON']),
 'env_observed': ("    if observed != want:", "    if False:", ['observed child env has extra OMP_PROC_BIND', 'observed child env value differs']),
 'inventory_equality': ("    if set(pub) != set(found):", "    if False:", ['unlisted extra output file (receipt unchanged)', 'listed output file deleted']),
 'baseline_names': ("    if sorted(pub) != expected['expected_output_names']:", "    if False:", ['extra output file even when listed in the receipt', 'required output absent from disk and receipt']),
 'witness_count': ("    if len(marked) != expected['expected_witness_lines'] or", "    if False and ", ['8 witness lines on 3x3 ON', '10 witness lines on 3x3 ON', '0 witness lines on 3x3 ON', '1 witness line on global-only ON', '1 witness line on global-only OFF', '1 witness line on 3x3 OFF']),
 'witness_format': ("        if ln != WITNESS_LINE:", "        if False:", ['witness x_norm 22', 'witness pnx 41', 'witness nfx 21', 'witness x_norm 42.0 text', 'witness spaced variant', 'witness no leading space']),
 'runtime_hash': ("    rt = _bound_file(d, 'runtime.json', r.get('runtime'), 'RUNTIME')", "    rt = (d / 'runtime.json').read_bytes()", ['runtime.json tampered to another valid model (receipt stale)']),
 'roi_check': ("    if list(meta['roi']) != FIXED_ROI:", "    if False:", ['in-bounds wrong ROI [0,96,0,128]']),
 'star_case': ("    if _star_movie_stem(star_path) != case:", "    if False:", ['affine STAR in noisy run refused at scoring']),
 'run_dir': ("    if d.resolve() != (Path(evidence_root) / case / arm).resolve():", "    if False:", ['copied run dir with a self-consistent receipt']),
}
out = {}
for name, (old, new, expect_fail) in MUT.items():
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v3-mut-') as t:
        t = Path(t)
        (t / 'tests').mkdir()
        for f in ['score_fields_v2.py', 'score_fields_v3.py', 'ADMISSION_DRAFT_v3.json', 'COMMANDS_DRAFT_v3.json', 'COMMANDS_DRAFT.json']:
            shutil.copy(PILOT / f, t / f)
        shutil.copy(PILOT / 'tests/test_score_fields_v3.py', t / 'tests/test_score_fields_v3.py')
        src = (t / 'score_fields_v3.py').read_text()
        assert src.count(old) == 1, name
        (t / 'score_fields_v3.py').write_text(src.replace(old, new))
        p = subprocess.run([PY, '-B', str(t / 'tests/test_score_fields_v3.py'), str(t / 'r.json')], capture_output=True, text=True)
        failed = [l[5:].split(' :: ')[0] for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        killed = all(e in failed for e in expect_fail)
        out[name] = {'killed_all_intended': killed, 'intended': expect_fail, 'failed_tests': failed, 'exit': p.returncode}
        print(('KILLED ' if killed else 'SURVIVED ') + name, '| failed:', len(failed))
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
sys.exit(0 if all(v['killed_all_intended'] for v in out.values()) else 1)
