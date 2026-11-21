#!/usr/bin/env python3
"""Host controls for cpu1_sums.py (mock sums stored as .npy under the .mrc names; no GPU, no native run)."""
import json, os, pathlib, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cpu1_sums as S
S.read_sum = lambda p: np.load(p)


class Sums(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp())
        self.names = [f'dose1-s{i:02d}' for i in range(4)]

    def arm(self, results, name, arr, exit_=0):
        d = self.t / results / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        (d.parent / 'RUN.json').write_text(json.dumps({'exit': exit_}))
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def ref(self, name, arr):
        d = self.t / 'ref' / name / 'cpu-none' / 'output'; d.mkdir(parents=True)
        with open(d / 'movie.mrc', 'wb') as f: np.save(f, arr)

    def build(self, c1_override=None, exit_override=None):
        for i, n in enumerate(self.names):
            a = np.full((3, 4), float(i), dtype=np.float32)
            c = c1_override(n, a) if c1_override else a
            self.arm('c1', n, c, (exit_override or {}).get(n, 0)); self.ref(n, a)

    def cmp(self, expect=4):
        return S.compare(self.t, 'c1', self.t / 'ref', self.t / 'cmp.json', expect)

    def test_all_equal_is_zero(self):
        self.build(); self.assertEqual(self.cmp(), 0)

    def test_one_ulp_difference_is_one_and_named(self):
        self.build(lambda n, a: np.nextafter(a, np.float32(9)) if n.endswith('s02') else a)
        self.assertEqual(self.cmp(), 1); self.assertEqual(json.loads((self.t / 'cmp.json').read_text())['summary']['different'], ['dose1-s02'])

    def test_incomplete_or_invalid_is_two(self):
        self.build(); self.assertEqual(self.cmp(expect=5), 2)                                    # wrong count
        self.setUp(); self.build(exit_override={'dose1-s01': 1}); self.assertEqual(self.cmp(), 2)  # native failure
        self.setUp(); self.build(); (self.t / 'ref/dose1-s03/cpu-none/output/movie.mrc').unlink(); self.assertEqual(self.cmp(), 2)   # missing reference

    def test_shape_difference_is_not_equal(self):
        self.build(lambda n, a: np.zeros((3, 5), np.float32) if n.endswith('s00') else a); self.assertEqual(self.cmp(), 1)

    def eval_rows(self, vals, exit_=0):
        return [{'case': f'c{i}', 'native_exit': exit_, 'field_px': {'rms': v}, 'field_angstrom': {'rms': v * 1.1}, 'checker_exit': 1, 'checker_status': 'FAIL', 'sampling_status': 'VALID', 'field_gate': 'FAIL'}
                for i, v in enumerate(vals)]

    def test_v2check_requires_same_host_identity_and_zero_exits(self):
        w = lambda n, r: (self.t / n).write_text(json.dumps(r))
        base = [0.0, 0.3, 0.6, 0.45, 2.4, 2.6, 2.3, 18.0]
        w('c1.json', self.eval_rows(base)); w('f.json', self.eval_rows(base)); w('pub.json', self.eval_rows([v + 1e-9 for v in base]))
        self.assertEqual(S.v2check(self.t / 'c1.json', self.t / 'f.json', self.t / 'pub.json', self.t / 'o.json'), 0)   # cross-host published difference is information only
        self.assertFalse(all(r['field_equals_published_cross_host'] for r in json.loads((self.t / 'o.json').read_text())['rows'].values()))
        w('c1.json', self.eval_rows(base[:-1] + [18.0000001])); self.assertEqual(S.v2check(self.t / 'c1.json', self.t / 'f.json', self.t / 'pub.json', self.t / 'o.json'), 1)
        w('c1.json', self.eval_rows(base, exit_=1)); w('f.json', self.eval_rows(base, exit_=1)); self.assertEqual(S.v2check(self.t / 'c1.json', self.t / 'f.json', self.t / 'pub.json', self.t / 'o.json'), 1)

    def decide(self, c1_vs_ret_different=False, f_differs_from_c1=False, f_equals_ret=True):
        for i, n in enumerate(self.names):
            a = np.full((3, 4), float(i), np.float32); ret = a
            c1 = a + 1 if c1_vs_ret_different else a
            f = (c1 + 1) if f_differs_from_c1 else c1
            self.arm('c1', n, c1); self.arm('fc', n, f); self.ref(n, ret)
        S.compare(self.t, 'c1', self.t / 'ref', self.t / 'cmp.json', 4)
        return S.decide(self.t, 'c1', self.t / 'ref', 'fc', self.t / 'cmp.json', self.t / 'dec.json')

    def test_decision_pass_inconclusive_fail(self):
        self.assertEqual(self.decide(), 0)
        self.setUp(); self.assertEqual(self.decide(c1_vs_ret_different=True), 3)     # host effect cannot be excluded
        self.setUp(); self.assertEqual(self.decide(f_differs_from_c1=True), 4)       # C1 differs from same-host F
        self.setUp(); self.build(); S.compare(self.t, 'c1', self.t / 'ref', self.t / 'cmp.json', 4)
        self.assertEqual(S.decide(self.t, 'c1', self.t / 'ref', 'no-control-results', self.t / 'cmp.json', self.t / 'd.json'), 5)   # control missing: incomplete


if __name__ == '__main__':
    unittest.main(verbosity=2)
