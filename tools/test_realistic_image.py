#!/usr/bin/env python3
"""Image-truth evaluator controls: perfect, oracle-aligned, zero-motion and wrong-sign sums."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import check_realistic_image as img
gen = img.gen


class ImageTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        img.INTERIOR_MARGIN, img.CONTROL_SIZE, img.CONTROL_PAD = 24, 128, 40
        cls.tmp = tempfile.TemporaryDirectory(); t = Path(cls.tmp.name)
        cls.r = gen.recipe(nx=256, ny=192, frames=40)       # dose 1, pedestal 1, scale 1
        gen.expected(cls.r, t/'e.npy')
        cls.e = np.load(t/'e.npy')
        with (t/'movie.mrcs').open('wb') as f:
            f.write(bytes(1024)); cls.e.astype('<f4').tofile(f)       # noise-free movie
        cls.movie = t/'movie.mrcs'; cls.truth = img.truth_scene(cls.r)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_truth_is_frame0_expectation(self):
        np.testing.assert_allclose(self.e[0]-1, self.truth, atol=1e-5)

    def test_perfect_and_controls(self):
        c = img.evaluate_controls(self.r, self.movie, self.truth)
        p = c['truth_vs_truth']; self.assertAlmostEqual(p['transfer_inband'], 1); self.assertAlmostEqual(p['relrmse_inband'], 0)
        o = c['oracle']
        for b in o['bands']: self.assertGreater(b['transfer'], .9); self.assertGreater(b['frc'], .95)
        for k in ('zero', 'wrong_sign'):
            top = c[k]['bands'][-1]
            self.assertLess(top['transfer'], .5, k); self.assertLess(top['frc'], .6, k)
            self.assertGreater(c[k]['relrmse_inband'], 2*o['relrmse_inband'], k)
            self.assertGreater(c[k]['pixel_relrmse'], 3*c['oracle']['pixel_relrmse'], k)

    def test_evaluate_sum_on_unit_arithmetic(self):
        s = (self.r['pedestal']+self.r['scale']*self.r['dose']*self.truth.astype(float))*self.r['frames']
        m = img.evaluate_sum(self.r, s, self.truth)
        self.assertAlmostEqual(m['interior']['transfer_inband'], 1, places=6)
        self.assertLess(m['border']['border_rel_rms'], 1e-5)

    def test_paired_effect_zero_for_identical_sums(self):
        s = self.e.sum(axis=0)
        rows = img.paired_effect(self.r, s, s, self.truth)
        self.assertEqual(max(x['rms_change'] for x in rows), 0)
        # A border-only defect must show in the border bins and not in the interior bins.
        b = s.copy(); b[:4, :] += 5.
        rows = img.paired_effect(self.r, s, b, self.truth)
        self.assertGreater(rows[0]['rms_change'], 0.1); self.assertLess(rows[-1]['rms_change'], 0.05)


if __name__ == '__main__':
    unittest.main()
