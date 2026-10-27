"""Focused tests for score_fields_v3 (criteria frozen in SCORER_V3_PLAN.md). Scratch files only; no producer, no movie pixels.

usage: python -B tests/test_score_fields_v3.py RESULT.json   (real NumPy interpreter; run with OMP/OPENBLAS threads <= 2)
"""
import copy, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PILOT))
import score_fields_v3 as V3
import score_fields_v2 as V2

RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
FIX = Path('/tmp/motioncorr-b2-retained-challenge-20261026/v2fixtures')
REPO = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/experiment-local-full-width-weight-20261026')
CONSUMER = Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
ADM = json.loads((PILOT / 'ADMISSION_DRAFT_v3.json').read_text())
CMD = json.loads((PILOT / 'COMMANDS_DRAFT_v3.json').read_text())
BIN, BINSHA = '/fake/venue/bin/motioncorr', 'ab' * 32
sha = lambda b: hashlib.sha256(b).hexdigest()
RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''), flush=True)


class World:
    """One scratch evidence root with a test copy of the admission whose fixture pins match the fake inputs."""
    def __init__(self, scratch):
        self.root = Path(scratch) / 'ev'
        self.adm = copy.deepcopy(ADM)
        self.fixtures = {}

    def fake(self, case, name):
        return (name + ' ' + case + ' fake').encode()

    def build(self, case, arm, *, log_witness=None, patch=None, runtime_bytes=None, star_bytes=None, root=None):
        root = Path(root or self.root)
        exp = V3.resolve_expected_row(CMD, self.adm, case, arm, root, BIN, BINSHA)
        d = root / case / arm
        if d.exists():
            shutil.rmtree(d)
        (d / 'input').mkdir(parents=True); (d / 'output').mkdir()
        for n in exp['input_files']:
            b = self.fake(case, n); (d / 'input' / n).write_bytes(b)
            self.adm['fixture_files'][n] = {'bytes': len(b), 'sha256': sha(b)}
        real = case == 'noisy'
        for rel in exp['expected_output_names']:
            if rel == case + '.log':
                n = exp['expected_witness_lines'] if log_witness is None else log_witness
                text = 'Working on %s.mrcs with 2 thread(s).\n\nGlobal alignment:\n' % case + ' Iteration 1: RMSD = 1 px\n'
                text += ''.join('Patch (1, %d): %d / 9\n%s\n Iteration 1: RMSD = 1 px\n' % (i, i, V3.WITNESS_LINE) for i in range(1, n + 1))
                (d / 'output' / rel).write_text(text)
            elif rel == case + '.star':
                if star_bytes is not None:
                    (d / 'output' / rel).write_bytes(star_bytes)
                elif real:
                    shutil.copy(RAW / 'noisy' / 'UP_only' / 'output' / 'noisy.star', d / 'output' / rel)
                else:
                    (d / 'output' / rel).write_text('data_general\n\n_rlnMicrographMovieName  %s.mrcs\n' % case)
            else:
                (d / 'output' / rel).write_bytes(self.fake(case, rel))
        if runtime_bytes is not None:
            (d / 'runtime.json').write_bytes(runtime_bytes)
        elif real:
            shutil.copy(RAW / 'noisy' / 'UP_only' / 'runtime.json', d / 'runtime.json')
        else:
            (d / 'runtime.json').write_text(json.dumps({'local_enabled': False, 'global': [[0.0, 0.0]] * 5, 'coeff_x': [0.0] * 18, 'coeff_y': [0.0] * 18}))
        (d / 'stdout.log').write_text('stdout of %s %s\n' % (case, arm))
        self.write_receipt(d, exp)
        return d, exp

    def write_receipt(self, d, exp, edit=None):
        pub = {}
        out = d / 'output'
        for p in sorted(out.rglob('*')):
            if p.is_file() and not p.is_symlink():
                b = p.read_bytes(); pub[p.relative_to(out).as_posix()] = {'bytes': len(b), 'sha256': sha(b)}
        pin = lambda n: {'bytes': (d / n).stat().st_size, 'sha256': sha((d / n).read_bytes())}
        r = {'schema': V3.RECEIPT_SCHEMA, 'case': exp['case'], 'arm': exp['arm'], 'exit': 0, 'binary_sha256': BINSHA,
             'run_dir': str(d.resolve()), 'argv': list(exp['argv']), 'cwd': exp['cwd'], 'environment': dict(exp['environment']),
             'controlled_environment_observed': {k: v for k, v in exp['environment'].items() if k.startswith(V3.CONTROLLED_PREFIXES)},
             'publication': pub, 'runtime': pin('runtime.json'), 'stdout': pin('stdout.log')}
        if edit:
            edit(r)
        (d / 'RUN.json').write_text(json.dumps(r))
        return r

    def admit(self, d, exp, root=None):
        return V3.admit_producer(d, exp, self.adm, root or self.root)


def expect_code(name, code, fn):
    try:
        fn()
    except V3.AdmissionError as e:
        record(name, e.code == code, 'code=%s' % e.code if e.code == code else 'wanted %s got %s: %s' % (code, e.code, e))
        return
    except Exception as e:  # any non-AdmissionError is an infrastructure fault, not the intended rejection
        record(name, False, 'wrong exception %s: %s' % (type(e).__name__, e))
        return
    record(name, False, 'ADMITTED but wanted %s' % code)


def main(result_path):
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v3-') as scratch:
        w = World(scratch)
        # ---- positives ----------------------------------------------------------------------------------------
        built = {}
        for case, arm in [('noisy', 'OFF'), ('noisy', 'ON'), ('flat', 'OFF'), ('flat', 'ON')]:
            built[(case, arm)] = w.build(case, arm)
        for (case, arm), (d, exp) in built.items():
            try:
                a = w.admit(d, exp)
                want = 9 if (case, arm) == ('noisy', 'ON') else 0
                record('positive admit %s %s' % (case, arm), a['witness_lines'] == want, 'witness_lines=%d' % a['witness_lines'])
            except Exception as e:
                record('positive admit %s %s' % (case, arm), False, repr(e))
        for arm in ('OFF', 'ON'):
            d, exp = built[('noisy', arm)]
            try:
                m = V3.score_admitted(d, exp, w.adm, w.root, FIX)
                old = json.loads((RAW / 'noisy' / 'UP_only' / 'metrics.json').read_text())
                diff = max(abs(m[a]['angstrom'][k] - old[a]['angstrom'][k]) for a in ('runtime', 'STAR') for k in V3.LIMITS)
                record('positive score noisy %s equals retained pair' % arm, diff <= 1e-12 and m['runtime']['gate'] == 'FAIL', 'maxdiff_A=%.3g' % diff)
            except Exception as e:
                record('positive score noisy %s' % arm, False, repr(e))
        v1 = json.loads((PILOT / 'COMMANDS_DRAFT.json').read_text())
        record('v3 commands equal v1 argv/cwd/env/inputs/witness', len(v1) == len(CMD) == 16 and all(
            all(a[k] == b[k] for k in ('case', 'arm', 'argv', 'cwd', 'input_files', 'environment', 'status', 'expected_local_weight_witness_lines')) for a, b in zip(v1, CMD)))
        record('witness derivation: 9 on 3x3 ON, else 0', [V3.witness_expected(a, g) for a, g in [('ON', [3, 3]), ('OFF', [3, 3]), ('ON', [1, 1]), ('OFF', [1, 1])]] == [9, 0, 0, 0])

        # ---- unresolved/placeholder rows ----------------------------------------------------------------------
        expect_code('placeholder binary path refused', 'PLACEHOLDER', lambda: V3.resolve_expected_row(CMD, w.adm, 'noisy', 'OFF', w.root, '<PINNED_LINUX_BINARY>', BINSHA))
        expect_code('bad binary sha refused', 'BINARY', lambda: V3.resolve_expected_row(CMD, w.adm, 'noisy', 'OFF', w.root, BIN, 'AB' * 32))
        raw_row = [r for r in CMD if r['case'] == 'noisy' and r['arm'] == 'OFF'][0]
        unresolved = {'case': 'noisy', 'arm': 'OFF', 'argv': raw_row['argv'], 'cwd': raw_row['cwd'], 'environment': raw_row['environment'],
                      'input_files': raw_row['input_files'], 'patch_grid': [3, 3], 'expected_witness_lines': 0, 'expected_output_names': [], 'binary_sha256': BINSHA}
        d, _ = built[('noisy', 'OFF')]
        expect_code('unresolved draft row not admissible', 'PLACEHOLDER', lambda: w.admit(d, unresolved))
        expect_code('draft row cannot be re-resolved twice', 'PLACEHOLDER', lambda: V3.resolve_expected_row([dict(raw_row, argv=[BIN] + raw_row['argv'][1:])], w.adm, 'noisy', 'OFF', w.root, BIN, BINSHA))

        # ---- receipt/argv/env negatives: one change each, receipt otherwise consistent ----------------------------
        def neg(name, code, case, arm, edit=None, disk=None):
            d, exp = w.build(case, arm)
            if disk:
                disk(d)
            w.write_receipt(d, exp, edit) if (edit or disk == 'rehash') else None
            expect_code(name, code, lambda: w.admit(d, exp))

        def setkey(k, v):
            return lambda r: r.__setitem__(k, v)

        def delkey(k):
            return lambda r: r.pop(k)

        neg('missing arm', 'ARM', 'noisy', 'ON', delkey('arm'))
        neg('ON receipt in OFF slot', 'ARM', 'noisy', 'OFF', setkey('arm', 'ON'))
        neg('OFF receipt in ON slot', 'ARM', 'noisy', 'ON', setkey('arm', 'OFF'))
        # swapped directories: contents of OFF and ON exchanged
        w.build('noisy', 'OFF'); w.build('noisy', 'ON')
        o, n = w.root / 'noisy' / 'OFF', w.root / 'noisy' / 'ON'
        os.rename(o, w.root / 'noisy' / 'tmp'); os.rename(n, o); os.rename(w.root / 'noisy' / 'tmp', n)
        eo = V3.resolve_expected_row(CMD, w.adm, 'noisy', 'OFF', w.root, BIN, BINSHA); en = V3.resolve_expected_row(CMD, w.adm, 'noisy', 'ON', w.root, BIN, BINSHA)
        expect_code('swapped dirs: OFF slot holds ON', 'ARM', lambda: w.admit(o, eo))
        expect_code('swapped dirs: ON slot holds OFF', 'ARM', lambda: w.admit(n, en))
        # a tree copied to a non-canonical location with a self-consistent receipt for it
        d, exp = w.build('noisy', 'OFF')
        alt = Path(scratch) / 'elsewhere' / 'noisy' / 'OFF'
        shutil.copytree(d, alt)
        expect_code('run dir copied outside evidence_root/case/arm', 'RUN_DIR', lambda: V3.admit_producer(alt, exp, w.adm, w.root))
        rr = json.loads((alt / 'RUN.json').read_text()); rr['run_dir'] = str(alt.resolve()); (alt / 'RUN.json').write_text(json.dumps(rr))
        expect_code('copied run dir with a self-consistent receipt', 'RUN_DIR', lambda: V3.admit_producer(alt, exp, w.adm, w.root))
        neg('receipt run_dir names another directory', 'RUN_DIR', 'noisy', 'OFF', setkey('run_dir', str(w.root / 'noisy' / 'ON')))
        neg('missing flag on ON', 'FLAG_COUNT', 'noisy', 'ON', lambda r: r['argv'].remove(V3.FLAG))
        neg('flag on OFF', 'FLAG_COUNT', 'noisy', 'OFF', lambda r: r['argv'].append(V3.FLAG))
        neg('duplicate flag on ON', 'FLAG_COUNT', 'noisy', 'ON', lambda r: r['argv'].append(V3.FLAG))
        neg('extra unknown argv', 'ARGV', 'noisy', 'ON', lambda r: r['argv'].extend(['--experimental_local_b2']))
        neg('changed argv value', 'ARGV', 'noisy', 'ON', lambda r: r['argv'].__setitem__(r['argv'].index('--max_iter') + 1, '6'))
        neg('argv[0] left as placeholder', 'ARGV', 'noisy', 'OFF', lambda r: r['argv'].__setitem__(0, V3.PLACEHOLDER_BINARY))
        neg('wrong binary sha in receipt', 'BINARY', 'noisy', 'OFF', setkey('binary_sha256', 'cd' * 32))
        neg('uppercase binary sha in receipt', 'BINARY', 'noisy', 'OFF', setkey('binary_sha256', BINSHA.upper()))
        neg('cwd mismatch', 'CWD', 'noisy', 'OFF', setkey('cwd', str(w.root / 'noisy' / 'OFF')))
        neg('env value changed', 'ENV', 'noisy', 'ON', lambda r: r['environment'].__setitem__('OMP_NUM_THREADS', '4'))
        neg('env var missing', 'ENV', 'noisy', 'ON', lambda r: r['environment'].pop('MC_EXPERIMENT_CCF_DC_ARM'))
        neg('env var extra', 'ENV', 'noisy', 'ON', lambda r: r['environment'].__setitem__('OMP_PROC_BIND', 'close'))
        neg('observed child env has extra OMP_PROC_BIND', 'ENV_OBSERVED', 'noisy', 'ON', lambda r: r['controlled_environment_observed'].__setitem__('OMP_PROC_BIND', 'close'))
        neg('observed child env value differs', 'ENV_OBSERVED', 'noisy', 'OFF', lambda r: r['controlled_environment_observed'].__setitem__('OPENBLAS_NUM_THREADS', '2'))
        neg('exit 1 with a complete tap', 'EXIT', 'noisy', 'ON', setkey('exit', 1))
        neg('exit True', 'EXIT', 'noisy', 'ON', setkey('exit', True))
        neg('exit "0"', 'EXIT', 'noisy', 'ON', setkey('exit', '0'))
        neg('case swapped in receipt', 'CASE', 'noisy', 'ON', setkey('case', 'affine'))
        neg('receipt schema wrong', 'SCHEMA', 'noisy', 'ON', setkey('schema', 'v2'))
        neg('publication is a list', 'SCHEMA', 'noisy', 'ON', setkey('publication', []))
        neg('publication bytes is a string', 'SCHEMA', 'noisy', 'ON', lambda r: r['publication']['noisy.star'].__setitem__('bytes', '4857'))
        neg('runtime pin is not a dict', 'SCHEMA', 'noisy', 'ON', setkey('runtime', None))
        # strict JSON in the receipt itself
        d, exp = w.build('noisy', 'ON'); (d / 'RUN.json').write_text((d / 'RUN.json').read_text().replace('"exit": 0', '"exit": NaN') if '"exit": 0' in (d / 'RUN.json').read_text() else (d / 'RUN.json').read_text().replace('"exit":0', '"exit":NaN'))
        expect_code('receipt carries NaN', 'NONFINITE', lambda: w.admit(d, exp))

        # ---- staged input directory ---------------------------------------------------------------------------
        d, exp = w.build('noisy', 'OFF'); (d / 'input' / 'MANIFEST.json').write_text('{}')
        expect_code('extra file in staged cwd', 'INPUT', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'OFF'); (d / 'input' / 'noisy.mrcs').unlink()
        expect_code('missing staged movie', 'INPUT', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'OFF'); (d / 'input' / 'noisy.star').write_text('tampered')
        expect_code('staged input byte tamper', 'INPUT', lambda: w.admit(d, exp))

        # ---- witness (receipt re-hashed so only the witness differs) -------------------------------------------
        def witness_case(name, code, case, arm, transform):
            d, exp = w.build(case, arm)
            lp = d / 'output' / (case + '.log'); lp.write_text(transform(lp.read_text(), case)); w.write_receipt(d, exp)
            expect_code(name, code, lambda: w.admit(d, exp))
        W = V3.WITNESS_LINE
        witness_case('witness x_norm 22', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('x_norm = 42', 'x_norm = 22', 1))
        witness_case('witness pnx 41', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('pnx = 42', 'pnx = 41', 1))
        witness_case('witness nfx 21', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('nfx = 22', 'nfx = 21', 1))
        witness_case('witness x_norm 42.0 text', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('x_norm = 42,', 'x_norm = 42.0,', 1))
        witness_case('witness spaced variant', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('x_norm = 42', 'x_norm  = 42', 1))
        witness_case('witness no leading space', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace('\n' + W, '\n' + W[1:], 1))
        witness_case('8 witness lines on 3x3 ON', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace(W + '\n', '', 1))
        witness_case('10 witness lines on 3x3 ON', 'WITNESS', 'noisy', 'ON', lambda t, c: t + W + '\n')
        witness_case('0 witness lines on 3x3 ON', 'WITNESS', 'noisy', 'ON', lambda t, c: t.replace(W + '\n', ''))
        witness_case('1 witness line on global-only ON', 'WITNESS', 'flat', 'ON', lambda t, c: t + W + '\n')
        witness_case('1 witness line on global-only OFF', 'WITNESS', 'flat', 'OFF', lambda t, c: t + W + '\n')
        witness_case('1 witness line on 3x3 OFF', 'WITNESS', 'noisy', 'OFF', lambda t, c: t + W + '\n')
        witness_case('log of another case', 'LOG_CASE', 'noisy', 'ON', lambda t, c: t.replace('Working on noisy.mrcs', 'Working on affine.mrcs', 1))
        d, exp = w.build('noisy', 'ON'); lp = d / 'output' / 'noisy.log'; lp.write_bytes(b'\xff\xfe not utf8'); w.write_receipt(d, exp)
        expect_code('log is not utf-8', 'LOG_CASE', lambda: w.admit(d, exp))

        # ---- publication inventory ---------------------------------------------------------------------------
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'stray.txt').write_text('unlisted')
        expect_code('unlisted extra output file (receipt unchanged)', 'INVENTORY', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'stray.txt').write_text('unlisted'); w.write_receipt(d, exp)
        expect_code('extra output file even when listed in the receipt', 'INVENTORY', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'logfile.pdf.lst').unlink()
        expect_code('listed output file deleted', 'INVENTORY', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'logfile.pdf').unlink(); w.write_receipt(d, exp)
        expect_code('required output absent from disk and receipt', 'INVENTORY', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'noisy.mrc').write_bytes(b'changed')
        expect_code('listed output byte changed', 'PUBLICATION_HASH', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'output' / 'logfile.pdf').unlink(); os.symlink('/etc/hosts', d / 'output' / 'logfile.pdf'); w.write_receipt(d, exp)
        expect_code('symlink in output', 'INVENTORY', lambda: w.admit(d, exp))
        neg('publication path escapes output', 'INVENTORY', 'noisy', 'ON', lambda r: r['publication'].__setitem__('../RUN.json', {'bytes': 1, 'sha256': 'a' * 64}))

        # ---- runtime.json and stdout.log -----------------------------------------------------------------------
        d, exp = w.build('noisy', 'ON'); (d / 'runtime.json').write_text('{}')
        expect_code('runtime.json replaced by {} (receipt stale)', 'RUNTIME', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON')  # a still-valid, finite, correctly shaped model with one coefficient changed
        m = json.loads((d / 'runtime.json').read_text()); m['coeff_x'][0] += 1e-3; (d / 'runtime.json').write_text(json.dumps(m))
        expect_code('runtime.json tampered to another valid model (receipt stale)', 'RUNTIME', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'runtime.json').unlink()
        expect_code('runtime.json missing', 'RUNTIME', lambda: w.admit(d, exp))
        good = json.loads((RAW / 'noisy' / 'UP_only' / 'runtime.json').read_text())
        for name, code, mut in [
                ('runtime NaN with matching receipt hash', 'NONFINITE', lambda m: None),
                ('runtime 17 coefficients with matching receipt hash', 'RUNTIME', lambda m: m.__setitem__('coeff_x', m['coeff_x'][:17])),
                ('runtime local_enabled integer with matching receipt hash', 'RUNTIME', lambda m: m.__setitem__('local_enabled', 1)),
                ('runtime 4 frames with matching receipt hash', 'RUNTIME', lambda m: m.__setitem__('global', m['global'][:4])),
                ('runtime missing key with matching receipt hash', 'RUNTIME', lambda m: m.pop('coeff_y'))]:
            m = copy.deepcopy(good); mut(m)
            text = json.dumps(m)
            if code == 'NONFINITE':
                text = text.replace('-0.60471920692772696', 'NaN', 1) if '-0.60471920692772696' in text else text.replace(str(good['global'][1][0]), 'NaN', 1)
            d, exp = w.build('noisy', 'ON', runtime_bytes=text.encode()); expect_code(name, code, lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'stdout.log').write_text('tampered')
        expect_code('stdout.log tampered (receipt stale)', 'STDOUT', lambda: w.admit(d, exp))
        d, exp = w.build('noisy', 'ON'); (d / 'stdout.log').unlink()
        expect_code('stdout.log missing', 'STDOUT', lambda: w.admit(d, exp))

        # ---- scoring binding ------------------------------------------------------------------------------------
        # an admitted noisy run whose STAR is the affine movie's (receipt consistent): admission passes, scoring refuses.
        d, exp = w.build('noisy', 'ON', star_bytes=(RAW / 'affine' / 'UP_only' / 'output' / 'affine.star').read_bytes())
        try:
            w.admit(d, exp); record('affine STAR in noisy run is receipt-consistent (admits)', True)
        except Exception as e:
            record('affine STAR in noisy run is receipt-consistent (admits)', False, repr(e))
        expect_code('affine STAR in noisy run refused at scoring', 'STAR_CASE', lambda: V3.score_admitted(d, exp, w.adm, w.root, FIX))
        rt, st = RAW / 'noisy' / 'UP_only' / 'runtime.json', RAW / 'noisy' / 'UP_only' / 'output' / 'noisy.star'
        expect_code('truth file of another case name', 'TRUTH', lambda: V3.field_metrics_bound('noisy', rt, st, FIX / 'affine_field.npy', FIX))
        shutil.copy(st, Path(scratch) / 'other.star')
        expect_code('STAR file name of another case', 'STAR_CASE', lambda: V3.field_metrics_bound('noisy', rt, Path(scratch) / 'other.star', FIX / 'noisy_field.npy', FIX))
        expect_code('case absent from manifest', 'CASE', lambda: V3.field_metrics_bound('nonesuch', rt, st, FIX / 'nonesuch_field.npy', FIX))
        fx2 = Path(scratch) / 'fx_manifest_swap'; fx2.mkdir()
        for n in ('MANIFEST.json', 'noisy_field.npy'):
            shutil.copy(FIX / n, fx2 / n)
        man = json.loads((fx2 / 'MANIFEST.json').read_text()); man['cases']['noisy']['recipe']['pixel_size'] = 0.9; (fx2 / 'MANIFEST.json').write_text(json.dumps(man))
        expect_code('manifest hash swap', 'MANIFEST', lambda: V3.field_metrics_bound('noisy', rt, st, fx2 / 'noisy_field.npy', fx2))
        fx3 = Path(scratch) / 'fx_roi'; fx3.mkdir()
        for n in ('MANIFEST.json', 'noisy_field.npy'):
            shutil.copy(FIX / n, fx3 / n)
        man = json.loads((fx3 / 'MANIFEST.json').read_text()); man['cases']['noisy']['roi'] = [0, 96, 0, 128]; (fx3 / 'MANIFEST.json').write_text(json.dumps(man))
        saved = V3.MANIFEST_SHA256
        V3.MANIFEST_SHA256 = V3.sha(fx3 / 'MANIFEST.json')  # test double: isolate the ROI check from the manifest pin
        try:
            expect_code('in-bounds wrong ROI [0,96,0,128]', 'ROI', lambda: V3.field_metrics_bound('noisy', rt, st, fx3 / 'noisy_field.npy', fx3))
            ok_lowlevel = True
            try:
                meta = man['cases']['noisy']; V2.field_metrics(rt, st, fx3 / 'noisy_field.npy', meta, meta['files']['noisy_field.npy'])
            except Exception:
                ok_lowlevel = False
            record('control: v2 lowlevel accepts that wrong ROI (the gap field_metrics_bound closes)', ok_lowlevel)
        finally:
            V3.MANIFEST_SHA256 = saved

        # ---- v2 gaps documented as controls ---------------------------------------------------------------------
        def v2_admits(name, build_fn):
            d, exp = build_fn()
            try:
                V2.complete_publication(d, exp['case'], BINSHA); got = True
            except Exception:
                got = False
            try:
                w.admit(d, exp); v3 = True
            except V3.AdmissionError:
                v3 = False
            record('control: %s (v2 admits=%s, v3 admits=%s)' % (name, got, v3), got and not v3)
        def swapped():
            d, exp = w.build('noisy', 'OFF'); w.write_receipt(d, exp, setkey('arm', 'ON')); return d, exp
        def no_arm():
            d, exp = w.build('noisy', 'OFF'); w.write_receipt(d, exp, delkey('arm')); return d, exp
        def extra():
            d, exp = w.build('noisy', 'ON'); (d / 'output' / 'stray.txt').write_text('x'); return d, exp
        def rtt():
            d, exp = w.build('noisy', 'ON'); (d / 'runtime.json').write_text('{}'); return d, exp
        for nm, fn in [('ON-labelled receipt in OFF slot', swapped), ('receipt without arm', no_arm), ('unlisted extra output', extra), ('runtime.json tamper', rtt)]:
            v2_admits(nm, fn)

        # ---- original numerical negatives (v2 operators, unchanged) via the lowlevel/bound entries -----------------
        meta = json.loads((FIX / 'MANIFEST.json').read_text())['cases']['noisy']; tp = FIX / 'noisy_field.npy'; tsha = meta['files']['noisy_field.npy']
        good = json.loads(rt.read_text())
        def low(mut=None, truth_sha=tsha, case_meta=meta):
            m = copy.deepcopy(good)
            if mut: mut(m)
            p = Path(scratch) / 'rt_low.json'; p.write_text(json.dumps(m))
            return V2.field_metrics(p, st, tp, case_meta, truth_sha)
        for name, kw in [('lowlevel wrong truth sha', dict(truth_sha='0' * 64)),
                         ('lowlevel 17 coefficients', dict(mut=lambda m: m.__setitem__('coeff_x', m['coeff_x'][:17]))),
                         ('lowlevel integer local_enabled', dict(mut=lambda m: m.__setitem__('local_enabled', 1))),
                         ('lowlevel disabled with coefficients', dict(mut=lambda m: m.__setitem__('local_enabled', False))),
                         ('lowlevel 4-frame global', dict(mut=lambda m: m.__setitem__('global', m['global'][:4]))),
                         ('lowlevel out-of-bounds ROI', dict(case_meta=dict(meta, roi=[0, 200, 0, 128])))]:
            try:
                low(**kw); record(name + ' rejected', False, 'accepted')
            except Exception as e:
                record(name + ' rejected', True, type(e).__name__)
        try:
            base = low(); record('lowlevel positive control', base['runtime']['gate'] == 'FAIL')
        except Exception as e:
            record('lowlevel positive control', False, repr(e))

        # ---- four retained metadata score pairs ----------------------------------------------------------------
        for case in ('noisy', 'affine'):
            for arm in ('UP_only', 'UP_B2'):
                rd = RAW / case / arm
                try:
                    m = V3.field_metrics_bound(case, rd / 'runtime.json', rd / 'output' / (case + '.star'), FIX / (case + '_field.npy'), FIX)
                    old = json.loads((rd / 'metrics.json').read_text())
                    diff = max(abs(m[a]['angstrom'][k] - old[a]['angstrom'][k]) for a in ('runtime', 'STAR') for k in V3.LIMITS)
                    record('retained pair %s/%s reproduces' % (case, arm), diff <= 1e-12, 'maxdiff_A=%.3g' % diff)
                except Exception as e:
                    record('retained pair %s/%s reproduces' % (case, arm), False, repr(e))
                # copy the retained fetch into a canonical slot so the rejection is about its content, not its path
                exp = V3.resolve_expected_row(CMD, w.adm, case, 'OFF', w.root, BIN, BINSHA)
                slot = w.root / case / 'OFF'
                if slot.exists():
                    shutil.rmtree(slot)
                shutil.copytree(rd, slot)
                expect_code('retained metadata-only fetch %s/%s is not a complete producer' % (case, arm), 'SCHEMA', lambda: V3.admit_producer(slot, exp, w.adm, w.root))

        # ---- tool pins and the launch gate -----------------------------------------------------------------------
        roots = {'consumer_source': CONSUMER, 'repo': REPO, 'pilot': PILOT}
        try:
            record('all admission tool pins verify', V3.verify_tool_pins(ADM, roots) is True)
        except Exception as e:
            record('all admission tool pins verify', False, repr(e))
        bad = copy.deepcopy(ADM); bad['tools'][0]['sha256'] = '0' * 64
        expect_code('altered tool pin refused', 'TOOL_PIN', lambda: V3.verify_tool_pins(bad, roots))
        names = {t['path'].split('/')[-1] for t in ADM['tools']}
        need = {'compare_products.py', 'score_fields_v2.py', 'score_fields_v3.py', 'generate_known_motion_fixture.py', 'generate_realistic_motion.py',
                'generate_motion_diagnostics.py', 'check_motion_diagnostics.py', 'check_realistic_motion.py', 'motion_field.py', 'test_score_fields_v3.py'}
        record('admission v3 pins comparator, scorers, tests and all transitive generators', need <= names and any(t['sha256'] == '53449d2da682305c8c11e3ed3efb91103530196e481ac075b00f90e3d5ea0f47' for t in ADM['tools']))
        record('admission v3 stays HELD with final fields null', ADM['status'].startswith('HELD_') and all(ADM[k] is None for k in ('candidate_binary', 'source_archive', 'compiler_and_config', 'venue_identity', 'fresh_venue_resource_admission', 'independent_source_clearance')) and ADM['native_started'] is False and ADM['manifest_sha256'] == V3.MANIFEST_SHA256)
        record('launch gate: ON only after OFF compat and source identity PASS', [V3.on_launch_permitted(a, b) for a, b in [('PASS', 'PASS'), ('FAIL', 'PASS'), ('PASS', 'FAIL'), (None, 'PASS'), ('PASS', None)]] == [True, False, False, False, False])

    failed = [r for r in RESULTS if not r['ok']]
    Path(result_path).write_text(json.dumps({'total': len(RESULTS), 'failed': len(failed), 'results': RESULTS}, indent=1, allow_nan=False) + '\n')
    print('TOTAL %d FAILED %d' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
