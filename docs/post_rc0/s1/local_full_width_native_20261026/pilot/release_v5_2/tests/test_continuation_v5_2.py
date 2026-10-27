"""Tests for release v5.2 (criteria frozen in CONTINUATION_PLAN.md): root audit, controlled reuse of the one produced OFF, and the continuation driver.
Fake child and a replay of the single existing OFF only; no MotionCorr, no native, no fit.

usage: python -B tests/test_continuation_v5_2.py RESULT.json [group ...]   (real NumPy interpreter; threads <= 2)
"""
import copy, hashlib, json, os, shutil, sys, tempfile, traceback
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V52 = HERE.parent
PILOT = V52.parent
V5 = PILOT / 'release_v5'
os.environ.setdefault('V5_PIN_REPO_ROOT', str(PILOT.parents[4]))
sys.path.insert(0, str(V52)); sys.path.insert(0, str(V5 / 'tests')); sys.path.insert(0, str(V5))
import test_release_v5 as TR
import pair_decision_v5_2 as P
import driver_v5_2 as D
import fake_products as fp

TR.P5, TR.D5 = P, D  # the shared world builder now drives the v5.2 module and driver
V3 = P.V3
ORDER = TR.ORDER
sha = TR.sha
RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''), flush=True)


def expect_code(name, code, fn):
    try:
        fn()
    except (P.PairError, V3.AdmissionError, D.DriverStop) as e:
        record(name, e.code == code, 'code=%s' % e.code if e.code == code else 'wanted %s got %s: %s' % (code, e.code, e))
        return
    except BaseException as e:
        record(name, False, 'wrong exception %s: %s' % (type(e).__name__, e))
        return
    record(name, False, 'ACCEPTED but wanted %s' % code)


class W52(TR.W5):
    def __init__(self, scratch):
        self.cont = None
        self.sync_fn = None
        super().__init__(scratch)
        self.adm['baseline_root'] = str(self.base)
        for row in self.adm['rows']:  # baseline RUN.json as the retained ones: JSON with argv --o equal to the baseline output path
            c = row['case']; d = self.base / c / 'UP_only'
            (d / 'RUN.json').write_text(json.dumps({'case': c, 'arm': 'UP_only', 'argv': ['/x/motioncorr', '--i', c + '.star', '--o', str(d.resolve() / 'output'), '--use_own']}))
            self.repin(c)
        self.cont = {'kind': 'reuse_first_off_after_r1_stop', 'case': 'noisy', 'arm': 'OFF', 'run_json_sha256': '0' * 64, 'evidence_inventory': {}, 'evidence_inventory_sha256': '0' * 64,
                     'r1_decision_dir': str(self.s / 'decision_r1'), 'r1_ledger_sha256': '0' * 64, 'r1_stop_sha256': '0' * 64, 'r1_release_sha256': '0' * 64, 'r1_release_index_sha256': '0' * 64,
                     'launches_before': 1, 'remaining': 15, 'global_ceiling': 16}
        self.sync()

    def repin(self, case):
        d = self.base / case / 'UP_only'
        row = [r for r in self.adm['rows'] if r['case'] == case][0]
        row['baseline_files'] = {str(p.relative_to(d)): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in sorted(d.rglob('*')) if p.is_file()}

    def sync(self):
        cmds = json.loads(P.COMMANDS_PATH.read_text())
        if self.adm.get('candidate_binary'):
            self.adm['resolved_commands_sha256'] = {}
            for r in cmds:
                exp = V3.resolve_expected_row(cmds, self.adm, r['case'], r['arm'], str(self.ev), self.adm['candidate_binary']['path'], self.adm['candidate_binary']['sha256'])
                self.adm['resolved_commands_sha256']['%s/%s' % (r['case'], r['arm'])] = P._h({k: exp[k] for k in ('argv', 'cwd', 'environment', 'input_files')})
        if self.cont is not None:
            self.adm['continuation'] = self.cont
        p = self.s / 'ADMISSION_TEST.json'
        p.write_text(json.dumps(self.adm, indent=1))
        P.ADMISSION_PATH, P.ADMISSION_V5_2_SHA256 = p, sha(p.read_bytes())

    def freeze_reuse(self):
        """After noisy/OFF exists: write r1-like records and compute the frozen continuation block from what is actually on disk."""
        r1 = self.s / 'decision_r1'; r1.mkdir(exist_ok=True)
        for n, t in (('ledger.jsonl', '{"event": "launching"}\n{"event": "finished"}\n{"event": "STOP", "code": "COMPARATOR"}\n'), ('STOP.json', '{"code": "COMPARATOR"}\n'),
                     ('PARENT_RELEASE.json', '{"r1": true}\n'), ('PARENT_RELEASE_INDEX.json', '{"r1": true}\n')):
            (r1 / n).write_text(t)
        off = self.ev / 'noisy' / 'OFF'
        inv = D._tree_inventory(off)
        self.cont.update({'run_json_sha256': sha((off / 'RUN.json').read_bytes()), 'evidence_inventory': inv, 'evidence_inventory_sha256': hashlib.sha256(P._canon(inv)).hexdigest(),
                          'r1_ledger_sha256': sha((r1 / 'ledger.jsonl').read_bytes()), 'r1_stop_sha256': sha((r1 / 'STOP.json').read_bytes()),
                          'r1_release_sha256': sha((r1 / 'PARENT_RELEASE.json').read_bytes()), 'r1_release_index_sha256': sha((r1 / 'PARENT_RELEASE_INDEX.json').read_bytes())})
        self.sync()

    def release52(self, **over):
        r = {'release_module_sha256': sha((V52 / 'pair_decision_v5_2.py').read_bytes()), 'driver_sha256': sha((V52 / 'driver_v5_2.py').read_bytes()),
             'admission_sha256': sha(P.ADMISSION_PATH.read_bytes()), 'commands_sha256': sha(P.COMMANDS_PATH.read_bytes()), 'reused_off_run_json_sha256': self.cont['run_json_sha256'],
             'delta_review_report_sha256': 'a' * 64, 'approved_by': 'parent'}
        r.update(over)
        self.dec.mkdir(exist_ok=True)
        (self.dec / 'PARENT_RELEASE.json').write_text(json.dumps(r))


def fresh(fn, prepare=False):
    saved = (P.ADMISSION_PATH, P.ADMISSION_V5_2_SHA256, P.COMMANDS_PATH, P.COMMANDS_V5_2_SHA256, P._score_arm)
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v52-') as t:
        try:
            w = W52(t)
            if prepare:
                w.produce('noisy', 'OFF'); w.freeze_reuse()
            return fn(w)
        except BaseException as e:
            record('INFRA fault in %s' % fn.__name__, False, ''.join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            P.ADMISSION_PATH, P.ADMISSION_V5_2_SHA256, P.COMMANDS_PATH, P.COMMANDS_V5_2_SHA256, P._score_arm = saved


def guard_ok(step):
    return {'step': step}


def cont(w, **kw):
    return D.run_continuation(w.dec, execute=kw.pop('execute', True), guard=kw.pop('guard', guard_ok), cpus=None, timeout=kw.pop('timeout', 30))


def ledger(w):
    return [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]


# =============================== root audit ===========================================================================================
def g_audit(w):
    w.produce('noisy', 'OFF')
    record('positive: the audited baseline root passes the whole gate (OFF admitted, comparator IDENTICAL)', w.gate('noisy')['status'] == 'PASS')
    bd = w.base / 'noisy' / 'UP_only'
    run0 = (bd / 'RUN.json').read_text()
    def with_run(argv_edit):
        r = json.loads(run0); r['argv'] = argv_edit(r['argv']); (bd / 'RUN.json').write_text(json.dumps(r)); w.repin('noisy'); w.sync()
    def audit(name):
        expect_code(name, 'ROOT_AUDIT', lambda: P._verify_baseline(P.context(w.s / 'dec_audit'), 'noisy', bd))
    with_run(lambda a: [x.replace('/noisy/', '/affine/') if x.endswith('output') else x for x in a]); audit('baseline RUN.json --o names another case (basename)')
    with_run(lambda a: [x[:-8] + 'outpux' if x.endswith('output') else x for x in a]); audit('baseline RUN.json --o differs in the last character')
    with_run(lambda a: [x.replace('/baseline/', '/baseline1/') if x.endswith('output') else x for x in a]); audit('baseline RUN.json --o differs by one digit in a path component (numeric)')
    with_run(lambda a: [x for x in a if x != '--o']); audit('baseline RUN.json has no --o value pair')
    with_run(lambda a: a + ['--o', '/x/output']); audit('baseline RUN.json has a second --o')
    (bd / 'RUN.json').write_text(run0); w.repin('noisy'); w.sync()
    record('control: the restored baseline passes the audit again', P._verify_baseline(P.context(w.s / 'dec_audit2'), 'noisy', bd) is not None)
    star = bd / 'output' / 'corrected_micrographs.star'; keep = star.read_bytes()
    star.write_bytes(keep + b'/other/root/output/x.mrc\n'); w.repin('noisy'); w.sync()
    audit('corrected_micrographs.star embeds an extra root')
    star.write_bytes(keep.replace(str(bd.resolve() / 'output').encode(), b'/somewhere/else/output')); w.repin('noisy'); w.sync()
    audit('corrected_micrographs.star embeds a different root only')
    star.write_bytes(keep); w.repin('noisy'); w.sync()
    # the r1 failure mode: a copy at a different path over files that embed the original root
    dur = w.s / 'durable_like'; shutil.copytree(w.base / 'noisy' / 'UP_only', dur / 'noisy' / 'UP_only')
    w.adm['baseline_root'] = str(dur); w.sync()
    expect_code('r1 failure mode (durable-style path over original-root files) is now a loud ROOT_AUDIT', 'ROOT_AUDIT', lambda: w.gate('noisy'))
    w.adm['baseline_root'] = str(w.base); w.sync()
    # copy-only comparator control: with the audited root the normalisation is correct yet a real payload change is still detected
    mrc = w.base / 'noisy' / 'UP_only' / 'output' / 'noisy.mrc'; b = mrc.read_bytes(); mrc.write_bytes(b[:1030] + b'\x07' + b[1031:]); w.repin('noisy'); w.sync()
    expect_code('control: a changed MRC payload is still detected by the comparator after the audit', 'COMPARATOR', lambda: P.pre_ON_gate('noisy', decision_dir=w.s / 'dec_cmp'))


# =============================== reuse and continuation ===============================================================================
def g_happy(w):
    P._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: TR.crafted_scores()[case][arm]
    off = w.ev / 'noisy' / 'OFF'
    run0 = sha((off / 'RUN.json').read_bytes()); r1 = {n: sha((w.s / 'decision_r1' / n).read_bytes()) for n in ('ledger.jsonl', 'STOP.json')}
    dry = D.run_continuation(w.dec, execute=False, guard=guard_ok)
    record('dry run validates, plans 15 launches (noisy ON first) and creates nothing', dry['launches_planned'] == 15 and dry['rows'][0]['case'] == 'noisy' and dry['rows'][0]['arm'] == 'ON' and dry['created'] == []
           and sorted(p.name for p in w.ev.iterdir()) == ['noisy'] and not w.dec.exists())
    w.release52()
    res = cont(w)
    led = ledger(w)
    launches = [(e['case'], e['arm']) for e in led if e['event'] == 'launching']
    record('continuation ends in the decision with 15 new launches', res['prediction'] == 'SUPPORTED' and len(launches) == 15 and led[-1]['event'] == 'DECIDED' and led[-1]['global_launches'] == 16)
    record('the new ledger starts with the explicit REUSED event (before 1, remaining 15, ceiling 16)', led[0]['event'] == 'REUSED' and led[0]['launches_before'] == 1 and led[0]['remaining'] == 15 and led[0]['global_ceiling'] == 16)
    record('noisy/OFF is never launched again and the order is noisy ON then the 7 cases OFF/ON', ('noisy', 'OFF') not in launches and launches == [('noisy', 'ON')] + [(c, a) for c in ORDER[1:] for a in ('OFF', 'ON')])
    record('the reused OFF RUN.json and the r1 ledger/STOP are unchanged after the run', sha((off / 'RUN.json').read_bytes()) == run0 and all(sha((w.s / 'decision_r1' / n).read_bytes()) == h for n, h in r1.items()))
    record('pre-ON record for the reused OFF exists in the NEW decision directory (re-evaluated from saved outputs)', (w.dec / 'pre_on' / 'noisy' / 'pre_on.json').is_file())
    expect_code('a finished continuation is not restartable in place', 'REUSE', lambda: cont(w))


def _refuse(name, code, mutate, release=True, **over):
    def run(w):
        mutate(w)
        if release:
            w.release52(**over)
        expect_code(name, code, lambda: cont(w))
        record(name + ' [no producer launched]', not (w.dec / 'ledger.jsonl').exists() or not any(e.get('event') == 'launching' for e in ledger(w)))
    fresh(run, prepare=True)


def refusals():
    _refuse('unexpected existing row: another case directory', 'REUSE', lambda w: (w.ev / 'affine').mkdir())
    _refuse('unexpected existing row: an existing ON', 'REUSE', lambda w: (w.ev / 'noisy' / 'ON').mkdir())
    _refuse('unexpected existing row: a stray file in evidence_root', 'REUSE', lambda w: (w.ev / 'stray.txt').write_text('x'))
    _refuse('changed first OFF: one output byte', 'REUSE', lambda w: (w.ev / 'noisy' / 'OFF' / 'output' / 'noisy.mrc').write_bytes((w.ev / 'noisy' / 'OFF' / 'output' / 'noisy.mrc').read_bytes() + b'x'))
    _refuse('changed first OFF: an extra file', 'REUSE', lambda w: (w.ev / 'noisy' / 'OFF' / 'extra.txt').write_text('x'))
    _refuse('changed first OFF: the receipt', 'REUSE', lambda w: (w.ev / 'noisy' / 'OFF' / 'RUN.json').write_text((w.ev / 'noisy' / 'OFF' / 'RUN.json').read_text() + ' '))
    _refuse('missing first OFF', 'REUSE', lambda w: shutil.rmtree(w.ev / 'noisy' / 'OFF'))
    _refuse('r1 ledger changed', 'REUSE', lambda w: (w.s / 'decision_r1' / 'ledger.jsonl').write_text('tampered\n'))
    _refuse('r1 STOP changed', 'REUSE', lambda w: (w.s / 'decision_r1' / 'STOP.json').write_text('{}'))

    def other_case(w):
        w.cont['case'] = 'affine'; w.sync()
    _refuse('reuse naming another case is refused', 'REUSE', other_case)

    def other_arm(w):
        w.cont['arm'] = 'ON'; w.sync()
    _refuse('reuse naming another arm is refused', 'REUSE', other_arm)

    def wrong_hash(w):
        w.cont['run_json_sha256'] = 'f' * 64; w.sync()
    _refuse('admission reuse hash wrong', 'REUSE', wrong_hash)

    def budget(w):
        w.cont['remaining'] = 14; w.sync()
    _refuse('plan plus the reused OFF is not the budget', 'BUDGET', budget)
    _refuse('release without the reused-OFF hash', 'RELEASE', lambda w: None, reused_off_run_json_sha256='0' * 64)
    _refuse('release naming the old v5.1 driver', 'RELEASE', lambda w: None, driver_sha256=hashlib.sha256((V5 / 'driver_v5_1.py').read_bytes()).hexdigest())
    _refuse('release without any file', 'RELEASE', lambda w: w.dec.mkdir(exist_ok=True), release=False)
    _refuse('release commands hash wrong', 'RELEASE', lambda w: None, commands_sha256='1' * 64)

    def nonfresh(w):
        w.dec.mkdir(exist_ok=True); (w.dec / 'ledger.jsonl').write_text('{}\n')
    _refuse('decision directory not fresh', 'EXISTS', nonfresh)


def g_stops(w):
    P._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: TR.crafted_scores()[case][arm]
    w.modes({'affine/OFF': {'payload_bytes': 'zzzz'}})
    w.release52()
    expect_code('a later-case OFF compat failure stops before its ON', 'COMPARATOR', lambda: cont(w))
    led = ledger(w)
    record('stop after exactly noisy ON and affine OFF, no affine ON, no further case', [(e['case'], e['arm']) for e in led if e['event'] == 'launching'] == [('noisy', 'ON'), ('affine', 'OFF')] and not (w.ev / 'affine' / 'ON').exists() and led[-1]['event'] == 'STOP')
    record('the old OFF still untouched after a stop', json.loads((w.ev / 'noisy' / 'OFF' / 'RUN.json').read_text())['exit'] == 0)


def g_stop_on(w):
    w.modes({'noisy/ON': {'exit': 1}}); w.release52()
    expect_code('a failing noisy ON producer stops the continuation', 'PRODUCER', lambda: cont(w))
    led = ledger(w)
    record('no further launch after the noisy ON failure', sum(1 for e in led if e['event'] == 'launching') == 1 and led[-1]['event'] == 'STOP')


GROUPS = {'audit': (g_audit, False), 'happy': (g_happy, True), 'stops': (g_stops, True), 'stop_on': (g_stop_on, True), 'refusals': (None, None)}


def main(result_path, only=None):
    for name, (fn, prep) in GROUPS.items():
        if only and name not in only:
            continue
        if name == 'refusals':
            refusals()
        else:
            fresh(fn, prepare=prep)
    failed = [r for r in RESULTS if not r['ok']]
    Path(result_path).write_text(json.dumps({'total': len(RESULTS), 'failed': len(failed), 'results': RESULTS}, indent=1, allow_nan=False) + '\n')
    print('TOTAL %d FAILED %d' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], set(sys.argv[2:]) or None))
