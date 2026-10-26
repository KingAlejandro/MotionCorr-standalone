"""Guard-removal controls for release v5 and the driver (scratch copies only). Each mutant weakens one guard; the named test groups must then fail
the named tests. Guards that another guard shadows are declared up front (SHADOWED) and never claimed as kills."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
V5 = Path(__file__).resolve().parent.parent
PILOT = V5.parent
REPO = PILOT.parents[4]
PY = sys.executable
P = 'pair_decision_v5.py'; D = 'driver_v5.py'
GATE_RAW = "    _verify_baseline(ctx, case, baseline_dir)\n    _off_raw_check(ctx, case, off_dir)\n    fns = _pinned_functions(ctx)\n"
VERIFY_RAW = "    _verify_baseline(ctx, case, baseline_dir)\n    _off_raw_check(ctx, case, off_dir)\n    man = _manipulation_checked(case, 'OFF', off_dir, fns, grid)\n"
M = {
 'anchor_admission': (P, [("    if _sha_bytes(ab) != ADMISSION_V5_SHA256:", "    if False:")], ['identity'], ['altered anchored admission refused'], False),
 'anchor_commands': (P, [("    if _sha_bytes(cb) != COMMANDS_V5_SHA256:", "    if False:")], ['identity'], ['hand-edited commands refused'], False),
 'held_and_null_fields': (P, [("        if str(adm.get('status', '')).startswith('HELD_') or any(adm.get(k) is None for k in LAUNCH_FIELDS) \\", "        if False and any(adm.get(k) is None for k in LAUNCH_FIELDS) \\")], ['identity'], ['null candidate_binary refused', 'null build_receipt refused', 'HELD status refused'], False),
 'identity_file_hash': (P, [("        if _file_sha(p) != d['sha256']:", "        if False:")], ['identity'], ['binary on disk differs', 'source archive changed after the pin', 'build receipt changed after the pin'], False),
 'identity_symlink': (P, [("        if p.is_symlink() or not p.is_file():\n            raise PairError('IDENTITY'", "        if not p.is_file():\n            raise PairError('IDENTITY'")], ['identity'], ['binary given as a symlink (pin and receipt agree on the link)'], False),
 'identity_commit': (P, [("    if adm.get('candidate_source_commit') != sa.get('commit') or", "    if False and adm.get('candidate_source_commit') != sa.get('commit') or")], ['identity'], ['candidate_source_commit differs'], False),
 'identity_receipt_binding': (P, [("    if not ok:\n        raise PairError('IDENTITY', 'build receipt does not bind", "    if False:\n        raise PairError('IDENTITY', 'build receipt does not bind")], ['identity'], ['build receipt with the wrong archive sha256', 'build receipt with the wrong commit', 'build receipt with the wrong binary sha256', 'binary path differs from the build receipt'], False),
 'resolved_commands': (P, [("            if frozen.get(key) != _h(", "            if False and frozen.get(key) != _h(")], ['identity'], ['resolved command row differs'], False),
 'tool_pins': (P, [("            V3.verify_tool_pins(adm, self.roots)", "            pass")], ['identity'], ['altered tool pin refused'], False),
 'gate_off_raw': (P, [(GATE_RAW, "    _verify_baseline(ctx, case, baseline_dir)\n    fns = _pinned_functions(ctx)\n")], ['l2'], ['gate refuses the changed OFF runtime'], False),
 'gate_l3_removed': (P, [("    man = _manipulation_checked(case, 'OFF', off_dir, fns, exp['patch_grid'])  # L3: before any ON launch", "    man = {}")], ['l3'], ['L3 gate stops before ON: OFF zero global DC counters', 'L3 gate stops before ON: OFF missing DC line', 'global-only OFF with local work', '3x3 OFF with local eligible 0'], False),
 'gate_l3_coverage_rules': (P, [("    man = _manipulation_checked(case, 'OFF', off_dir, fns, exp['patch_grid'])  # L3: before any ON launch", "    man = fns[1](Path(off_dir) / 'stdout.log')")], ['l3'], ['global-only OFF with local work', '3x3 OFF with local eligible 0'], False),
 'verify_raw': (P, [(VERIFY_RAW, "    _verify_baseline(ctx, case, baseline_dir)\n    man = _manipulation_checked(case, 'OFF', off_dir, fns, grid)\n")], ['l2', 'l2b'], ['L2 self-consistent handwritten record', 'L2 OFF STAR edited after the gate'], False),
 'verify_baseline': (P, [(VERIFY_RAW, "    _off_raw_check(ctx, case, off_dir)\n    man = _manipulation_checked(case, 'OFF', off_dir, fns, grid)\n")], ['l2b'], ['L2 baseline byte changed after the gate'], False),
 'record_binding': (P, [("    if rec.get('bound') != bound or rec.get('binding_sha256') != _h(bound) or _h(rec['bound']) != rec['binding_sha256']:", "    if False:")], ['record'], ['tampered pre-ON record'], False),
 'record_status': (P, [("    if rec.get('schema') != PRE_ON_SCHEMA or rec.get('status') != 'PASS':", "    if False:")], ['record'], ['pre-ON record status not PASS'], False),
 'fresh_pair_dir': (P, [("        try:\n            d.mkdir()\n            return d\n        except FileExistsError:\n            k += 1", "        d.mkdir(exist_ok=True)\n        return d")], ['l1'], ['INFRA fault in g_l1'], False),
 'witness_variant': (P, [("        if VARIANT.search(ln) and ln != V3.WITNESS_LINE:", "        if False:")], ['v4'], ['witness spelling variant rejected'], False),
 'global_bits': (P, [("    if fo['global_bits'] != fn_['global_bits']:", "    if False:")], ['v4'], ['ON global runtime 1 ulp different'], False),
 'cases_param': (P, [("    if cases is not None and list(cases) != order:", "    if False:")], ['l1'], ['cases parameter reordered'], False),
 'cases_present': (P, [("    if present != sorted(order):", "    if False:")], ['l1'], ['unlisted extra case directory'], False),
 'driver_release_present': (D, [("    if not rp.is_file():\n        raise DriverStop('RELEASE'", "    if False:\n        raise DriverStop('RELEASE'")], ['driver_ok'], ['real launch refused without PARENT_RELEASE.json'], False),
 'driver_release_hashes': (D, [("        if r.get(k) != v:\n            raise DriverStop('RELEASE'", "        if False:\n            raise DriverStop('RELEASE'")], ['driver_ok'], ['release file with a wrong release_module_sha256', 'release file with a wrong driver_sha256', 'release file with a wrong admission_sha256'], False),
 'driver_release_review': (D, [("    if not (isinstance(r.get('delta_review_report_sha256'), str)", "    if False and not (isinstance(r.get('delta_review_report_sha256'), str)")], ['driver_ok'], ['wrong delta_review_report_sha256'], False),
 'driver_guard_call': (D, [("                g = guard('%s/%s' % (case, arm))\n", "                g = {}\n")], ['f8', 'driver_ok'], ['guard failure before an ON launch'], False),
 'driver_exclusive_dir': (D, [("        run_dir.mkdir()  # exclusive", "        run_dir.mkdir(exist_ok=True)  # exclusive")], ['f9'], ['run directory already exists'], False),
 'driver_staging_listing': (D, [("    if sorted(os.listdir(inp)) != sorted([case + '.mrcs', case + '.star']):", "    if False:")], ['f9'], ['a truth file in the staged cwd is refused'], False),
 'driver_producer_stop': (D, [("                if receipt['exit'] != 0 or receipt['timed_out']:", "                if False:")], ['f1', 'f2'], ['fake child exits 1 on the first OFF', 'fake child times out'], False),
 'driver_evidence_empty': (D, [("    if ev.exists() and any(ev.iterdir()):", "    if False:")], ['f9'], ['evidence_root not empty at the start'], False),
 'driver_identity_each_launch': (D, [("                P5._verify_identity(ctx.adm)  # before anything is staged or counted: the binary must still equal its pin\n", "")], ['f11'], ['binary changed between the OFF and ON launches'], False),
 'driver_budget': (D, [("    if len(plan) > budget:", "    if False:")], ['f10'], ['plan above the producer budget'], False),
 'driver_fixture_pins': (D, [("        if not p.is_file() or p.stat().st_size != pin['bytes'] or _sha(p) != pin['sha256']:\n            raise DriverStop('FIXTURE', 'fixture differs from its pin: ' + n)", "        if False:\n            raise DriverStop('FIXTURE', 'fixture differs from its pin: ' + n)")], ['f9'], ['fixture differing from its pin refuses the campaign'], False),
 'driver_baseline_validate': (D, [("            P5._verify_baseline(ctx, case, ctx.baseline_dir(case))", "            pass")], ['f10'], ['missing retained baseline refuses the campaign'], False),
 # the ledger-exists guard is shadowed by the evidence_root-not-empty guard (checked first)
 'driver_ledger_exists': (D, [("    if ledger.exists():", "    if False:")], ['driver_ok'], [], True),
 # PAIR_BINARY is shadowed by the per-arm binary checks of the single admission
 'pair_binary': (P, [("    if ro['binary_sha256'] != rn['binary_sha256'] or ro['argv'][0] != rn['argv'][0] or ro['binary_sha256'] != ctx.binary_sha256:", "    if False:")], ['v4', 'l2'], [], True),
}
FILES = ['pair_decision_v5.py', 'driver_v5.py', 'ADMISSION_V5.json', 'COMMANDS_V5.json']
only = set(sys.argv[2:]) or None
out = {}
for name, (fname, edits, groups, intended, shadowed) in M.items():
    if only and name not in only:
        continue
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v5-mut-') as t:
        t = Path(t)
        pilot = t / 'a' / 'b' / 'c' / 'd' / 'pilot'; v5 = pilot / 'release_v5'; (v5 / 'tests').mkdir(parents=True)
        for f in ('score_fields_v2.py', 'score_fields_v3.py'):
            shutil.copy(PILOT / f, pilot / f)
        for f in FILES:
            shutil.copy(V5 / f, v5 / f)
        for f in (V5 / 'tests').glob('*.py'):
            shutil.copy(f, v5 / 'tests' / f.name)
        src = (v5 / fname).read_text()
        for o, n in edits:
            assert src.count(o) == 1, (name, src.count(o))
            src = src.replace(o, n)
        (v5 / fname).write_text(src)
        if fname == P:  # the admission anchors are constants inside the module and stay as built
            pass
        env = dict(os.environ, V5_PIN_PILOT_ROOT=str(PILOT), V5_PIN_REPO_ROOT=str(REPO))
        p = subprocess.run([PY, '-B', str(v5 / 'tests' / 'test_release_v5.py'), str(t / 'r.json')] + groups, capture_output=True, text=True, env=env)
        failed = [l[5:].split(' :: ')[0] for l in p.stdout.splitlines() if l.startswith('FAIL ')]
        covered = [any(frag in f for f in failed) for frag in intended]
        status = ('SHADOWED_AS_DECLARED' if not failed else 'UNEXPECTEDLY_CAUGHT') if shadowed else ('KILLED' if intended and all(covered) else 'SURVIVED')
        out[name] = {'status': status, 'groups': groups, 'intended': intended, 'covered': covered, 'failed_count': len(failed), 'failed_tests': failed, 'exit': p.returncode}
        print('%s %s | failed %d' % (status, name, len(failed)), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
sys.exit(1 if any(v['status'] in ('SURVIVED', 'UNEXPECTEDLY_CAUGHT') for v in out.values()) else 0)
