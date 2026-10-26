"""Guard-removal controls for pair_decision_v4 (scratch copies only). A guard that the suite shows to be shadowed by another guard is
reported as SHADOWED (expected survivors are declared up front), never claimed as killed."""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(__file__).resolve().parent.parent
PY = sys.executable
# (file, old, new, [test-name fragments that must fail], expected_shadowed)
M = {
 'anchor_admission': ('pair_decision_v4.py', "    if _sha_bytes(ab) != ADMISSION_V3_SHA256:", "    if False:", ['altered anchored admission file'], False),
 'anchor_commands': ('pair_decision_v4.py', "    if _sha_bytes(cb) != COMMANDS_V3_SHA256:", "    if False:", ['hand-edited commands'], False),
 'held_gate': ('pair_decision_v4.py', "        if need_launch:", "        if False:", ['real HELD admission cannot satisfy pre_ON_gate', 'null launch field', 'HELD status in an otherwise filled'], False),
 'tool_pins': ('pair_decision_v4.py', "            V3.verify_tool_pins(self.adm, roots)", "            pass", ['tool pins verified before use'], False),
 'decision_dir_overlap': ('pair_decision_v4.py', "        if d == o or d.is_relative_to(o) or o.is_relative_to(d):", "        if False:", ['decision_dir inside a run directory'], False),
 'baseline_inventory': ('pair_decision_v4.py', "    if set(disk) != set(pins):", "    if False:", ['baseline extra file', 'baseline file missing'], False),
 'baseline_bytes': ('pair_decision_v4.py', "        if disk[k] != pins[k]:", "        if False:", ['baseline byte changed (pin kept)'], False),
 'baseline_symlink': ('pair_decision_v4.py', "            if (Path(dirpath) / n).is_symlink():", "            if False:", ['baseline file replaced by a symlink'], False),
 'off_raw_runtime': ('pair_decision_v4.py', "        if (off / rel).stat().st_size != pins[rel][0] or _sha_file(off / rel) != pins[rel][1]:", "        if False:", ['OFF runtime differs from the retained baseline bytes'], False),
 # the real comparator exits 1 whenever it reports DIFFERENT, so the rc guard and the verdict guard shadow each other; each alone is declared shadowed
 'comparator_verdict_only': ('pair_decision_v4.py', "    if j.get('verdict') != 'IDENTICAL' or j.get('n_gated_differing') != 0 or j.get('root_a')", "    if False and j.get('root_a')", [], True),
 'comparator_rc_only': ('pair_decision_v4.py', "    if cmdj['returncode'] != 0 or not jp.is_file():", "    if not jp.is_file():", [], True),
 'comparator_rc_and_verdict': ('pair_decision_v4.py', ["    if cmdj['returncode'] != 0 or not jp.is_file():", "    if j.get('verdict') != 'IDENTICAL' or j.get('n_gated_differing') != 0 or j.get('root_a')"], ["    if not jp.is_file():", "    if False and j.get('root_a')"], ['comparator detects MRC header', 'comparator detects MRC payload', 'comparator detects EPS', 'comparator detects corrected_micrographs STAR', 'comparator detects a file-inventory'], False),
 'pre_on_binding': ('pair_decision_v4.py', "    if rec.get('bound') != bound or rec.get('binding_sha256') != _h(bound) or _h(rec['bound']) != rec['binding_sha256']:", "    if False:", ['tampered pre-ON record', 'record bound to a different OFF byte', 'retained comparator JSON altered', 'edited after the gate'], False),
 'pre_on_status': ('pair_decision_v4.py', "    if rec.get('schema') != PRE_ON_SCHEMA or rec.get('status') != 'PASS':", "    if False:", ['pre-ON record status not PASS'], False),
 'pre_on_present': ('pair_decision_v4.py', "    if not rp.is_file():", "    if False:", ['absent pre-ON record'], False),
 'global_bits': ('pair_decision_v4.py', "    if fo['global_bits'] != fn_['global_bits']:", "    if False:", ['1 ulp'], False),
 'global_star': ('pair_decision_v4.py', "    if fo['global_star_block'] != fn_['global_star_block']:", "    if False:", ['serialised global STAR block'], False),
 # manipulation() forces zeroed == eligible == coupled global peaks, so a DC drift always also drifts the coupled counters: shadowed
 'dc_drift': ('pair_decision_v4.py', "        if mo['dc'][key] != mn['dc'][key]:", "        if False:", [], True),
 'coupled_drift': ('pair_decision_v4.py', "    if mo['coupled']['global'] != mn['coupled']['global']:", "    if False:", ['global coupled counters drift'], False),
 'local3_eligible': ('pair_decision_v4.py', "        if local3 and le <= 0:", "        if False:", ['3x3 ON local eligible 0', '3x3 OFF local eligible 0'], False),
 'global_only_local_work': ('pair_decision_v4.py', "        if not local3 and (le != 0 or m['coupled']['patch']['peaks'] != 0):", "        if False:", ['global-only ON has local DC/coupled work'], False),
 'global_eligible_positive': ('pair_decision_v4.py', "        if m['dc']['global_eligible'] <= 0:", "        if False:", [], True),
 'global_only_block': ('pair_decision_v4.py', "    if not local3:\n        for rel in ('runtime.json'", "    if False:\n        for rel in ('runtime.json'", ['global-only ON MRC payload', 'global-only ON MRC header', 'global-only ON EPS', 'global-only ON runtime bytes differ'], False),
 'pair_binary': ('pair_decision_v4.py', "    if ro['binary_sha256'] != rn['binary_sha256'] or ro['argv'][0] != rn['argv'][0] or ro['binary_sha256'] != binary_sha256:", "    if False:", [], True),
 'witness_variant': ('pair_decision_v4.py', "        if VARIANT.search(ln) and ln != V3.WITNESS_LINE:", "        if False:", ['witness variant (lowercase hyphenless)', 'ON witness variant spelling'], False),
 'cases_param': ('pair_decision_v4.py', "    if cases is not None and list(cases) != order:", "    if False:", ['cases parameter reordered', 'cases parameter with a duplicate', 'cases parameter missing a case'], False),
 'cases_present': ('pair_decision_v4.py', "    if present != sorted(order):", "    if False:", ['unlisted extra case directory'], False),
 'pair_complete': ('pair_decision_v4.py', "        if not cd.is_dir() or sorted(p.name for p in cd.iterdir()) != ['OFF', 'ON'] or not ((cd / 'OFF').is_dir() and (cd / 'ON').is_dir()):", "        if False:", ['case without its ON directory'], False),
 'p2_strict': ('pair_decision_v4.py', "n['ON'][f]['angstrom'][k] < n['OFF'][f]['angstrom'][k]}", "n['ON'][f]['angstrom'][k] <= n['OFF'][f]['angstrom'][k]}", ['P2 fails on a tie'], False),
 'increases': ('pair_decision_v4.py', "                if on > off:", "                if False:", ['PASS->PASS increase is listed', 'P1 loss is listed'], False),
 'p1': ('pair_decision_v4.py', "    p1_ok = all(v['ON'][f] == 'PASS' for v in p1.values() for f in ('runtime', 'STAR'))", "    p1_ok = True", ['P1 lost on one case'], False),
 'prediction': ('pair_decision_v4.py', "'prediction': 'SUPPORTED' if (p1_ok and p2_ok) else 'NOT_SUPPORTED',", "'prediction': 'SUPPORTED',", ['P1 lost on one case', 'P2 fails on a single regressed'], False),
 'raw_gate': ('pair_decision_v4.py', "'noisy_raw_gate': 'PASS' if all(v == 'PASS' for v in noisy_gate.values()) else 'FAIL'", "'noisy_raw_gate': 'PASS' if p2_ok else 'FAIL'", ['improving P2 leaves the noisy raw gate FAIL'], False),
 'v3_names_guard': ('score_fields_v3.py', "    if names != sorted(expected['input_files']):", "    if False:", ['T1 extra staged file', 'T1 missing staged movie'], False),
 'v3_symlink_guard': ('score_fields_v3.py', "            if p.is_symlink():\n                _fail('INVENTORY', 'symlink under output: ' + name)", "            if False:\n                _fail('INVENTORY', 'symlink under output: ' + name)", ['T3 real symlink'], False),
 'v3_finite_guard': ('score_fields_v3.py', "    if not all(np.isfinite(a).all() for a in (g, cx, cy)):", "    if False:", ['T2 runtime overflow'], False),
}
FILES = ['score_fields_v2.py', 'score_fields_v3.py', 'pair_decision_v4.py', 'ADMISSION_DRAFT_v3.json', 'COMMANDS_DRAFT_v3.json', 'COMMANDS_DRAFT.json']
TESTS = ['tests/test_score_fields_v3.py', 'tests/test_pair_decision_v4.py']
only = set(sys.argv[2:]) if len(sys.argv) > 2 else None
out = {}
for name, (fname, old, new, intended, shadowed) in M.items():
    if only and name not in only:
        continue
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v4-mut-') as t:
        t = Path(t); (t / 'tests').mkdir()
        for f in FILES + TESTS:
            shutil.copy(PILOT / f, t / f)
        src = (t / fname).read_text()
        for o, n in (zip(old, new) if isinstance(old, list) else [(old, new)]):
            assert src.count(o) == 1, (name, src.count(o))
            src = src.replace(o, n)
        (t / fname).write_text(src)
        if fname == 'score_fields_v3.py':  # re-anchor the mutated v3 in the scratch copy so the mutation, not the anchor, is under test
            import hashlib
            h = hashlib.sha256((t / fname).read_bytes()).hexdigest()
            p4 = (t / 'pair_decision_v4.py').read_text()
            (t / 'pair_decision_v4.py').write_text(re.sub(r"V3_MODULE_SHA256 = '[0-9a-f]{64}'", "V3_MODULE_SHA256 = '%s'" % h, p4))
        env = dict(os.environ, V4_PIN_PILOT_ROOT=str(PILOT))
        p = subprocess.run([PY, '-B', str(t / 'tests/test_pair_decision_v4.py'), str(t / 'r.json')], capture_output=True, text=True, env=env)
        failed = [l[5:].split(' :: ')[0] for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        covered = [any(frag in f for f in failed) for frag in intended]
        if shadowed:
            status = 'SHADOWED_AS_DECLARED' if not failed else 'UNEXPECTEDLY_CAUGHT'
        else:
            status = 'KILLED' if all(covered) and intended else 'SURVIVED'
        out[name] = {'status': status, 'intended': intended, 'covered': covered, 'failed_count': len(failed), 'failed_tests': failed, 'exit': p.returncode}
        print('%s %s | failed %d' % (status, name, len(failed)), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
bad = [k for k, v in out.items() if v['status'] in ('SURVIVED', 'UNEXPECTEDLY_CAUGHT')]
sys.exit(1 if bad else 0)
