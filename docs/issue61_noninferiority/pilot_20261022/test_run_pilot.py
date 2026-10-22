"""Safety checks on the only transformation of the frozen numerical argv."""
import copy
import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).with_name('run_pilot.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Staging(unittest.TestCase):
    def jobs(self):
        jobs = []
        for arm in ('baseline', 'thinned'):
            for half in (1, 2):
                output = f'rec/{arm}/held_half{half}_class001_unfil.mrc'
                jobs.append({'arm': arm, 'half': half, 'subset': 'held', 'omitted_movie': None,
                             'cwd': str(p.PROJECT), 'status': 'UNRUN', 'output': output,
                             'argv': [str(p.BIN/'relion_reconstruct'), '--i', str(p.PLAN/'stars'/arm/'held.star'),
                                      '--o', str(p.PLAN/output), '--sym', 'D2', '--subset', str(half), '--pad', '2', '--ctf']})
        return jobs

    def test_only_output_changes_and_jackknife_is_excluded(self):
        jobs = self.jobs()
        original = copy.deepcopy(jobs)
        jobs.append(dict(jobs[0], subset='jk_0000'))
        staged = p.selected_jobs(jobs, Path('/new'))
        self.assertEqual(jobs[:4], original)
        self.assertEqual(len(staged), 4)
        for before, after in zip(original, staged):
            self.assertEqual(after['argv'][:4], before['argv'][:4])
            self.assertEqual(after['argv'][5:], before['argv'][5:])
            self.assertEqual(after['argv'][4], str(Path('/new')/before['output']))
            self.assertEqual(after['original_argv'], before['argv'])

    def test_refuses_settings_cwd_duplicate_and_missing_half(self):
        for mutate in (lambda j: j[0]['argv'].__setitem__(6, 'C1'),
                       lambda j: j[0].__setitem__('cwd', '/other'),
                       lambda j: j.__setitem__(3, j[0]),
                       lambda j: j.pop()):
            jobs = self.jobs()
            mutate(jobs)
            with self.assertRaises(AssertionError):
                p.selected_jobs(jobs, Path('/new'))

    def test_runtime_resolution_accepts_non_system_prefix_and_refuses_missing(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d)/'apptainer'
            runtime.write_text('#!/bin/sh\nexit 0\n')
            runtime.chmod(0o755)
            with patch.dict(p.os.environ, {'PATH': d}):
                self.assertEqual(p.executable('apptainer'), runtime.resolve())
                with self.assertRaises(FileNotFoundError):
                    p.executable('absent-runtime')

    def test_environment_is_cpu_only_and_private(self):
        env = p.environment(Path('/new'))
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '')
        self.assertNotIn('--nv', env['RELION_CONTAINER_RUN_ARGS'])
        self.assertTrue(all(env[k] == '1' for k in p.THREADS))
        self.assertIn(str(p.PROJECT)+':'+str(p.PROJECT)+':ro', env['RELION_CONTAINER_RUN_ARGS'])
        self.assertEqual(env['APPTAINER_TMPDIR'], '/new/tmp')


if __name__ == '__main__':
    unittest.main()
