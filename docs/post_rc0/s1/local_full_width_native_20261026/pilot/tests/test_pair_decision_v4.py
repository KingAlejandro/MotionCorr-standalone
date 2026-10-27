"""Tests for pair_decision_v4 (criteria frozen in PAIR_V4_PLAN.md). Scratch files only; tiny fake byte products; the actual pinned
comparator runs as a subprocess. Synthetic receipts test consumer logic only, not that any producer obeys it.

usage: python -B tests/test_pair_decision_v4.py RESULT.json   (real NumPy interpreter; threads <= 2)
"""
import copy, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(__file__).resolve().parent.parent
PIN_PILOT = Path(os.environ.get('V4_PIN_PILOT_ROOT', str(PILOT)))  # mutation controls point pins at the real pilot files
sys.path.insert(0, str(PILOT)); sys.path.insert(0, str(PILOT / 'tests'))
import pair_decision_v4 as P4
import score_fields_v3 as V3
import test_score_fields_v3 as TV3

RAW, FIX, REPO, CONSUMER = TV3.RAW, TV3.FIX, TV3.REPO, TV3.CONSUMER
BIN, BINSHA = TV3.BIN, TV3.BINSHA
ADM_REAL = json.loads((PILOT / 'ADMISSION_DRAFT_v3.json').read_text())
ROWS = {r['case']: r for r in ADM_REAL['rows']}
sha = lambda b: hashlib.sha256(b).hexdigest()
RESULTS = []
ROOTS = {'consumer_source': CONSUMER, 'repo': REPO, 'pilot': PIN_PILOT}
ALL_CASES = ADM_REAL['case_order']


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''), flush=True)


def expect_code(name, code, fn):
    try:
        fn()
    except (P4.PairError, V3.AdmissionError) as e:
        record(name, e.code == code, 'code=%s' % e.code if e.code == code else 'wanted %s got %s: %s' % (code, e.code, e))
        return
    except Exception as e:
        record(name, False, 'wrong exception %s: %s' % (type(e).__name__, e))
        return
    record(name, False, 'ACCEPTED but wanted %s' % code)


def make_log(case, arm, local3):
    t = 'Working on %s.mrcs with 2 thread(s).\n\nGlobal alignment:\n Iteration 1: RMSD = 0.31 px\n Iteration 2: RMSD = 0.12 px\n\nLocal alignments:\nPatches: X = %d Y = %d\n' % (case, 3 if local3 else 1, 3 if local3 else 1)
    if local3:
        for i in range(9):
            t += 'Patch (%d, %d): %d / 9\n' % (i // 3 + 1, i % 3 + 1, i + 1)
            if arm == 'ON':
                t += V3.WITNESS_LINE + '\n'
            t += ' Iteration 1: RMSD = 0.40 px\n Iteration 2: RMSD = 0.20 px\n'
    return t


def make_stdout(local3, g=(40, 40), l=None, gpeaks=None, patch_peaks=None, dc=True, dup=False, coupled=True):
    l = l if l is not None else ((360, 360) if local3 else (0, 0))
    gpeaks = g[1] if gpeaks is None else gpeaks
    lines = []
    dcl = 'MC_EXPERIMENT_CCF_DC arm=both cpu.global=%d/%d cpu.local=%d/%d cuda_single.global=0/0 cuda_single.local=0/0 cuda_batched.global=0/0 cuda_batched.local=0/0' % (g + l)
    if dc:
        lines.append(dcl)
        if dup:
            lines.append(dcl)
    if coupled:
        lines.append('[coupled_peak] scope=global peaks=%d guard_fired=2 (not_negative_definite=1, offset_gt_1px=1)' % gpeaks)
        pp = patch_peaks if patch_peaks is not None else (l[1] // 9 if local3 else 0)
        if local3 or pp:
            lines += ['[coupled_peak] scope=patch peaks=%d guard_fired=0 (not_negative_definite=0, offset_gt_1px=0)' % pp] * 9
    return '\n'.join(lines) + '\n'


class PW(TV3.World):
    """Pair world: scratch evidence root, baseline root, test admission with filled launch fields and matching pins."""
    def __init__(self, scratch):
        super().__init__(scratch)
        self.scratch = Path(scratch)
        self.base_root = self.scratch / 'baseline'
        self.dec = self.scratch / 'decision'
        self.n = 0
        self.adm['status'] = 'ADMITTED_TEST_ONLY'
        for k in P4.LAUNCH_FIELDS:
            self.adm[k] = 'test-' + k
        self.cases = {}

    # --- products --------------------------------------------------------------------------------------------------
    def star_text(self, case, arm, local3):
        if case in ('noisy', 'affine'):
            t = (RAW / case / 'UP_only' / 'output' / (case + '.star')).read_text()
            if arm == 'ON' and local3:
                head, tail = t.split('data_local_shift', 1)
                lines = tail.split('\n')
                for i, ln in enumerate(lines):
                    w = ln.split()
                    if len(w) == 5 and not w[0].startswith(('_', '#', 'data_')):
                        lines[i] = ln.rstrip() + '1'
                        break
                t = head + 'data_local_shift' + '\n'.join(lines)
            return t
        return ('data_general\n\n_rlnMicrographMovieName  %s.mrcs\n\ndata_global_shift\n\nloop_\n_rlnMicrographFrameNumber\n_rlnMicrographShiftX\n_rlnMicrographShiftY\n'
                '1 0.0 0.0\n2 0.1 0.2\n3 0.2 0.3\n4 0.3 0.5\n5 0.4 0.6\n\ndata_local_shift\n\nloop_\n' % case)

    def runtime_bytes(self, case, arm, local3):
        if case in ('noisy', 'affine'):
            b = (RAW / case / 'UP_only' / 'runtime.json').read_bytes()
            if arm == 'ON' and local3:
                m = json.loads(b); m['coeff_x'][0] += 1e-3
                return json.dumps(m).encode()
            return b
        return json.dumps({'local_enabled': False, 'global': [[0.0, 0.0], [0.1, 0.2], [0.2, 0.3], [0.3, 0.5], [0.4, 0.6]], 'coeff_x': [0.0] * 18, 'coeff_y': [0.0] * 18}).encode()

    def write_output(self, d, case, arm, local3):
        out = d / 'output'; R = str(out.resolve())
        mrc = bytes(range(256)) * 4 + (b'ON-PAYLOAD-LOCAL!' if (arm == 'ON' and local3) else b'OFF-PAYLOAD-0000!')[:16]
        files = {case + '.mrc': mrc, case + '.star': self.star_text(case, arm, local3).replace('@ROOT@', R).encode(),
                 case + '_shifts.eps': ('%%!PS root %s/%s_shifts.eps %s\n' % (R, case, case)).encode(),
                 'corrected_micrographs.star': ('data_x\n_rlnMicrographName %s/%s.mrc\n' % (R, case)).encode(),
                 'logfile.pdf': b'%PDF-1.4 fake ' + case.encode(), 'logfile.pdf.lst': ('lst ' + case + '\n').encode(),
                 case + '.log': make_log(case, arm, local3).encode()}
        for k in ('Early', 'Late', 'Total'):
            files['corrected_micrographs_all_rlnAccumMotion%s.eps' % k] = ('%%!PS %s/all%s.eps\n' % (R, k)).encode()
        for name, b in files.items():
            (out / name).write_bytes(b)

    def make(self, case):
        local3 = ROWS[case]['patch_grid'] == [3, 3]
        made = {}
        for arm in ('OFF', 'ON'):
            d, exp = self.build(case, arm)
            self.write_output(d, case, arm, local3)
            (d / 'runtime.json').write_bytes(self.runtime_bytes(case, arm, local3))
            (d / 'stdout.log').write_text(make_stdout(local3))
            self.write_receipt(d, exp)
            made[arm] = (d, exp)
        base = self.base_root / case
        if base.exists():
            shutil.rmtree(base)
        shutil.copytree(made['OFF'][0] / 'output', base / 'output')
        Roff, Rb = str((made['OFF'][0] / 'output').resolve()), str((base / 'output').resolve())
        for p in (base / 'output').iterdir():
            b = p.read_bytes()
            if Roff.encode() in b:
                p.write_bytes(b.replace(Roff.encode(), Rb.encode()))
        shutil.copy(made['OFF'][0] / 'runtime.json', base / 'runtime.json')
        shutil.copy(made['OFF'][0] / 'stdout.log', base / 'stdout.log')
        for n in ('RUN.json', 'admission.json', 'checker.json', 'checker.stdout', 'metrics.json', 'occupancy-before.txt', 'time.txt'):
            (base / n).write_text('baseline %s %s\n' % (case, n))
        self.repin(case)
        self.cases[case] = made
        return made, base

    def repin(self, case):
        base = self.base_root / case
        row = [r for r in self.adm['rows'] if r['case'] == case][0]
        for name in list(row['baseline_files']):
            b = (base / name).read_bytes()
            row['baseline_files'][name] = {'bytes': len(b), 'sha256': sha(b)}

    # --- plumbing ----------------------------------------------------------------------------------------------------
    def sync(self):
        p = self.scratch / 'ADMISSION_TEST.json'
        p.write_text(json.dumps(self.adm, indent=1))
        P4.ADMISSION_PATH, P4.ADMISSION_V3_SHA256 = p, sha(p.read_bytes())

    def kw(self, **over):
        self.n += 1
        kw = dict(evidence_root=self.root, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=self.dec)
        kw.update(over)
        return kw

    def gate(self, case, **over):
        self.sync()
        return P4.pre_ON_gate(case, self.root / case / 'OFF', self.base_root / case, **self.kw(**over))

    def pair(self, case, **over):
        self.sync()
        return P4.admit_pair(case, self.root / case / 'OFF', self.root / case / 'ON', self.base_root / case, **self.kw(**over))

    def edit(self, case, arm, rel, fn):
        d, exp = self.cases[case][arm]
        p = d / rel
        p.write_bytes(fn(p.read_bytes()))
        self.write_receipt(d, exp)


def fresh(fn, cases=('noisy',)):
    """Run fn(world) in a fresh scratch with the named cases built."""
    real = (P4.ADMISSION_PATH, P4.ADMISSION_V3_SHA256, P4.COMMANDS_PATH, P4.COMMANDS_V3_SHA256)
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v4-') as t:
        w = PW(Path(t).resolve())
        for c in cases:
            w.make(c)
        try:
            return fn(w)
        except Exception as e:  # an infrastructure fault must fail the suite, not abort the remaining checks
            import traceback
            record('INFRA fault in %s' % getattr(fn, '__name__', 'case'), False, ''.join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            P4.ADMISSION_PATH, P4.ADMISSION_V3_SHA256, P4.COMMANDS_PATH, P4.COMMANDS_V3_SHA256 = real


def crafted(rms, p95, mx, scale=1.0):
    a = {'rms': rms, 'p95': p95, 'max': mx}
    return {'runtime': {'angstrom': dict(a), 'px': {k: v / .885 for k, v in a.items()}}, 'STAR': {'angstrom': dict(a), 'px': {k: v / .885 for k, v in a.items()}}}


def crafted_scores(override=None):
    s = {}
    for c in ALL_CASES:
        if c in P4.P1_CASES:
            s[c] = {'OFF': crafted(.1, .2, .3), 'ON': crafted(.1, .2, .3)}
        elif c == 'noisy':
            s[c] = {'OFF': crafted(1.6, 3.3, 7.2), 'ON': crafted(1.2, 2.9, 6.0)}
        else:
            s[c] = {'OFF': crafted(2.0, 4.0, 8.0), 'ON': crafted(2.0, 4.0, 8.0)}
    for (c, arm), v in (override or {}).items():
        s[c][arm] = v
    return s


def main(result_path):
    # ---- trust roots and signatures -------------------------------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v4-') as t:
        t = Path(t)
        expect_code('real HELD admission cannot satisfy pre_ON_gate', 'HELD', lambda: P4.pre_ON_gate('noisy', t / 'o', t / 'b', evidence_root=t / 'ev', roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=t / 'dec'))
        expect_code('real HELD admission cannot satisfy admit_pair', 'HELD', lambda: P4.admit_pair('noisy', t / 'o', t / 'n', t / 'b', evidence_root=t / 'ev', roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=t / 'dec2'))
        expect_code('real HELD admission cannot satisfy decide_pilot', 'HELD', lambda: P4.decide_pilot(evidence_root=t / 'ev', baseline_root=t / 'b', fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=t / 'dec3'))
        record('HELD failure is retained as STOP.json', json.loads((t / 'dec' / 'STOP.json').read_text())['code'] == 'HELD')
    for fn_name, extra in [('pre_ON_gate', {'pre_on_status': 'PASS'}), ('admit_pair', {'expected': {}}), ('admit_pair', {'admission': {}}),
                           ('admit_pair', {'commands': []}), ('decide_pilot', {'pair_records': {}}), ('decide_pilot', {'scores': {}}),
                           ('admit_single', {'expected': {}})]:
        f = getattr(P4, fn_name)
        try:
            if fn_name == 'pre_ON_gate':
                f('noisy', 'a', 'b', evidence_root='e', roots={}, binary_path=BIN, binary_sha256=BINSHA, decision_dir='d', **extra)
            elif fn_name == 'admit_pair':
                f('noisy', 'a', 'b', 'c', evidence_root='e', roots={}, binary_path=BIN, binary_sha256=BINSHA, decision_dir='d', **extra)
            elif fn_name == 'admit_single':
                f('noisy', 'OFF', 'a', evidence_root='e', roots={}, binary_path=BIN, binary_sha256=BINSHA, **extra)
            else:
                f(evidence_root='e', baseline_root='b', fixture_dir='f', roots={}, binary_path=BIN, binary_sha256=BINSHA, decision_dir='d', **extra)
            record('signature rejects caller-typed %s on %s' % (list(extra), fn_name), False, 'accepted')
        except TypeError:
            record('signature rejects caller-typed %s on %s' % (list(extra), fn_name), True)

    # ---- positives -------------------------------------------------------------------------------------------------------
    def pos(w):
        rec = w.gate('noisy')
        record('positive pre_ON_gate noisy (comparator subprocess ran)', rec['status'] == 'PASS' and (w.dec / 'pre_on' / 'noisy' / 'command.json').is_file() and (w.dec / 'pre_on' / 'noisy' / 'compare_products.json').is_file() and rec['bound']['comparator']['n_gated'] >= 5, 'binding=%s' % rec['binding_sha256'][:12])
        cmd = json.loads((w.dec / 'pre_on' / 'noisy' / 'command.json').read_text())
        record('retained comparator command is the pinned script via python -B', cmd['argv'][1] == '-B' and cmd['argv'][2].endswith('compare_products.py') and cmd['comparator_sha256'] == '53449d2da682305c8c11e3ed3efb91103530196e481ac075b00f90e3d5ea0f47' and cmd['returncode'] == 0)
        raw_star_differs = (RAW / 'noisy' / 'UP_only' / 'output' / 'noisy.star').read_bytes() == (w.base_root / 'noisy' / 'output' / 'noisy.star').read_bytes()
        eps_b = (w.base_root / 'noisy' / 'output' / 'noisy_shifts.eps').read_bytes(); eps_o = (w.cases['noisy']['OFF'][0] / 'output' / 'noisy_shifts.eps').read_bytes()
        record('control: raw EPS text differs between baseline and OFF (comparator normalises the root)', eps_b != eps_o)
        pr = w.pair('noisy')
        record('positive admit_pair 3x3', pr['global_bits_equal'] and pr['witness_lines'] == {'OFF': 0, 'ON': 9} and pr['global_only_comparator'] is None and pr['counters']['ON']['dc']['local_eligible'] == 360 and pr['local_enabled']['ON'] is True)
        record('pair record keeps convergence/local_enabled separately', set(pr['convergence']) == {'OFF', 'ON'} and len(pr['convergence']['ON']['patches']) == 9)
        record('pre-ON record binds identity and pins', all(k in rec['bound'] for k in ('off_receipt_sha256', 'baseline_inventory_sha256', 'comparator', 'admission_sha256', 'tool_pins_sha256', 'binary_sha256', 'identity')) and rec['bound']['identity']['candidate_binary'] == 'test-candidate_binary')
    fresh(pos)

    def pos_global(w):
        w.gate('flat'); pr = w.pair('flat')
        record('positive admit_pair global-only incl. whole-product comparator', pr['global_only_comparator'] is not None and pr['witness_lines'] == {'OFF': 0, 'ON': 0} and pr['counters']['ON']['dc']['local_eligible'] == 0)
        record('retained global-only comparator output is outside product dirs', (w.dec / 'pair' / 'flat' / 'compare_products.json').is_file() and not (w.cases['flat']['ON'][0] / 'compare_products.json').exists())
    fresh(pos_global, ('flat',))

    def pos_inventory_only(w):
        # logs and PDFs are inventory-only in the pinned comparator: differing bytes there do not fail the OFF gate
        d, exp = w.cases['noisy']['OFF']
        (d / 'output' / 'logfile.pdf').write_bytes(b'%PDF-1.4 a different render'); w.write_receipt(d, exp)
        base_pdf = w.base_root / 'noisy' / 'output' / 'logfile.pdf'
        record('control: inventory-only PDF differs from baseline yet pre-ON passes', (base_pdf.read_bytes() != (d / 'output' / 'logfile.pdf').read_bytes()) and w.gate('noisy')['status'] == 'PASS')
    fresh(pos_inventory_only)

    # ---- anchors: altered files and hand-edited commands -------------------------------------------------------------------
    def anchors(w):
        w.sync()
        p = P4.ADMISSION_PATH
        alt = w.scratch / 'adm_alt.json'; alt.write_text(p.read_text().replace('ADMITTED_TEST_ONLY', 'ADMITTED_TEST_ONLY '))
        P4.ADMISSION_PATH = alt
        expect_code('altered anchored admission file refused', 'ANCHOR', lambda: P4.pre_ON_gate('noisy', w.root / 'noisy' / 'OFF', w.base_root / 'noisy', **w.kw()))
        P4.ADMISSION_PATH = p
        cmds = json.loads((PILOT / 'COMMANDS_DRAFT_v3.json').read_text())
        for r in cmds:
            r['argv'][r['argv'].index('--max_iter') + 1] = '9'; r['environment']['OMP_NUM_THREADS'] = '8'
        cp = w.scratch / 'commands_hand.json'; cp.write_text(json.dumps(cmds, indent=2) + '\n')
        P4.COMMANDS_PATH = cp
        expect_code('hand-edited commands (max_iter 9, OMP 8) refused by the anchor', 'ANCHOR', lambda: P4.pre_ON_gate('noisy', w.root / 'noisy' / 'OFF', w.base_root / 'noisy', **w.kw()))
        P4.COMMANDS_PATH = PILOT / 'COMMANDS_DRAFT_v3.json'
        w.adm_backup = copy.deepcopy(w.adm)
        w.adm['status'] = 'HELD_SOURCE_REVIEW_AND_VENUE_INPUTS_PENDING'
        expect_code('HELD status in an otherwise filled admission refused', 'HELD', lambda: w.gate('noisy'))
        w.adm['status'] = 'ADMITTED_TEST_ONLY'
        for k in P4.LAUNCH_FIELDS:
            saved = w.adm[k]; w.adm[k] = None
            expect_code('null launch field %s refused' % k, 'HELD', lambda: w.gate('noisy', decision_dir=w.scratch / ('d_' + k)))
            w.adm[k] = saved
        expect_code('unresolved placeholder binary path refused', 'PLACEHOLDER', lambda: w.gate('noisy', binary_path='<PINNED_LINUX_BINARY>', decision_dir=w.scratch / 'd_ph'))
        expect_code('non-hex binary sha refused', 'BINARY', lambda: w.gate('noisy', binary_sha256='XY' * 32, decision_dir=w.scratch / 'd_hex'))
        roots = dict(ROOTS, repo=w.scratch)
        expect_code('tool pins verified before use', 'TOOL_PIN', lambda: w.gate('noisy', roots=roots, decision_dir=w.scratch / 'd_pin'))
        expect_code('decision_dir inside a run directory refused', 'DECISION_DIR', lambda: w.gate('noisy', decision_dir=w.cases['noisy']['OFF'][0] / 'dec'))
    fresh(anchors)

    # ---- handbuilt grid cannot bypass: a 3x3 ON run with zero witnesses ----------------------------------------------------
    def grid(w):
        d, exp = w.cases['noisy']['ON']
        lp = d / 'output' / 'noisy.log'; lp.write_text(lp.read_text().replace(V3.WITNESS_LINE + '\n', '')); w.write_receipt(d, exp)
        w.sync()
        expect_code('3x3 ON with 0 witnesses cannot be admitted (grid comes from the anchored admission)', 'WITNESS', lambda: P4.admit_single('noisy', 'ON', d, evidence_root=w.root, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA))
    fresh(grid)

    # ---- baseline / OFF / comparator negatives -----------------------------------------------------------------------------
    def base_edit(case, rel, fn, repin):
        def run(w):
            p = w.base_root / case / rel
            p.write_bytes(fn(p.read_bytes()))
            if repin:
                w.repin(case)
            return w
        return run

    def case_neg(name, code, setup, case='noisy', check=None, cases=None):
        def run(w):
            setup(w)
            expect_code(name, code, lambda: w.gate(case))
            if check:
                record(name + ' [evidence]', check(w), '')
        fresh(run, cases or (case,))

    case_neg('baseline byte changed (pin kept)', 'BASELINE', lambda w: base_edit('noisy', 'output/noisy.mrc', lambda b: b[:-1] + b'X', False)(w))
    def base_extra(w): (w.base_root / 'noisy' / 'output' / 'extra.txt').write_text('x')
    case_neg('baseline extra file', 'BASELINE', base_extra)
    def base_missing(w): (w.base_root / 'noisy' / 'time.txt').unlink()
    case_neg('baseline file missing', 'BASELINE', base_missing)
    def base_link(w):  # the symlink target holds the pinned bytes, so only the symlink guard can reject it
        p = w.base_root / 'noisy' / 'time.txt'; keep = w.scratch / 'time_target.txt'; keep.write_bytes(p.read_bytes()); p.unlink(); os.symlink(keep, p)
    case_neg('baseline file replaced by a symlink', 'BASELINE', base_link)
    def hdr(w): base_edit('noisy', 'output/noisy.mrc', lambda b: b[:10] + b'\xff' + b[11:], True)(w)
    case_neg('comparator detects MRC header change', 'COMPARATOR', hdr, check=lambda w: json.loads((w.dec / 'pre_on' / 'noisy' / 'compare_products.json').read_text())['verdict'] == 'DIFFERENT' and any(r.get('header_0_223_equal') is False for r in json.loads((w.dec / 'pre_on' / 'noisy' / 'compare_products.json').read_text())['rows']))
    def pay(w): base_edit('noisy', 'output/noisy.mrc', lambda b: b[:1030] + b'\x01' + b[1031:], True)(w)
    case_neg('comparator detects MRC payload change', 'COMPARATOR', pay, check=lambda w: any(r.get('pixels_equal') is False for r in json.loads((w.dec / 'pre_on' / 'noisy' / 'compare_products.json').read_text())['rows']))
    def eps(w): base_edit('noisy', 'output/noisy_shifts.eps', lambda b: b + b'changed', True)(w)
    case_neg('comparator detects EPS change', 'COMPARATOR', eps)
    def cstar(w): base_edit('noisy', 'output/corrected_micrographs.star', lambda b: b + b'changed', True)(w)
    case_neg('comparator detects corrected_micrographs STAR change', 'COMPARATOR', cstar)
    def off_runtime(w):
        d, exp = w.cases['noisy']['OFF']; m = json.loads((d / 'runtime.json').read_text()); m['coeff_x'][1] += 1e-9
        (d / 'runtime.json').write_text(json.dumps(m)); w.write_receipt(d, exp)
    case_neg('OFF runtime differs from the retained baseline bytes', 'OFF_RAW', off_runtime)
    def off_star(w): w.edit('noisy', 'OFF', 'output/noisy.star', lambda b: b + b'\n# edited\n')
    case_neg('OFF case STAR differs from the retained baseline bytes', 'OFF_RAW', off_star)
    def off_noruntime(w):
        d, exp = w.cases['noisy']['OFF']; (d / 'runtime.json').unlink()
    case_neg('OFF runtime.json missing', 'RUNTIME', off_noruntime)
    def off_witness(w): w.edit('noisy', 'OFF', 'output/noisy.log', lambda b: b + (V3.WITNESS_LINE + '\n').encode())
    case_neg('OFF with a witness line is not an OFF run', 'WITNESS', off_witness)

    def inv(w):
        w.sync(); ctx = P4._Ctx(ROOTS, w.root, BIN, BINSHA, w.dec, True)
        a = w.scratch / 'tree_a'; b = w.scratch / 'tree_b'
        shutil.copytree(w.base_root / 'noisy' / 'output', a); shutil.copytree(w.base_root / 'noisy' / 'output', b); (b / 'logfile.pdf.lst').unlink()
        expect_code('comparator detects a file-inventory difference', 'COMPARATOR', lambda: P4._compare(ctx, a, b, w.scratch / 'cmp_inv'))
        j = json.loads((w.scratch / 'cmp_inv' / 'compare_products.json').read_text())
        record('inventory difference recorded by the comparator itself', j['verdict'] == 'DIFFERENT' and any(r['file'] == 'logfile.pdf.lst' and r['in_b'] is False for r in j['rows']))
        c = json.loads((w.scratch / 'cmp_inv' / 'command.json').read_text())
        record('failed comparator rc retained', c['returncode'] == 1)
    fresh(inv)

    def stop_before_on(w):
        base_edit('noisy', 'output/noisy.mrc', lambda b: b[:1030] + b'\x01' + b[1031:], True)(w)
        expect_code('failing OFF gate raises before ON', 'COMPARATOR', lambda: w.gate('noisy'))
        stop = json.loads((w.dec / 'STOP.json').read_text())
        record('STOP.json retained with the code', stop['code'] == 'COMPARATOR')
        expect_code('ON cannot be paired without a passing record', 'PRE_ON', lambda: w.pair('noisy', decision_dir=w.dec))
    fresh(stop_before_on)

    # ---- pre-ON record binding ---------------------------------------------------------------------------------------------
    def rec_tests(w):
        expect_code('absent pre-ON record', 'PRE_ON', lambda: w.pair('noisy', decision_dir=w.scratch / 'd_none'))
        rec = w.gate('noisy')
        rp = w.dec / 'pre_on' / 'noisy' / 'pre_on.json'
        good = rp.read_text()
        j = json.loads(good); j['bound']['binary_sha256'] = 'ef' * 32; rp.write_text(json.dumps(j))
        expect_code('tampered pre-ON record', 'PRE_ON', lambda: w.pair('noisy'))
        j = json.loads(good); j['status'] = 'FAIL'; rp.write_text(json.dumps(j))
        expect_code('pre-ON record status not PASS', 'PRE_ON', lambda: w.pair('noisy'))
        rp.write_text(good)
        w.edit('noisy', 'OFF', 'output/logfile.pdf', lambda b: b + b'x')
        expect_code('record bound to a different OFF byte', 'PRE_ON', lambda: w.pair('noisy'))
    fresh(rec_tests)

    def comparator_json_tamper(w):
        w.gate('noisy'); jp = w.dec / 'pre_on' / 'noisy' / 'compare_products.json'
        j = json.loads(jp.read_text()); j['n_files'] += 1; jp.write_text(json.dumps(j))
        expect_code('retained comparator JSON altered after the gate', 'PRE_ON', lambda: w.pair('noisy'))
    fresh(comparator_json_tamper)

    # ---- pair negatives (3x3) ------------------------------------------------------------------------------------------------
    def pair_neg(name, code, setup, case='noisy', pre=False):
        def run(w):
            if pre:
                setup(w); w.gate(case)  # an OFF-side defect present when the gate ran: the pair layer must still find it
            else:
                w.gate(case); setup(w)
            expect_code(name, code, lambda: w.pair(case))
        fresh(run, (case,))

    def ulp(w):
        d, exp = w.cases['noisy']['ON']; import numpy as np
        m = json.loads((d / 'runtime.json').read_text()); m['global'][1][0] = float(np.nextafter(m['global'][1][0], 1.0))
        (d / 'runtime.json').write_text(json.dumps(m)); w.write_receipt(d, exp)
    pair_neg('ON global runtime differs by 1 ulp', 'GLOBAL_RUNTIME', ulp)
    def gstar(w):
        def f(b):
            t = b.decode(); i = t.index('data_global_shift'); j = t.index('data_local_motion_model')
            blk = t[i:j]; ln = [x for x in blk.split('\n') if len(x.split()) >= 3 and not x.startswith(('_', 'data', 'loop'))][1]
            return (t[:i] + blk.replace(ln, ln + '0', 1) + t[j:]).encode()
        w.edit('noisy', 'ON', 'output/noisy.star', f)
    pair_neg('ON serialised global STAR block differs', 'GLOBAL_STAR', gstar)
    def ondc_missing(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, dc=False).encode())
    pair_neg('ON missing DC stage line', 'MANIPULATION', ondc_missing)
    def offdc_zero(w): w.edit('noisy', 'OFF', 'stdout.log', lambda b: make_stdout(True, g=(0, 0), gpeaks=0).encode())
    pair_neg('OFF zero global DC counters', 'MANIPULATION', offdc_zero, pre=True)
    pair_neg('OFF zero global DC counters edited after the gate', 'PRE_ON', offdc_zero)
    def drift(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, g=(41, 41)).encode())
    pair_neg('global DC counters drift between OFF and ON', 'COUNTERS', drift)
    def zeroed_drift(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, g=(39, 40), gpeaks=40).encode())
    pair_neg('global zeroed count drifts (zeroed != eligible)', 'MANIPULATION', zeroed_drift)
    def gcoupled_drift(w):
        w.edit('noisy', 'ON', 'stdout.log', lambda b: b.replace(b'scope=global peaks=40 guard_fired=2 (not_negative_definite=1, offset_gt_1px=1)', b'scope=global peaks=40 guard_fired=3 (not_negative_definite=2, offset_gt_1px=1)'))
    pair_neg('global coupled counters drift', 'COUNTERS', gcoupled_drift)
    def l0(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, l=(0, 0), patch_peaks=0).encode())
    pair_neg('3x3 ON local eligible 0', 'MANIPULATION', l0)
    def off_l0(w): w.edit('noisy', 'OFF', 'stdout.log', lambda b: make_stdout(True, l=(0, 0), patch_peaks=0).encode())
    pair_neg('3x3 OFF local eligible 0', 'MANIPULATION', off_l0, pre=True)
    def cov(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, gpeaks=39).encode())
    pair_neg('coupled global peaks disagree with DC eligible', 'MANIPULATION', cov)
    def lcov(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, patch_peaks=39).encode())
    pair_neg('coupled patch peaks disagree with local DC eligible', 'MANIPULATION', lcov)
    def dup(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, dup=True).encode())
    pair_neg('duplicate DC counter line', 'MANIPULATION', dup)
    def nocoup(w): w.edit('noisy', 'ON', 'stdout.log', lambda b: make_stdout(True, coupled=False).encode())
    pair_neg('coupled counters absent', 'MANIPULATION', nocoup)
    def noconv(w): w.edit('noisy', 'ON', 'output/noisy.log', lambda b: b.replace(b'Global alignment:', b'Global shifts:'))
    pair_neg('convergence log unparsable', 'CONVERGENCE', noconv)
    def sameb(w):
        d, exp = w.cases['noisy']['ON']
        w.write_receipt(d, exp, lambda r: r.__setitem__('binary_sha256', 'cd' * 32))
    pair_neg('same binary path with a different sha256 in ON', 'BINARY', sameb)
    def on_extra(w): (w.cases['noisy']['ON'][0] / 'output' / 'stray.txt').write_text('x')
    pair_neg('ON extra output file', 'INVENTORY', on_extra)
    def on_variant(w): w.edit('noisy', 'ON', 'output/noisy.log', lambda b: b + b' EXPERIMENTAL local fullwidth weight: x_norm = 42, pnx = 42, nfx = 22\n')
    pair_neg('ON witness variant spelling', 'WITNESS_VARIANT', on_variant)

    # ---- global-only negatives -------------------------------------------------------------------------------------------------
    def go_neg(name, code, setup):
        def run(w):
            w.gate('flat'); setup(w)
            expect_code(name, code, lambda: w.pair('flat'))
        fresh(run, ('flat',))
    def go_payload(w): w.edit('flat', 'ON', 'output/flat.mrc', lambda b: b[:1030] + b'\x07' + b[1031:])
    go_neg('global-only ON MRC payload differs (comparator)', 'GLOBAL_ONLY', go_payload)
    def go_hdr(w): w.edit('flat', 'ON', 'output/flat.mrc', lambda b: b[:20] + b'\x07' + b[21:])
    go_neg('global-only ON MRC header differs (comparator)', 'GLOBAL_ONLY', go_hdr)
    def go_eps(w): w.edit('flat', 'ON', 'output/flat_shifts.eps', lambda b: b + b'x')
    go_neg('global-only ON EPS differs (comparator)', 'GLOBAL_ONLY', go_eps)
    def go_rt(w): w.edit('flat', 'ON', 'runtime.json', lambda b: b + b' ')
    go_neg('global-only ON runtime bytes differ', 'GLOBAL_ONLY', go_rt)
    def go_star(w): w.edit('flat', 'ON', 'output/flat.star', lambda b: b + b'# trailing\n')
    go_neg('global-only ON case STAR bytes differ', 'GLOBAL_ONLY', go_star)
    def go_local(w): w.edit('flat', 'ON', 'stdout.log', lambda b: make_stdout(True).encode())
    go_neg('global-only ON has local DC/coupled work', 'MANIPULATION', go_local)
    def go_witness(w): w.edit('flat', 'ON', 'output/flat.log', lambda b: b + (V3.WITNESS_LINE + '\n').encode())
    go_neg('global-only ON carries a witness line', 'WITNESS', go_witness)

    # ---- R2 LOW tests ------------------------------------------------------------------------------------------------------------
    def variants(w):
        w.sync()
        for label, line in [('lowercase hyphenless', ' experimental local fullwidth weight: x_norm = 42, pnx = 42, nfx = 22'),
                            ('underscored', ' EXPERIMENTAL local_full_width weight x_norm = 42'),
                            ('title case', ' Experimental Local Full-Width Weight: x_norm = 42'),
                            ('spaced', ' EXPERIMENTAL local full width weight: x_norm = 42, pnx = 42, nfx = 22')]:
            d, exp = w.cases['flat']['OFF']
            lp = d / 'output' / 'flat.log'; orig = lp.read_text(); lp.write_text(orig + line + '\n'); w.write_receipt(d, exp)
            try:
                V3.admit_producer(d, exp, w.adm, w.root); v3 = 'v3 admits'
            except V3.AdmissionError as e:
                v3 = 'v3 rejects %s' % e.code
            expect_code('witness variant (%s) rejected by the prescan' % label, 'WITNESS_VARIANT', lambda: P4.admit_single('flat', 'OFF', d, evidence_root=w.root, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA))
            record('control: %s [%s]' % (label, v3), v3 == 'v3 admits' or label == 'title case', v3)
            lp.write_text(orig); w.write_receipt(d, exp)
        try:
            P4.admit_single('flat', 'OFF', w.cases['flat']['OFF'][0], evidence_root=w.root, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA)
            record('control: clean OFF log passes the prescan', True)
        except Exception as e:
            record('control: clean OFF log passes the prescan', False, repr(e))
    fresh(variants, ('flat',))

    def t_tests(w):
        w.sync()
        # T1: an extra staged file whose bytes DO match a fixture pin; only the names guard can reject it
        d, exp = w.cases['noisy']['OFF']
        (d / 'input' / 'extra.bin').write_bytes(b'extra staged'); w.adm['fixture_files']['extra.bin'] = {'bytes': 12, 'sha256': sha(b'extra staged')}
        expect_code('T1 extra staged file with a matching fixture pin', 'INPUT', lambda: V3.admit_producer(d, exp, w.adm, w.root))
        (d / 'input' / 'extra.bin').unlink()
        # T1b: staged movie missing while every present file matches its pin
        (d / 'input' / 'noisy.mrcs').unlink()
        expect_code('T1 missing staged movie, remaining pins match', 'INPUT', lambda: V3.admit_producer(d, exp, w.adm, w.root))
    fresh(t_tests)

    def t2(w):
        d, exp = w.cases['noisy']['OFF']
        text = (d / 'runtime.json').read_text()
        tok = '-0.60471920692772696'  # the retained noisy runtime's global[1][0] literal
        record('control: the retained runtime text carries that literal', tok in text)
        (d / 'runtime.json').write_text(text.replace(tok, '1e400', 1)); w.write_receipt(d, exp)
        parsed = json.loads((d / 'runtime.json').read_text())['global'][1][0]
        record('control: Python parses 1e400 as inf without parse_constant', parsed == float('inf'))
        expect_code('T2 runtime overflow literal 1e400 with a matching receipt hash', 'NONFINITE', lambda: V3.admit_producer(d, exp, w.adm, w.root))
    fresh(t2)

    def t3(w):
        d, exp = w.cases['noisy']['OFF']
        real = w.scratch / 'target.pdf'; real.write_bytes((d / 'output' / 'logfile.pdf').read_bytes())
        (d / 'output' / 'logfile.pdf').unlink(); os.symlink(real, d / 'output' / 'logfile.pdf')
        b = real.read_bytes()
        def edit(r): r['publication']['logfile.pdf'] = {'bytes': len(b), 'sha256': sha(b)}
        w.write_receipt(d, exp, edit)
        rr = json.loads((d / 'RUN.json').read_text())
        record('control: the receipt lists the symlink with the target hash', rr['publication']['logfile.pdf']['sha256'] == sha(b) and (d / 'output' / 'logfile.pdf').is_symlink())
        expect_code('T3 real symlink in output with a self-consistent receipt', 'INVENTORY', lambda: V3.admit_producer(d, exp, w.adm, w.root))
    fresh(t3)

    # ---- decision rules (pure) -----------------------------------------------------------------------------------------------------
    base = P4._decide(crafted_scores())
    record('decision: P1 and P2 hold -> SUPPORTED, never accepted', base['prediction'] == 'SUPPORTED' and base['acceptance'] == 'NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE' and base['P1']['ok'] and base['P2']['ok'])
    record('decision: improving P2 leaves the noisy raw gate FAIL', base['noisy_raw_gate'] == 'FAIL' and base['noisy_raw_gate_by_field'] == {'runtime': 'FAIL', 'STAR': 'FAIL'})
    record('decision: flat/repeated UNIDENTIFIABLE with raw distances', all(base['unidentifiable'][c]['status'] == 'UNIDENTIFIABLE' and 'rms' in base['unidentifiable'][c]['raw_distances_angstrom']['ON']['runtime'] for c in ('flat', 'repeated')) and 'gate' not in json.dumps(base['unidentifiable']))
    record('decision: no increase listed when nothing increases', base['increases'] == [])
    s = crafted_scores({('fractional', 'ON'): dict(crafted(.1, .2, .3), STAR={'angstrom': {'rms': .21, 'p95': .2, 'max': .3}, 'px': {'rms': .2, 'p95': .2, 'max': .3}})})
    d = P4._decide(s)
    record('decision: P1 lost on one case/field (fractional STAR rms .21)', d['P1']['ok'] is False and d['prediction'] == 'NOT_SUPPORTED' and d['P1']['cases']['fractional']['ON']['STAR'] == 'FAIL' and d['P1']['cases']['affine']['ON']['STAR'] == 'PASS')
    record('decision: the P1 loss is listed as a PASS->FAIL increase', any(i['case'] == 'fractional' and i['field'] == 'STAR' and i['metric'] == 'rms' and i['gate_transition'] == 'PASS->FAIL' for i in d['increases']))
    for metric in ('rms', 'p95', 'max'):
        on = {'rms': 1.2, 'p95': 2.9, 'max': 6.0}; on[metric] = {'rms': 1.7, 'p95': 3.4, 'max': 7.3}[metric]
        d = P4._decide(crafted_scores({('noisy', 'ON'): {'runtime': {'angstrom': dict(on), 'px': dict(on)}, 'STAR': {'angstrom': {'rms': 1.2, 'p95': 2.9, 'max': 6.0}, 'px': dict(on)}}}))
        record('decision: P2 fails on a single regressed %s (runtime only)' % metric, d['P2']['ok'] is False and d['P2']['noisy']['runtime'][metric]['strictly_lower'] is False and d['prediction'] == 'NOT_SUPPORTED')
        on = {'rms': 1.2, 'p95': 2.9, 'max': 6.0}; on[metric] = {'rms': 1.6, 'p95': 3.3, 'max': 7.2}[metric]
        d = P4._decide(crafted_scores({('noisy', 'ON'): {'runtime': {'angstrom': dict(on), 'px': dict(on)}, 'STAR': {'angstrom': {'rms': 1.2, 'p95': 2.9, 'max': 6.0}, 'px': dict(on)}}}))
        record('decision: P2 fails on a tie in %s (strict improvement required)' % metric, d['P2']['ok'] is False)
    s = crafted_scores({('zero', 'ON'): crafted(.15, .25, .35)})
    d = P4._decide(s)
    record('decision: PASS->PASS increase is listed and P1 still holds', d['P1']['ok'] and {(i['metric'], i['gate_transition']) for i in d['increases'] if i['case'] == 'zero' and i['field'] == 'runtime'} == {('rms', 'PASS->PASS'), ('p95', 'PASS->PASS'), ('max', 'PASS->PASS')})
    d = P4._decide(crafted_scores({('noisy', 'ON'): crafted(.1, .2, .3)}))
    record('decision: a noisy ON that passes all limits reports raw gate PASS', d['noisy_raw_gate'] == 'PASS' and d['P2']['ok'])

    # ---- decide_pilot end to end: structure -------------------------------------------------------------------------------------------
    def build_all(w):
        for c in ALL_CASES:
            if c not in w.cases:
                w.make(c)
        for c in ALL_CASES:
            w.gate(c)

    def e2e(w):
        build_all(w); w.sync()
        orig = P4._score_arm
        P4._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: crafted_scores()[case][arm]
        try:
            res = P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.dec)
            record('decide_pilot over 8 synthetic cases (crafted scores)', res['prediction'] == 'SUPPORTED' and set(res['pair_record_sha256']) == set(ALL_CASES) and (w.dec / 'DECISION.json').is_file())
            record('all 8 pair records retained', all((w.dec / 'pair' / c / 'pair.json').is_file() for c in ALL_CASES))
            expect_code('cases parameter reordered', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd2', cases=list(reversed(ALL_CASES))))
            expect_code('cases parameter with a duplicate', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd3', cases=ALL_CASES[:-1] + ['noisy']))
            expect_code('cases parameter missing a case', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd4', cases=ALL_CASES[:-1]))
            (w.root / 'extra_case').mkdir()
            expect_code('unlisted extra case directory', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd5'))
            (w.root / 'extra_case').rmdir()
            shutil.move(str(w.root / 'repeated' / 'ON'), str(w.scratch / 'parked_on'))
            expect_code('case without its ON directory', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd6'))
            shutil.move(str(w.scratch / 'parked_on'), str(w.root / 'repeated' / 'ON'))
            shutil.rmtree(w.root / 'zero')
            expect_code('a case directory missing entirely', 'CASES', lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.scratch / 'd7'))
        finally:
            P4._score_arm = orig
    fresh(e2e, ())

    def e2e_real(w):
        build_all(w); w.sync()
        orig = P4._score_arm
        crafted_all = crafted_scores()
        def scorer(case, arm, run_dir, expected, adm, ev, fx):
            if case in ('noisy', 'affine'):
                return orig(case, arm, run_dir, expected, adm, ev, fx)
            return crafted_all[case][arm]
        P4._score_arm = scorer
        try:
            res = P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=FIX, roots=ROOTS, binary_path=BIN, binary_sha256=BINSHA, decision_dir=w.dec)
            old = json.loads((RAW / 'noisy' / 'UP_only' / 'metrics.json').read_text())
            got = res['P2']['noisy']['runtime']['rms']['OFF']
            record('real noisy/affine scoring flows through decide_pilot', abs(got - old['runtime']['angstrom']['rms']) <= 1e-12, 'noisy OFF rms=%.12f' % got)
            record('real data: the tiny coefficient change does not improve every metric, so P2 fails (no vacuous PASS)', res['P2']['ok'] is False and res['prediction'] == 'NOT_SUPPORTED')
            record('real affine ON keeps PASS on both fields', res['P1']['cases']['affine']['ON'] == {'runtime': 'PASS', 'STAR': 'PASS'})
        finally:
            P4._score_arm = orig
    fresh(e2e_real, ())

    failed = [r for r in RESULTS if not r['ok']]
    Path(result_path).write_text(json.dumps({'total': len(RESULTS), 'failed': len(failed), 'results': RESULTS}, indent=1, allow_nan=False) + '\n')
    print('TOTAL %d FAILED %d' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
