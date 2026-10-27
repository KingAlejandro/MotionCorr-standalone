"""Reviewer guard-removal controls for score_fields_v3 guards NOT covered by the author's 11 mutants.

Each mutant weakens one guard in a scratch copy of the pilot files and runs the author's unchanged test file there.
KILLED = every intended test reports FAIL (wrong code, wrong exception or admission all count as FAIL in expect_code).
SURVIVED = the guard is shadowed by another guard for every test that names it (redundant or not isolated).
usage: python -B -I extra_mutants.py PILOT_DIR OUT.json
"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(sys.argv[1]).resolve()
PY = sys.executable
MUT = {
 'exit': ("    if not _is_int(r.get('exit')) or r['exit'] != 0:", "    if False:", ['exit 1 with a complete tap', 'exit True', 'exit "0"']),
 'receipt_case': ("    if r.get('case') != case:", "    if False:", ['case swapped in receipt']),
 'receipt_run_dir_string': ("    if r.get('run_dir') != str(d.resolve()):", "    if False:", ['receipt run_dir names another directory']),
 'binary': ("    if r.get('binary_sha256') != expected['binary_sha256'] or not _hex(r.get('binary_sha256')):", "    if False:", ['wrong binary sha in receipt', 'uppercase binary sha in receipt']),
 'argv_equality': ("    if argv != expected['argv']:", "    if False:", ['extra unknown argv', 'changed argv value', 'argv[0] left as placeholder']),
 'cwd': ("    if r.get('cwd') != expected['cwd'] or Path(expected['cwd']).resolve() != (d / 'input').resolve():", "    if False:", ['cwd mismatch']),
 'input_names': ("    if names != sorted(expected['input_files']):", "    if False:", ['extra file in staged cwd', 'missing staged movie']),
 'input_bytes': ("        if p.is_symlink() or not p.is_file() or pin is None or p.stat().st_size != pin['bytes'] or sha(p) != pin['sha256']:", "        if False:", ['staged input byte tamper']),
 'env_declared': ("    if env != expected['environment']:", "    if False:", ['env value changed', 'env var missing', 'env var extra']),
 'publication_hash': ("        _bound_file(d / 'output', rel, pub[rel], 'PUBLICATION_HASH')", "        pass", ['listed output byte changed']),
 'stdout': ("    _bound_file(d, 'stdout.log', r.get('stdout'), 'STDOUT')", "    pass", ['stdout.log tampered (receipt stale)', 'stdout.log missing']),
 'log_case': ("    if lines[0] != 'Working on %s.mrcs with 2 thread(s).' % case:", "    if False:", ['log of another case']),
 'truth_name': ("    if Path(truth_path).name != tname:", "    if False:", ['truth file of another case name']),
 'star_file_name': ("    if Path(star_path).name != case + '.star':", "    if False:", ['STAR file name of another case']),
 'manifest_pin': ("    if sha(fx / 'MANIFEST.json') != MANIFEST_SHA256:", "    if False:", ['manifest hash swap']),
 'runtime_geometry': ("    if type(model.get('local_enabled')) is not bool or g.shape != (FIXED_RECIPE[0], 2) or cx.shape != (18,) or cy.shape != (18,):", "    if False:", ['runtime 17 coefficients with matching receipt hash', 'runtime local_enabled integer with matching receipt hash', 'runtime 4 frames with matching receipt hash']),
 'runtime_nonfinite_numpy': ("    if not all(np.isfinite(a).all() for a in (g, cx, cy)):", "    if False:", ['runtime NaN with matching receipt hash']),
 'admit_placeholder': ("    if any(isinstance(a, str) and a.startswith('<') and a.endswith('>') for a in expected['argv']) or not _hex(expected.get('binary_sha256')):", "    if False:", ['unresolved draft row not admissible']),
 'output_symlink': ("            if p.is_symlink():\n                _fail('INVENTORY', 'symlink under output: ' + name)", "            pass", ['symlink in output']),
 'publication_escape': ("        if k.startswith('/') or '..' in Path(k).parts:", "        if False:", ['publication path escapes output']),
 'witness_grid_recheck': ("or expected['expected_witness_lines'] != witness_expected(arm, expected['patch_grid'])", "or False", []),
}
out = {}
for name, (old, new, expect_fail) in MUT.items():
    with tempfile.TemporaryDirectory(prefix='mc-lfw-r2-mut-') as t:
        t = Path(t)
        (t / 'tests').mkdir()
        for f in ['score_fields_v2.py', 'score_fields_v3.py', 'ADMISSION_DRAFT_v3.json', 'COMMANDS_DRAFT_v3.json', 'COMMANDS_DRAFT.json']:
            shutil.copy(PILOT / f, t / f)
        shutil.copy(PILOT / 'tests/test_score_fields_v3.py', t / 'tests/test_score_fields_v3.py')
        src = (t / 'score_fields_v3.py').read_text()
        assert src.count(old) == 1, name
        (t / 'score_fields_v3.py').write_text(src.replace(old, new))
        p = subprocess.run([PY, '-B', '-I', str(t / 'tests/test_score_fields_v3.py'), str(t / 'r.json')], capture_output=True, text=True)
        failed = [l[5:].split(' :: ')[0] for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        failed_detail = [l[5:] for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        killed = bool(expect_fail) and all(e in failed for e in expect_fail)
        out[name] = {'killed_all_intended': killed, 'intended': expect_fail, 'failed_tests': failed_detail,
                     'exit': p.returncode, 'stderr_tail': p.stderr[-400:]}
        print(('KILLED ' if killed else 'SURVIVED ') + name, '| failed:', len(failed), flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n')
