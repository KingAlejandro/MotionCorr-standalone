#!/usr/bin/env python3
"""Host controls for cpu1c_sums.py. Ordinary valid data (including FAIL and UNIDENTIFIABLE truth outcomes and finite sums) stays valid; negatives cover the parent's all-ABORT false-PASS control,
null/non-finite/bool/missing metrics, invalid checker contracts, bool/float/string exits, non-object RUN files, Inf/NaN/empty sums, partial/wrong-name sets and self-selected counts. Mock sums are .npy under .mrc names."""
import json, os, pathlib, subprocess, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cpu1c_sums as S
S.read_sum = lambda p: np.load(p)
C1, FB = 'c' * 64, 'f' * 64
SMALL = dict(EXPECT_ALL=6, EXPECT_CONTROL=3, CONTROL_NAMES=['dose1-s00', 'dose1-s01', 'dose1-s02'])
DEFAULTS = dict(EXPECT_ALL=S.EXPECT_ALL, EXPECT_CONTROL=S.EXPECT_CONTROL, CONTROL_NAMES=list(S.CONTROL_NAMES))


def strict(path): return json.loads(pathlib.Path(path).read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))


class Base(unittest.TestCase):
    def setUp(self):
        for k, v in SMALL.items(): setattr(S, k, v)
        self.t = pathlib.Path(tempfile.mkdtemp())
        self.all = [f'{c}-s{i:02d}' for c in ('dose1', 'dose2') for i in range(3)]
        self.control = SMALL['CONTROL_NAMES']
        os.environ['C1_KM_FIXTURES'] = str(self.t / 'fixtures')
        for n in self.all:
            (self.t / 'fixtures' / n).mkdir(parents=True); (self.t / 'fixtures' / n / 'RECEIPT.json').write_text(json.dumps({'files': {'movie.mrcs': 'm' + n}}))
        self.ids = self.t / 'ids.json'; self.write_ids({'all': self.all, 'control': self.control})

    def tearDown(self):
        for k, v in DEFAULTS.items(): setattr(S, k, v)

    def write_ids(self, d): self.ids.write_text(json.dumps(d))

    def arm(self, results, name, arr, exit_=0, sha=C1, movie=None, raw_run=None):
        d = self.t / results / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        if raw_run is None: raw_run = json.dumps({'exit': exit_, 'binary_sha256': sha, 'movie_sha256': movie or 'm' + name})
        if raw_run != '': (d.parent / 'RUN.json').write_text(raw_run)
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def ref(self, name, arr):
        d = self.t / 'ref' / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def value(self, n): return np.full((3, 4), float(self.all.index(n)), np.float32)

    def populate(self, names=None, c1=None, f=None, ref=None):
        for n in self.all: self.ref(n, ref(n) if ref else self.value(n))
        for n in (names or self.all): self.arm('c1', n, c1(n) if c1 else self.value(n))
        for n in self.control if f is None else f: self.arm('fc', n, self.value(n), sha=FB)

    def cmp(self, group='all', sha=C1): return S.compare(self.t, 'c1', self.t / 'ref', self.t / 'cmp.json', self.ids, group, sha)
    def dec(self): return S.decide(self.t, 'c1', 'fc', self.t / 'ref', self.ids, self.t / 'dec.json', C1, FB)
    def verdict(self): return strict(self.t / 'dec.json')['verdict']


class Compare(Base):
    def test_positive_and_strict_json_output(self):
        self.populate(); self.assertEqual(self.cmp(), 0); strict(self.t / 'cmp.json')

    def test_one_ulp_difference_named(self):
        self.populate(c1=lambda n: np.nextafter(self.value(n), np.float32(99)) if n == 'dose2-s01' else self.value(n))
        self.assertEqual(self.cmp(), 1); self.assertEqual(strict(self.t / 'cmp.json')['summary']['different'], ['dose2-s01'])

    def test_sets_and_runs(self):
        self.populate(names=self.all[:-1]); self.assertEqual(self.cmp(), 2)
        self.setUp(); self.populate(); self.arm('c1', 'dose9-s00', self.value('dose1-s00')); self.assertEqual(self.cmp(), 2)
        for kw in ({'exit_': 1}, {'exit_': False}, {'exit_': 0.0}, {'exit_': '0'}, {'sha': 'd' * 64}, {'movie': 'wrong'}, {'raw_run': ''}, {'raw_run': '[]'}, {'raw_run': 'null'}, {'raw_run': '{'}, {'raw_run': '"x"'}):
            with self.subTest(kw):
                self.setUp(); self.populate(names=self.all[1:]); self.arm('c1', self.all[0], self.value(self.all[0]), **kw); self.assertEqual(self.cmp(), 2)

    def test_non_finite_and_empty_sums_cannot_qualify_even_when_identical(self):
        for bad in (np.array([[np.inf, 1], [2, 3]], np.float32), np.array([[np.nan, 1], [2, 3]], np.float32), np.zeros((0, 4), np.float32)):
            with self.subTest(str(bad.tolist())):
                self.setUp(); self.populate(c1=lambda n, b=bad: b if n == 'dose2-s02' else self.value(n), ref=lambda n, b=bad: b if n == 'dose2-s02' else self.value(n))
                self.assertEqual(self.cmp(), 2)
                self.assertIn('dose2-s02', strict(self.t / 'cmp.json')['summary']['errors'])

    def test_self_selected_counts_and_identities_are_refused(self):
        self.populate(); self.write_ids({'all': self.all, 'control': self.control, 'expected_all': 6, 'expected_control': 3})
        for k, v in DEFAULTS.items(): setattr(S, k, v)                                          # the fixed 100/10 contract
        self.assertEqual(self.cmp(), 2)                                                          # a smaller self-consistent file is not accepted
        self.assertIn('invalid', strict(self.t / 'cmp.json'))
        for k, v in SMALL.items(): setattr(S, k, v)
        for name, d in {'duplicate': {'all': self.all + [self.all[0]], 'control': self.control}, 'unsorted': {'all': self.all[::-1], 'control': self.control},
                        'wrong control names': {'all': self.all, 'control': ['dose2-s00', 'dose2-s01', 'dose2-s02']}, 'short': {'all': self.all[:5], 'control': self.control}, 'not object': []}.items():
            with self.subTest(name):
                self.write_ids(d)
                with self.assertRaises(S.Invalid): S.load_ids(self.ids)

    def test_unexpected_exception_is_invalid_not_a_crash(self):
        self.assertEqual(S.main(['x', 'compare', str(self.t), 'c1', str(self.t / 'ref'), str(self.t / 'o.json'), str(self.t / 'missing-ids.json'), 'all', C1]), 2)
        self.assertEqual(S.main(['x', 'decide', str(self.t), 'c1', 'fc', str(self.t / 'ref'), str(self.t / 'missing-ids.json'), str(self.t / 'o.json'), C1, FB]), 5)


class Decide(Base):
    def test_positive_pass(self): self.populate(); self.assertEqual(self.dec(), 0); self.assertEqual(self.verdict(), 'PASS')

    def test_inconclusive_preserved_never_pass(self):
        self.populate(c1=lambda n: self.value(n) + 1, f=[]); [self.arm('fc', n, self.value(n) + 1, sha=FB) for n in self.control]
        self.assertEqual(self.dec(), 3); self.assertTrue(self.verdict().startswith('INCONCLUSIVE')); self.assertIn('not a PASS', self.verdict())

    def test_fail_and_incomplete_cases(self):
        self.populate(f=[]); [self.arm('fc', n, self.value(n) + 1, sha=FB) for n in self.control]; self.assertEqual(self.dec(), 4)
        self.setUp(); self.populate(f=self.control[:1]); self.assertEqual(self.dec(), 5)
        self.setUp(); self.populate(f=self.control[:2]); self.arm('fc', 'dose2-s00', self.value('dose2-s00'), sha=FB); self.assertEqual(self.dec(), 5)
        self.setUp(); self.populate(names=self.all[:-1]); self.assertEqual(self.dec(), 5)
        self.setUp(); self.populate(f=[]); self.assertEqual(self.dec(), 5)

    def test_f_run_problems_are_incomplete(self):
        for kw in ({'exit_': 1}, {'exit_': False}, {'raw_run': '[]'}, {'raw_run': ''}, {'sha': C1}, {'movie': 'wrong'}):
            with self.subTest(kw):
                self.setUp(); self.populate(f=self.control[1:]); self.arm('fc', self.control[0], self.value(self.control[0]), **{'sha': FB, **kw}); self.assertEqual(self.dec(), 5)

    def test_identical_infinite_sums_cannot_pass_and_nonobject_c1_run_is_incomplete(self):
        inf = np.array([[np.inf, 1]], np.float32)
        self.populate(c1=lambda n: inf, ref=lambda n: inf, f=[]); [self.arm('fc', n, inf, sha=FB) for n in self.control]; self.assertEqual(self.dec(), 5)
        self.setUp(); self.populate(names=self.all[1:]); self.arm('c1', self.all[0], self.value(self.all[0]), raw_run='[]'); self.assertEqual(self.dec(), 5)

    def test_stale_comparison_file_not_trusted(self):
        self.populate(); (self.t / 'cmp.json').write_text(json.dumps({'summary': {'equal': 6}}))
        with open(self.t / 'c1' / self.all[0] / 'cpu-none/output/movie.mrc', 'wb') as f: np.save(f, self.value(self.all[0]) + 3)
        self.assertEqual(self.dec(), 4)


def row(case, status, exit_, sampling='VALID', gate=None, **over):
    gate = gate or ('PASS' if status == 'PASS' else 'FAIL')
    r = {'case': case, 'native_exit': 0, 'dc': 'unset', 'field_px': {'rms': 0.1, 'p95': 0.2, 'max': 0.3}, 'field_angstrom': {'rms': 0.09, 'p95': 0.18, 'max': 0.27},
         'field_gate': gate, 'checker_exit': exit_, 'checker_message': 'ok', 'checker_status': status, 'sampling_status': sampling}
    r.update(over); return r


def valid_rows():
    return [row('zero', 'PASS', 0), row('integer', 'FAIL', 1), row('fractional', 'FAIL', 1), row('affine', 'FAIL', 1), row('pedestal', 'FAIL', 1),
            row('noisy', 'FAIL', 1, 'OUTSIDE_FIXED_ROI'), row('flat', 'UNIDENTIFIABLE', 0, gate='FAIL'), row('repeated', 'UNIDENTIFIABLE', 1, 'OUTSIDE_FIXED_ROI', gate='FAIL')]


class V2(unittest.TestCase):
    def setUp(self): self.t = pathlib.Path(tempfile.mkdtemp())

    def run_(self, c1, f=None, pub=None):
        for n, d in (('c1.json', c1), ('f.json', f if f is not None else c1), ('pub.json', pub if pub is not None else valid_rows())):
            (self.t / n).write_text(d if isinstance(d, str) else json.dumps(d))
        code = S.v2check(self.t / 'c1.json', self.t / 'f.json', self.t / 'pub.json', self.t / 'o.json'); strict(self.t / 'o.json'); return code

    def test_valid_fail_and_unidentifiable_truth_outcomes_are_evidence(self):
        self.assertEqual(self.run_(valid_rows()), 0)                                             # not every case passes, by design
        r = valid_rows(); r[5] = row('noisy', 'FAIL', 0, 'VALID'); self.assertEqual(self.run_(r), 0)   # characterization FAIL with a valid sampling exits 0
        self.assertEqual(self.run_(valid_rows(), pub=[{**x, 'field_px': {'rms': 9.9, 'p95': 9.9, 'max': 9.9}} for x in valid_rows()]), 0)   # cross-host published values are information only

    def test_parent_all_abort_null_control_is_invalid(self):
        abort = [{'case': c, 'native_exit': 0, 'dc': 'unset', 'checker_exit': 2, 'checker_message': 'candidate samples outside fixed valid detector region', 'field_px': None, 'field_angstrom': None,
                  'field_gate': 'ABORT', 'checker_status': 'ABORT_NO_RESULT'} for c in S.CASES]
        self.assertEqual(self.run_(abort, abort), 2)

    def test_parent_actual_control_files_discriminate_old_from_new(self):
        d = pathlib.Path(__file__).resolve().parent / 'parent-control'
        new = S.v2check(d / 'c1.json', d / 'F.json', d / 'published.json', self.t / 'parent.json'); strict(self.t / 'parent.json')
        self.assertEqual(new, 2)                                                                  # equal checker ABORT rows with null metrics are not completed K267 metrics
        old_dir = pathlib.Path(__file__).resolve().parents[1] / 'cpu1b'
        if (old_dir / 'cpu1b_sums.py').exists():                                                  # the control must fail the previous helper: it returned PASS (0)
            sys.path.insert(0, str(old_dir)); import cpu1b_sums as OLD
            self.assertEqual(OLD.v2check(d / 'c1.json', d / 'F.json', d / 'published.json', self.t / 'old.json'), 0)

    def test_incomplete_or_nonfinite_metrics_are_invalid(self):
        for name, mut in {'null metrics': lambda r: r[1].update(field_px=None), 'missing p95': lambda r: r[1]['field_px'].pop('p95'), 'bool metric': lambda r: r[1]['field_px'].update(rms=True),
                          'string metric': lambda r: r[1]['field_angstrom'].update(max='0.3'), 'negative metric': lambda r: r[1]['field_px'].update(rms=-1.0),
                          'not dict': lambda r: r[1].update(field_angstrom=[0.1, 0.2, 0.3]), 'missing sampling_status': lambda r: r[2].pop('sampling_status')}.items():
            with self.subTest(name):
                r = valid_rows(); mut(r); self.assertEqual(self.run_(r), 2)
        r = json.dumps(valid_rows()).replace('"rms": 0.1', '"rms": NaN', 1); self.assertEqual(self.run_(r), 2)                 # NaN token
        r = json.dumps(valid_rows()).replace('"rms": 0.1', '"rms": Infinity', 1); self.assertEqual(self.run_(r), 2)

    def test_checker_contract_violations_are_invalid(self):
        for name, mut in {'exit 2': lambda r: r[1].update(checker_exit=2), 'ABORT status': lambda r: r[1].update(checker_status='ABORT_NO_RESULT'), 'gate FAIL with exit 0': lambda r: r[1].update(checker_exit=0),
                          'PASS with exit 1': lambda r: r[0].update(checker_exit=1), 'UNIDENTIFIABLE on a gate case': lambda r: r[1].update(checker_status='UNIDENTIFIABLE'),
                          'flat as FAIL': lambda r: r[6].update(checker_status='FAIL'), 'status disagrees with gate': lambda r: r[0].update(field_gate='FAIL'), 'field_gate ABORT': lambda r: r[1].update(field_gate='ABORT'),
                          'exit bool': lambda r: r[0].update(checker_exit=False), 'PASS outside ROI': lambda r: r[0].update(sampling_status='OUTSIDE_FIXED_ROI', checker_exit=1),
                          'unknown sampling': lambda r: r[0].update(sampling_status='MAYBE')}.items():
            with self.subTest(name):
                r = valid_rows(); mut(r); self.assertEqual(self.run_(r), 2)

    def test_native_exit_and_structure(self):
        for name, mut in {'False': lambda r: r[0].update(native_exit=False), 'zero float': lambda r: r[0].update(native_exit=0.0), 'string': lambda r: r[0].update(native_exit='0'), 'one': lambda r: r[0].update(native_exit=1),
                          'dc both': lambda r: r[0].update(dc='both'), 'row not object': lambda r: r.__setitem__(0, 'zero'), 'wrong case': lambda r: r[1].update(case='oops')}.items():
            with self.subTest(name):
                r = valid_rows(); mut(r); self.assertEqual(self.run_(r), 2)
        self.assertEqual(self.run_(valid_rows()[:7]), 2); self.assertEqual(self.run_(valid_rows()[::-1]), 2); self.assertEqual(self.run_({'not': 'a list'}), 2)

    def test_c1_versus_f_difference_is_a_mismatch_not_invalid(self):
        f = valid_rows(); f[4]['field_px'] = {'rms': 2.0, 'p95': 2.1, 'max': 2.2}
        self.assertEqual(self.run_(valid_rows(), f), 1)
        a, b = valid_rows(), valid_rows(); del b[5]['checker_message']; self.assertEqual(self.run_(a, b), 1)                    # one-sided optional key is a difference, never None == None


if __name__ == '__main__':
    unittest.main(verbosity=2)
