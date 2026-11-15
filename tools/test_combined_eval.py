#!/usr/bin/env python3
"""Actual combined-evaluator CLI controls; generated inputs, no native execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import check_motion_diagnostics as check

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO/'docs/post_rc0/s1/synth_combined/eval_v2.py'
gen = check.gen


def star_text(shift=0):
    return ('data_general\n_rlnImageSizeX 128\n_rlnImageSizeY 96\n_rlnImageSizeZ 5\n'
            '_rlnMicrographOriginalPixelSize 0.885\n_rlnMicrographStartFrame 1\n'
            '_rlnMicrographBinning 1\n_rlnMotionModelVersion 0\n'
            'data_global_shift\nloop_\n_rlnMicrographFrameNumber #1\n'
            '_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n'+
            ''.join(f'{f+1} {shift if f == 4 else 0} 0\n' for f in range(5)))


class CombinedEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_tmp = tempfile.TemporaryDirectory()
        cls.fixtures = Path(cls.fixtures_tmp.name)/'fixtures'
        gen.generate(cls.fixtures)

    @classmethod
    def tearDownClass(cls):
        cls.fixtures_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root/'run'; self.run.mkdir()
        self.out = self.root/'out.json'
        rows = []
        for name in gen.CASES:
            case = self.run/name; case.mkdir()
            (case/f'{name}.star').write_text(star_text())
            target = np.load(self.fixtures/f'{name}_target.npy')
            gen.write_mrc_stack(case/f'{name}.mrc', target[None]*5, .885)
            rows.append(dict(case=name, exit=7 if name == 'noisy' else 0, dc='none'))
        (self.run/'runs.json').write_text(json.dumps(rows))

    def evaluate(self, wrapper=WRAPPER):
        env = os.environ.copy(); env.pop('PYTHONPATH', None)
        p = subprocess.run([sys.executable, str(wrapper), str(self.fixtures),
                            str(self.run), str(self.out)], cwd=self.root,
                           env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        return {r['case']: r for r in json.loads(self.out.read_text())}

    def test_documented_cli_valid_reports_and_determinism(self):
        rows = self.evaluate()
        first = self.out.read_bytes()
        self.assertEqual(rows['zero']['field_gate'], 'PASS')
        self.assertEqual(rows['noisy']['native_exit'], 7)
        for name, row in rows.items():
            expected = check.check_case(self.fixtures, name,
                                       self.run/name/f'{name}.star',
                                       self.run/name/f'{name}.mrc')
            self.assertEqual(row['sampling_status'], 'VALID')
            self.assertEqual(row['field_px'], expected['field_px'])
            self.assertEqual(row['field_angstrom'], expected['field_angstrom'])
            self.assertEqual(row['checker_status'], expected['accuracy_status'])
            self.assertEqual(row['image'], expected['signal'])
        self.evaluate()
        self.assertEqual(self.out.read_bytes(), first)

    def test_copied_helper_under_source_root(self):
        # The original one-level helper layout remains usable, as does the
        # deeper committed path. Neither invocation depends on cwd/PYTHONPATH.
        source = self.root/'source'; helper = source/'helpers/eval_v2.py'
        helper.parent.mkdir(parents=True)
        (source/'tools').symlink_to(REPO/'tools', target_is_directory=True)
        (source/'test-data').symlink_to(REPO/'test-data', target_is_directory=True)
        shutil.copyfile(WRAPPER, helper)
        self.assertEqual(self.evaluate(helper)['zero']['checker_status'], 'PASS')

    def test_finite_outside_keeps_fields_and_null_image_metric(self):
        for name in ['zero', 'flat']:
            (self.run/name/f'{name}.star').write_text(star_text(200))
        rows = self.evaluate(); first = self.out.read_bytes()
        for name in ['zero', 'flat']:
            row = rows[name]
            self.assertEqual(row['checker_exit'], 1)
            self.assertEqual(row['sampling_status'], 'OUTSIDE_FIXED_ROI')
            self.assertEqual(row['field_gate'], 'FAIL')
            self.assertIsNone(row['image']['estimated_motion_bilinear'])
            self.assertIn('published_sum_divided_by_frames', row['image'])
            self.assertGreater(row['field_px']['max'], 190)
        self.assertEqual(rows['zero']['checker_status'], 'FAIL')
        self.assertEqual(rows['flat']['checker_status'], 'UNIDENTIFIABLE')
        self.assertIn(b'"estimated_motion_bilinear": null', first)
        self.evaluate(); self.assertEqual(self.out.read_bytes(), first)

    def test_input_error_never_consumes_cached_success(self):
        good = self.evaluate()
        cached = self.run/'zero.checker.json'
        old = cached.read_bytes()
        for summed in [np.zeros((1, 4, 4)), np.full((1, 96, 128), np.nan)]:
            with self.subTest(shape=summed.shape):
                gen.write_mrc_stack(self.run/'zero/zero.mrc', summed, .885)
                row = self.evaluate()['zero']
                self.assertEqual(row['checker_exit'], 2)
                self.assertIn('INPUT ERROR:', row['checker_message'])
                self.assertEqual(row['checker_status'], 'ABORT_NO_RESULT')
                self.assertNotIn('image', row)
                self.assertNotIn('sampling_status', row)
                self.assertEqual(row['field_px'], good['zero']['field_px'])
                self.assertEqual(cached.read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
