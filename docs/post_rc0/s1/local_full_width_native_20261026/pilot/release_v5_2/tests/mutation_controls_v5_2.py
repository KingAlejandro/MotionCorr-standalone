"""Guard-removal controls for release v5.2 (scratch copies only). Shadowed guards are declared up front and not claimed as kills; a mutant that kills or hangs the test process counts as killed."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
V52 = Path(__file__).resolve().parent.parent
PILOT = V52.parent
V5 = PILOT / 'release_v5'
REPO = PILOT.parents[4]
PY = sys.executable
P = 'pair_decision_v5_2.py'; D = 'driver_v5_2.py'
M = {
 'audit_argv': (P, [("    if len(idx) != 1 or idx[0] + 1 >= len(argv) or argv[idx[0] + 1] != root:", "    if False:")], ['audit'], ['names another case (basename)', 'differs in the last character', 'by one digit', 'no --o value pair', 'has a second --o'], False),
 'audit_embedded': (P, [("    if embedded != {root}:", "    if False:")], ['audit'], ['embeds an extra root', 'embeds a different root only'], False),
 'audit_called': (P, [("    _root_audit(case, baseline_dir)\n    return pins", "    return pins")], ['audit'], ['extra root', 'different root only', 'r1 failure mode'], False),
 'audit_path_shape': (P, [("    if bd.name != 'UP_only' or bd.parent.name != case:", "    if False:")], ['audit'], [], True),
 'reuse_arm': (D, [("    if (c.get('case'), c.get('arm')) != first or c.get('kind') != 'reuse_first_off_after_r1_stop':", "    if False:")], ['refusals'], ['reuse naming another arm is refused'], False),
 'reuse_listing': (D, [("    if not ev.is_dir() or sorted(p.name for p in ev.iterdir()) != [first[0]] or sorted(p.name for p in (ev / first[0]).iterdir()) != ['OFF']:", "    if False:")], ['refusals'], ['another case directory', 'an existing ON', 'a stray file in evidence_root'], False),
 'reuse_inventory': (D, [("    if inv != c['evidence_inventory'] or hashlib.sha256(P5._canon(inv)).hexdigest() != c['evidence_inventory_sha256']:", "    if False:")], ['refusals'], ['one output byte', 'an extra file'], False),
 'reuse_run_hash': (D, [("    if _sha(off / 'RUN.json') != c['run_json_sha256']:", "    if False:")], ['refusals'], ['admission reuse hash wrong'], False),
 'reuse_r1_records': (D, [("        if not (r1 / name).is_file() or _sha(r1 / name) != c[key]:", "        if False:")], ['refusals'], ['r1 ledger changed', 'r1 STOP changed'], False),
 'budget_arithmetic': (D, [("    if len(plan) + c['launches_before'] != budget or c['remaining'] != len(plan) or c['global_ceiling'] != budget or budget != 16:", "    if False:")], ['refusals'], ['plan plus the reused OFF is not the budget'], False),
 'release_reused_hash': (D, [(",\n            'reused_off_run_json_sha256': ctx.continuation['run_json_sha256']}", "}")], ['refusals'], ['release without the reused-OFF hash'], False),
 'release_commands': (D, [(" 'commands_sha256': hashlib.sha256(P5.COMMANDS_PATH.read_bytes()).hexdigest(),", "")], ['refusals'], ['release commands hash wrong'], False),
 'ledger_fresh': (D, [("    if ledger.exists():\n        raise DriverStop('EXISTS', 'ledger already exists: the continuation decision directory must be fresh')", "    if False:\n        raise DriverStop('EXISTS', 'x')")], ['refusals'], ['decision directory not fresh'], False),
 'reused_event': (D, [("'event': 'REUSED'", "'event': 'NOTE'")], ['happy'], ['explicit REUSED event'], False),
 'pre_on_reused': (D, [("        P5.pre_ON_gate(order[0], decision_dir=dd)  # re-evaluated", "        pass  # re-evaluated")], ['happy'], ['INFRA fault in g_happy'], False),
 'plan_noisy_on_first': (D, [("    plan = [(order[0], 'ON')] + [(c, a) for c in order[1:] for a in ARMS]", "    plan = [(order[0], 'OFF'), (order[0], 'ON')] + [(c, a) for c in order[1:] for a in ARMS]")], ['happy'], ['INFRA fault in g_happy'], False),
}
FILES52 = ['pair_decision_v5_2.py', 'driver_v5_2.py', 'ADMISSION_V5_2.json', 'COMMANDS_V5_2.json']
FILES5 = ['pair_decision_v5.py', 'driver_v5.py', 'driver_v5_1.py', 'ADMISSION_V5.json', 'COMMANDS_V5.json']
only = set(sys.argv[2:]) or None
out = {}
for name, (fname, edits, groups, intended, shadowed) in M.items():
    if only and name not in only:
        continue
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v52-mut-') as t:
        t = Path(t)
        pilot = t / 'a' / 'b' / 'c' / 'd' / 'pilot'; v52 = pilot / 'release_v5_2'; v5 = pilot / 'release_v5'
        (v52 / 'tests').mkdir(parents=True); (v5 / 'tests').mkdir(parents=True)
        for f in ('score_fields_v2.py', 'score_fields_v3.py'):
            shutil.copy(PILOT / f, pilot / f)
        for f in FILES52:
            shutil.copy(V52 / f, v52 / f)
        for f in FILES5:
            shutil.copy(V5 / f, v5 / f)
        for f in (V52 / 'tests').glob('*.py'):
            shutil.copy(f, v52 / 'tests' / f.name)
        for f in (V5 / 'tests').glob('*.py'):
            shutil.copy(f, v5 / 'tests' / f.name)
        src = (v52 / fname).read_text()
        for o, n in edits:
            assert src.count(o) == 1, (name, src.count(o))
            src = src.replace(o, n)
        (v52 / fname).write_text(src)
        env = dict(os.environ, V5_PIN_PILOT_ROOT=str(PILOT), V5_PIN_REPO_ROOT=str(REPO))
        try:
            p = subprocess.run([PY, '-B', str(v52 / 'tests' / 'test_continuation_v5_2.py'), str(t / 'r.json')] + groups, capture_output=True, text=True, env=env, timeout=600)
            stdout, rc = p.stdout, p.returncode
            stderr_tail = p.stderr[-800:]
        except subprocess.TimeoutExpired as e:
            stdout, rc = '', -999
            stderr_tail = 'TIMEOUT'
        failed = [l[5:].split(' :: ')[0] for l in stdout.splitlines() if l.startswith('FAIL ')]
        crashed = 'TOTAL ' not in stdout
        covered = [any(frag in f for f in failed) for frag in intended]
        status = ('SHADOWED_AS_DECLARED' if not failed and not crashed else 'UNEXPECTEDLY_CAUGHT') if shadowed else ('KILLED' if (crashed or (intended and all(covered))) else 'SURVIVED')
        out[name] = {'status': status, 'groups': groups, 'intended': intended, 'covered': covered, 'failed_count': len(failed), 'crashed_or_hung': crashed, 'failed_tests': failed, 'exit': rc, 'stderr_tail': stderr_tail, 'stdout_tail': stdout[-400:]}
        print('%s %s | failed %d%s' % (status, name, len(failed), ' (test process died/hung)' if crashed else ''), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
sys.exit(1 if any(v['status'] in ('SURVIVED', 'UNEXPECTEDLY_CAUGHT') for v in out.values()) else 0)
