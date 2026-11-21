#!/usr/bin/env python3
"""Host controls for cpu1b_sums.py: ordinary valid controls plus negative controls for partial/wrong-name/duplicate sets, nonzero or foreign-binary native runs,
unbound fixtures, malformed identities and missing v2 keys. Mock sums are .npy files under .mrc names; no GPU, no native run."""
import copy, json, os, pathlib, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cpu1b_sums as S
S.read_sum = lambda p: np.load(p)
C1, FB = 'c' * 64, 'f' * 64


class Base(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp())
        self.all = [f'{c}-s{i:02d}' for c in ('dose1', 'dose2') for i in range(3)]       # 6 identities; the control is the three dose1 movies
        self.control = [n for n in self.all if n.startswith('dose1')]
        os.environ['C1_KM_FIXTURES'] = str(self.t / 'fixtures')
        for n in self.all:
            (self.t / 'fixtures' / n).mkdir(parents=True)
            (self.t / 'fixtures' / n / 'RECEIPT.json').write_text(json.dumps({'files': {'movie.mrcs': 'm' + n}}))
        self.ids = self.t / 'ids.json'; self.write_ids({'all': self.all, 'control': self.control, 'expected_all': 6, 'expected_control': 3})

    def write_ids(self, d): self.ids.write_text(json.dumps(d))

    def arm(self, results, name, arr, exit_=0, sha=C1, movie=None, write_run=True):
        d = self.t / results / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        if write_run: (d.parent / 'RUN.json').write_text(json.dumps({'exit': exit_, 'binary_sha256': sha, 'movie_sha256': movie or 'm' + name}))
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def ref(self, name, arr):
        d = self.t / 'ref' / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def value(self, n): return np.full((3, 4), float(self.all.index(n)), np.float32)

    def populate(self, names=None, c1=None, f=None):
        for n in self.all: self.ref(n, self.value(n))
        for n in (names or self.all): self.arm('c1', n, c1(n) if c1 else self.value(n))
        for n in self.control if f is None else f: self.arm('fc', n, self.value(n), sha=FB)

    def cmp(self, group='all', sha=C1, results='c1'):
        return S.compare(self.t, results, self.t / 'ref', self.t / 'cmp.json', self.ids, group, sha)

    def dec(self, c1_sha=C1, f_sha=FB): return S.decide(self.t, 'c1', 'fc', self.t / 'ref', self.ids, self.t / 'dec.json', c1_sha, f_sha)

    def verdict(self): return json.loads((self.t / 'dec.json').read_text())['verdict']


class Compare(Base):
    def test_positive_all_equal(self): self.populate(); self.assertEqual(self.cmp(), 0)

    def test_one_ulp_difference_named(self):
        self.populate(c1=lambda n: np.nextafter(self.value(n), np.float32(99)) if n == 'dose2-s01' else self.value(n))
        self.assertEqual(self.cmp(), 1); self.assertEqual(json.loads((self.t / 'cmp.json').read_text())['summary']['different'], ['dose2-s01'])

    def test_partial_wrong_name_and_extra_sets_are_invalid(self):
        self.populate(names=self.all[:-1]); self.assertEqual(self.cmp(), 2)                                       # one movie missing
        self.setUp(); self.populate(); self.arm('c1', 'dose9-s00', self.value('dose1-s00')); self.assertEqual(self.cmp(), 2)   # extra identity
        self.setUp(); self.populate(names=self.all[:-1]); self.arm('c1', 'dose2-s99', self.value('dose2-s02')); self.assertEqual(self.cmp(), 2)   # wrong name, right count

    def test_native_run_problems_are_invalid(self):
        for kw in ({'exit_': 1}, {'sha': 'd' * 64}, {'movie': 'wrong'}, {'write_run': False}):
            with self.subTest(kw):
                self.setUp(); self.populate(names=self.all[1:]); self.arm('c1', self.all[0], self.value(self.all[0]), **kw); self.assertEqual(self.cmp(), 2)

    def test_malformed_identity_files_are_refused(self):
        self.populate()
        for name, d in {'duplicate': {'all': self.all + [self.all[0]], 'control': self.control, 'expected_all': 7, 'expected_control': 3}, 'unsorted': {'all': self.all[::-1], 'control': self.control, 'expected_all': 6, 'expected_control': 3},
                        'control not subset': {'all': self.all, 'control': ['x-s00', 'x-s01', 'x-s02'], 'expected_all': 6, 'expected_control': 3}, 'wrong count': {'all': self.all[:5], 'control': self.control, 'expected_all': 6, 'expected_control': 3},
                        'empty control': {'all': self.all, 'control': [], 'expected_all': 6, 'expected_control': 0}}.items():
            with self.subTest(name):
                self.write_ids(d)
                with self.assertRaises(ValueError): S.load_ids(self.ids)


class Decide(Base):
    def test_positive_pass(self): self.populate(); self.assertEqual(self.dec(), 0); self.assertEqual(self.verdict(), 'PASS')

    def test_inconclusive_when_only_retained_differs(self):
        self.populate(c1=lambda n: self.value(n) + 1, f=[]); [self.arm('fc', n, self.value(n) + 1, sha=FB) for n in self.control]
        self.assertEqual(self.dec(), 3)

    def test_fail_when_c1_differs_from_same_host_f(self):
        self.populate(f=[]); [self.arm('fc', n, self.value(n) + 1, sha=FB) for n in self.control]; self.assertEqual(self.dec(), 4)

    def test_partial_one_row_f_control_is_incomplete(self):
        self.populate(f=self.control[:1]); self.assertEqual(self.dec(), 5); self.assertTrue(self.verdict().startswith('INCOMPLETE'))

    def test_wrong_name_f_control_is_incomplete(self):
        self.populate(f=self.control[:2]); self.arm('fc', 'dose2-s00', self.value('dose2-s00'), sha=FB); self.assertEqual(self.dec(), 5)

    def test_f_run_nonzero_exit_with_existing_mrc_is_incomplete(self):
        self.populate(f=self.control[1:]); self.arm('fc', self.control[0], self.value(self.control[0]), exit_=1, sha=FB); self.assertEqual(self.dec(), 5)

    def test_f_run_missing_record_or_wrong_binary_or_unbound_is_incomplete(self):
        for kw in ({'write_run': False}, {'sha': C1}, {'movie': 'wrong'}):
            with self.subTest(kw):
                self.setUp(); self.populate(f=self.control[1:]); self.arm('fc', self.control[0], self.value(self.control[0]), **{'sha': FB, **kw}); self.assertEqual(self.dec(), 5)

    def test_missing_c1_movie_or_no_control_directory_is_incomplete(self):
        self.populate(names=self.all[:-1]); self.assertEqual(self.dec(), 5)
        self.setUp(); self.populate(f=[]); self.assertEqual(self.dec(), 5)

    def test_does_not_trust_a_stale_comparison_file(self):
        self.populate(); (self.t / 'cmp.json').write_text(json.dumps({'summary': {'n': 6, 'expected': 6, 'equal': 6, 'different': [], 'errors': {}}}))
        d = self.t / 'c1' / self.all[0] / 'cpu-none' / 'output' / 'movie.mrc'
        with open(d, 'wb') as f: np.save(f, self.value(self.all[0]) + 3)
        self.assertEqual(self.dec(), 4 if self.all[0] in self.control else 3)


class V2(Base):
    def rows(self, **over):
        r = [{'case': c, 'native_exit': 0, 'dc': 'unset', 'field_px': {'rms': 0.1 * i}, 'field_angstrom': {'rms': 0.11 * i}, 'field_gate': 'FAIL', 'checker_exit': 1, 'checker_status': 'FAIL', 'sampling_status': 'VALID'}
             for i, c in enumerate(S.CASES)]
        for k, v in over.items(): r[int(k[1:])].update(v)
        return r

    def run_(self, c1, f, pub=None):
        for n, d in (('c1.json', c1), ('f.json', f), ('pub.json', pub if pub is not None else self.rows())): (self.t / n).write_text(json.dumps(d))
        return S.v2check(self.t / 'c1.json', self.t / 'f.json', self.t / 'pub.json', self.t / 'o.json')

    def test_positive_and_published_difference_is_information(self):
        self.assertEqual(self.run_(self.rows(), self.rows(), self.rows(r3={'field_px': {'rms': 9.9}})), 0)
        self.assertFalse(json.loads((self.t / 'o.json').read_text())['rows']['affine']['field_equals_published_cross_host'])

    def test_missing_keys_in_both_rows_do_not_compare_equal(self):
        a, b = self.rows(), self.rows()
        for r in (a, b): del r[2]['field_px']
        self.assertEqual(self.run_(a, b), 1)
        a, b = self.rows(), self.rows()
        for r in (a, b): del r[0]['checker_status']
        self.assertEqual(self.run_(a, b), 1)

    def test_wrong_case_names_count_or_order(self):
        self.assertEqual(self.run_(self.rows()[:7], self.rows()[:7]), 1)
        r = self.rows(); r[1]['case'] = 'oops'; self.assertEqual(self.run_(r, r), 1)
        r = self.rows()[::-1]; self.assertEqual(self.run_(r, r), 1)

    def test_difference_nonzero_exit_or_wrong_dc(self):
        self.assertEqual(self.run_(self.rows(r4={'field_px': {'rms': 2.0}}), self.rows()), 1)
        self.assertEqual(self.run_(self.rows(r1={'native_exit': 1}), self.rows(r1={'native_exit': 1})), 1)
        self.assertEqual(self.run_(self.rows(r1={'dc': 'both'}), self.rows(r1={'dc': 'both'})), 1)
        a = self.rows(); b = self.rows(); del b[5]['sampling_status']; self.assertEqual(self.run_(a, b), 1)     # one-sided optional key is a difference, not None == None


if __name__ == '__main__':
    unittest.main(verbosity=2)
