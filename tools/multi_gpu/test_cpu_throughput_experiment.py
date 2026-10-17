#!/usr/bin/env python3
"""Budget, routing and child-exit negative controls for the diagnostic tool."""
import copy
import json
import os
from pathlib import Path
import signal
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

import cpu_throughput_experiment as experiment


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cpus = sorted(os.sched_getaffinity(0))[:2]
        self.plan = {'cpu_budget': 2, 'headroom_bytes': 1 << 30,
                     'memory_budget_bytes': 8 << 30, 'worker_args': ['--use_own'],
                     'configurations': [{'name': 'one', 'binary': sys.executable,
                                         'worker_rss_kib': 100,
                                         'masks': [','.join(map(str, self.cpus))]}]}

    def tearDown(self):
        self.temp.cleanup()

    def require_two_cpus(self):
        if len(self.cpus) < 2:
            self.skipTest('two allocated CPU IDs are required for this control')

    def require_child_support(self):
        self.require_two_cpus()
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            self.skipTest('Linux pidfd APIs unavailable for child control')
        try:
            fd = os.pidfd_open(os.getpid()); os.close(fd)
        except OSError as exc:
            self.skipTest(f'kernel pidfd unavailable for child control: {exc}')

    def test_disjoint_fixed_budget_and_owned_options(self):
        self.require_two_cpus()
        self.assertEqual(experiment.validate(self.plan), set(self.cpus))
        for mutation in ('overlap', 'budget', 'owned', 'headroom'):
            plan = copy.deepcopy(self.plan)
            if mutation == 'overlap':
                plan['configurations'][0]['masks'] = [str(self.cpus[0]), str(self.cpus[0])]
            elif mutation == 'budget':
                plan['cpu_budget'] = 1
            elif mutation == 'owned':
                plan['worker_args'].extend(['--j', '200'])
            else:
                plan['headroom_bytes'] = 0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                experiment.validate(plan)

    def test_memory_budget_refuses_without_launching(self):
        for current, limit, budget, allowed in [
                ('1024', '8589934592', 8 << 30, True),
                ('8589934592', '8589934592', 8 << 30, False),
                ('1024', '8589934592', 1, False),
                ('1024', 'max', 8 << 30, True)]:
            self.plan['memory_budget_bytes'] = budget
            with self.subTest(current=current, limit=limit, budget=budget), \
                 mock.patch.object(experiment.Path, 'read_text', side_effect=[current, limit]):
                report = experiment.memory_preflight(self.plan, self.plan['configurations'][0])
                self.assertEqual(report['allowed'], allowed)
                self.assertEqual(report['cgroup_current_bytes'], int(current))

    def fixture(self):
        workers = [self.root / 'w0', self.root / 'w1']
        for index, worker in enumerate(workers):
            (worker / 'Movies').mkdir(parents=True)
            for suffix in ('.mrc', '.star', '_shifts.eps'):
                (worker / 'Movies' / (chr(97 + index) + suffix)).write_text('data')
        manifest = {'canonical_movies': ['Movies/a.tiff', 'Movies/b.tiff'],
                    'shards': [{'index': 0, 'movies': ['Movies/a.tiff']},
                               {'index': 1, 'movies': ['Movies/b.tiff']}]}
        return workers, manifest

    def test_correct_staging_and_missing_output_negative(self):
        workers, manifest = self.fixture()
        result = experiment.stage_products(self.root / 'merged', manifest, workers,
                                           ['.mrc', '.star', '_shifts.eps'])
        self.assertEqual(len(result), 6)
        with self.assertRaisesRegex(RuntimeError, 'missing required product'):
            experiment.stage_products(self.root / 'missing', manifest, workers,
                                       ['.mrc', '.star', '_noDW.mrc'])

    def test_misrouted_output_negative(self):
        workers, manifest = self.fixture()
        source = workers[0] / 'Movies/a.mrc'
        source.rename(workers[1] / 'Movies/a.mrc')
        with self.assertRaisesRegex(RuntimeError, 'misrouted'):
            experiment.stage_products(self.root / 'merged', manifest, workers, ['.mrc'])

    def test_unassigned_output_negative(self):
        workers, manifest = self.fixture()
        (workers[0] / 'unexpected.mrc').write_text('wrong')
        with self.assertRaisesRegex(RuntimeError, 'unassigned'):
            experiment.stage_products(self.root / 'merged', manifest, workers, ['.mrc'])

    def test_aggregate_rewrite_negative_even_same_bytes(self):
        workers, manifest = self.fixture()
        merged = self.root / 'merged'
        staged = experiment.stage_products(merged, manifest, workers, ['.mrc', '.star'])
        experiment.verify_unchanged(merged, staged)
        target = merged / 'Movies/a.mrc'
        target.write_bytes(target.read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'aggregate rewrote'):
            experiment.verify_unchanged(merged, staged)

    def test_immutable_input_hash_negative(self):
        target = self.root / 'movie.mrcs'; target.write_bytes(b'input')
        plan = {'input_sha256': {str(target): experiment.sha(target)}}
        experiment.check_inputs(plan)
        target.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'input bytes changed'):
            experiment.check_inputs(plan)

    def test_comparison_view_paths_and_numeric_negative(self):
        for name, token in [('a', 'Ab12Cd'), ('b', 'Xy98Za')]:
            raw = self.root / name / 'merged'; raw.mkdir(parents=True)
            worker = self.root / name / 'w0'
            header = bytearray(1024); struct.pack_into('<4i', header, 0, 1, 1, 1, 2)
            (raw / 'movie.mrc').write_bytes(header + struct.pack('<f', 1.0))
            (raw / 'other.mrc').write_bytes(header + struct.pack('<f', 2.0))
            (raw / 'movie.star').write_text('_rlnMicrographMovieName movie.tiff\n')
            (raw / 'other.star').write_text('_rlnMicrographMovieName other.tiff\n')
            (raw / 'movie_shifts.eps').write_text(f'({worker}/movie_shifts.eps) show\n1.25 2.0 lineto\n')
            (raw / 'header.pdf.lst').write_text(''.join(
                f'{raw}/.aggregate-{token}/corrected_micrographs_{kind}_rlnAccumMotion{period}.eps\n'
                for period in ('Total', 'Early', 'Late') for kind in ('all', 'hist')))
            experiment.canonical_comparison_view(raw, [worker], self.root / name / 'view')
        a = self.root / 'a/view'; b = self.root / 'b/view'
        self.assertTrue(experiment.identity.compare_trees(str(a), str(b))['identical'])
        for mutation in ('none', 'pixel', 'association', 'plot', 'list'):
            copy = self.root / ('copy-' + mutation); shutil.copytree(b, copy)
            # Relocate known text roots before the positive-copy check. MRCs
            # are copied, not linked, so mutations cannot touch originals.
            for path in copy.iterdir():
                if path.suffix != '.mrc':
                    path.write_bytes(path.read_bytes().replace(str(b).encode(), str(copy).encode()))
            if mutation == 'pixel':
                image = copy / 'movie.mrc'; data = bytearray(image.read_bytes())
                struct.pack_into('<f', data, 1024, 1.0000001192092896); image.write_bytes(data)
            elif mutation == 'association':
                shutil.copyfile(copy / 'other.mrc', copy / 'movie.mrc')
            elif mutation == 'plot':
                path = copy / 'movie_shifts.eps'; path.write_text(path.read_text().replace('1.25 2.0', '1.26 2.0'))
            elif mutation == 'list':
                path = copy / 'header.pdf.lst'; path.write_text(path.read_text().replace('MotionTotal.eps', 'MotionOther.eps'))
            with self.subTest(mutation=mutation):
                self.assertEqual(experiment.identity.compare_trees(str(a), str(copy))['identical'], mutation == 'none')
        raw = self.root / 'b/merged'
        (raw / 'movie_shifts.eps').write_text('(/unknown/output/movie_shifts.eps) show\n1.25 2.0 lineto\n')
        experiment.canonical_comparison_view(raw, [self.root / 'b/w0'], self.root / 'unknown-view')
        self.assertFalse(experiment.identity.compare_trees(str(a), str(self.root / 'unknown-view'))['identical'])
        header = raw / 'header.pdf.lst'
        # The runner emits only all-movie plots at <=3 movies; histogram
        # membership remains mandatory above that source-defined threshold.
        with self.assertRaisesRegex(RuntimeError, 'header list membership'):
            experiment.observed_aggregate_scratch(raw, 2)
        header.write_text(''.join(line for line in header.read_text().splitlines(keepends=True) if '_hist_' not in line))
        self.assertTrue(experiment.observed_aggregate_scratch(raw, 2).endswith('.aggregate-Xy98Za'))
        with self.assertRaisesRegex(RuntimeError, 'header list membership'):
            experiment.observed_aggregate_scratch(raw, 4)

    def test_direct_child_self_affinity_and_nonzero_exit(self):
        self.require_child_support()
        for returncode in (0, 7):
            child = experiment.launch([sys.executable, '-c', f'raise SystemExit({returncode})'],
                                      {self.cpus[0]}, self.root / f'{returncode}.log',
                                      self.root / f'{returncode}.json', 1)
            if returncode:
                with self.assertRaisesRegex(RuntimeError, 'direct child failed'):
                    experiment.wait_all([child])
            else:
                experiment.wait_all([child])
            self.assertEqual(child['returncode'], returncode)
            self.assertGreater(child['rss_hwm_kib'], 0)
            self.assertEqual(json.loads(Path(child['witness']).read_text())['actual_before_exec'],
                             [self.cpus[0]])

    def test_partial_launch_failure_reaps_only_owned_child(self):
        self.require_child_support()
        binary = self.root / 'sleep-worker'
        binary.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(30)\n')
        binary.chmod(0o755)
        movie = self.root / 'a.mrcs'; movie.write_text('fixture')
        star = self.root / 'input.star'
        star.write_text('data_movies\nloop_\n_rlnMicrographMovieName #1\na.mrcs\nb.mrcs\n')
        plan = dict(self.plan, star=str(star), worker_args=['--use_own'], required_products=['.mrc'],
                    input_sha256={str(movie): experiment.sha(movie)})
        config = dict(plan['configurations'][0], binary=str(binary), masks=list(map(str, self.cpus)))
        original = experiment.launch
        launched = []
        def fail_second(*args):
            if launched:
                raise OSError('injected second launch failure')
            child = original(*args); launched.append(child); return child
        with mock.patch.object(experiment, 'launch', side_effect=fail_second), \
             mock.patch.object(experiment, 'memory_preflight', return_value={'allowed': True}):
            result = experiment.one_run(plan, config, self.root / 'run')
        self.assertIn('injected second launch failure', result['error'])
        self.assertFalse(result['diagnostic_complete'])
        self.assertNotIn('pidfd', launched[0])
        self.assertIn('ended', launched[0])
        with self.assertRaises(ChildProcessError):
            os.waitpid(launched[0]['pid'], os.WNOHANG)


if __name__ == '__main__':
    if sys.platform != 'linux':
        print('SKIP CpuDatasetThroughputExperiment: Linux-only controls')
        raise SystemExit(77)
    unittest.main()
