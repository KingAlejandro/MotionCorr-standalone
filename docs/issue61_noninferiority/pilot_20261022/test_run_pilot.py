"""Safety checks on the only transformation of the frozen numerical argv."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
from unittest.mock import patch

DRIVER = Path(os.environ.get('PILOT_DRIVER_UNDER_TEST', Path(__file__).with_name('run_pilot.py')))
spec = importlib.util.spec_from_file_location('pilot', DRIVER)
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
        self.assertTrue(all(env[k] == '1' for k in p.THREADS))
        self.assertEqual(env['APPTAINER_TMPDIR'], '/new/tmp')


class Refusal(unittest.TestCase):
    def ready(self, root):
        jobs = p.selected_jobs(Staging().jobs(), root)
        for i, job in enumerate(jobs):
            job['log'] = f'logs/rec_{i}.log'
        plan = {'reconstruct': jobs, 'postprocess': []}
        p.save(root/'execution_plan.json', plan)
        p.save(root/'PREFLIGHT_STARTED.json', {})
        options = p.container_options(root) if hasattr(p, 'container_options') else []
        p.save(root/'preflight.json', {'status': 'PASS', 'inputs': [], 'stacks': [], 'subsets': [],
               'execution_plan_sha256': p.digest(root/'execution_plan.json'),
               'container': {'runtime': '/verified/singularity', 'options': options}})
        return jobs

    def put(self, root, name):
        f = root/name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b'preserve earlier evidence\n')
        return f

    def test_execute_rejects_products_and_prior_markers_before_popen(self):
        # Both original reviewer cases must reach the intercepted Popen on old
        # code; rejection tests never permit a real numerical subprocess.
        conflicts = [f'rec/{a}/held_half{h}_class001_unfil.mrc'
                     for a in ('baseline', 'thinned') for h in (1, 2)]
        conflicts += ['preflight_FAIL.json', 'execute_FAIL.json', 'STARTED.json', 'DONE.json',
                      'job_0_started.json', 'job_0_pid.json', 'job_0_exit.json', 'map_0.json',
                      'products.json', 'analyser_attempt.json', 'launch_resources.json',
                      'pp/cpu/held22.star', 'pp/thinned/held22_masked.mrc',
                      'logs/prior.log', 'results/prior.json']
        for name in conflicts:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.ready(root)
                f = self.put(root, name)
                with patch.object(p.os, 'sched_getaffinity', return_value={14, 15}, create=True), \
                     patch.object(p, 'probe', return_value={}), \
                     patch.object(p.subprocess, 'Popen', side_effect=AssertionError('Popen reached')) as launch:
                    with self.assertRaises(FileExistsError):
                        p.execute(root)
                    launch.assert_not_called()
                self.assertEqual(f.read_bytes(), b'preserve earlier evidence\n')

    def test_preflight_rejects_prior_products_and_partial_preflight_before_reads(self):
        for name in ('rec/baseline/held_half1_class001_unfil.mrc', 'pp/cpu/held22.star',
                     'preflight_FAIL.json', 'execute_FAIL.json', 'PREFLIGHT_STARTED.json',
                     'execution_plan.json', 'preflight.json', 'STARTED.json', 'DONE.json',
                     'job_0_pid.json', 'historical_jobs_postprocess.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                f = self.put(root, name)
                with patch.object(p.os, 'sched_getaffinity', return_value={14, 15}, create=True), \
                     patch.object(p, 'digest', side_effect=AssertionError('input reads reached')) as reads, \
                     patch.object(p.subprocess, 'Popen', side_effect=AssertionError('Popen reached')) as launch:
                    with self.assertRaises(FileExistsError):
                        p.preflight(root)
                    reads.assert_not_called()
                    launch.assert_not_called()
                self.assertEqual(f.read_bytes(), b'preserve earlier evidence\n')

    def test_dangling_symlink_product_and_output_directory_are_refused(self):
        for stage in ('preflight', 'execute'):
            for name in ('rec', 'pp', 'logs', 'results', 'sources', 'home', 'tmp',
                         'container_work', 'rec/baseline/held_half1_class001_unfil.mrc'):
                with self.subTest(stage=stage, name=name), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    f = root/name
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.symlink_to(root/'absent')
                    with self.assertRaises(FileExistsError):
                        p.refuse_used(root, stage)
                    self.assertTrue(f.is_symlink())

    def test_empty_directory_at_declared_output_is_refused(self):
        outputs = [f'rec/{a}/held_half{h}_class001_unfil.mrc'
                   for a in ('baseline', 'thinned') for h in (1, 2)]
        for stage in ('preflight', 'execute'):
            for name in outputs + ['pp/cpu/held22', 'pp/thinned/held22']:
                with self.subTest(stage=stage, name=name), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    (root/name).mkdir(parents=True)
                    with self.assertRaises(FileExistsError):
                        p.refuse_used(root, stage)

    def test_fresh_preflight_to_execute_allows_first_intercepted_launch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for directory in ('rec/baseline', 'pp/cpu', 'logs', 'results', 'home', 'tmp', 'sources'):
                (root/directory).mkdir(parents=True)
            p.refuse_used(root, 'preflight')
            # Receipt fixture models successful frozen-input preflight; this
            # control exercises the real execute entry point up to Popen only.
            jobs = self.ready(root)
            p.refuse_used(root, 'execute')
            with self.assertRaises(FileExistsError):
                p.refuse_used(root, 'preflight')
            with patch.object(p.os, 'sched_getaffinity', return_value={14, 15}, create=True), \
                 patch.object(p, 'probe', return_value={}), \
                 patch.object(p.subprocess, 'Popen', side_effect=RuntimeError('intercepted fresh launch')) as launch:
                with self.assertRaisesRegex(RuntimeError, 'intercepted fresh launch'):
                    p.execute(root)
                self.assertEqual(launch.call_count, 1)
                self.assertEqual(launch.call_args.args[0],
                                 p.numerical_argv(root, '/verified/singularity', jobs[0]['argv']))

    def test_cli_refusal_preserves_failed_receipt_and_never_launches(self):
        # Actual argparse/main in a separate interpreter. Only the fixed remote
        # root prefix and Linux affinity/lock are adapted to disposable host paths.
        script = '''import importlib.util, pathlib, sys
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('pilot', sys.argv[1])
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
root = pathlib.Path(sys.argv[2]).resolve(); p.ROOT_PREFIX = str(root)
real_open = open
def fixture_open(path, *args, **kwargs):
    if path == '/tmp/motioncorr-i61-cpu-14-15.lock': path = root/'fixture.lock'
    return real_open(path, *args, **kwargs)
with patch.object(p.os, 'sched_getaffinity', return_value={14,15}, create=True), patch('builtins.open', fixture_open), patch.object(p.subprocess, 'Popen', side_effect=AssertionError('Popen reached')) as launch:
    try: p.main([sys.argv[3], str(root)])
    except FileExistsError as exc:
        launch.assert_not_called()
        print('REFUSED BEFORE POPEN:', exc)
    else: raise AssertionError('accepted used scratch')
'''
        for stage in ('preflight', 'execute'):
            for name in ('preflight_FAIL.json', 'rec/baseline/held_half1_class001_unfil.mrc'):
                with self.subTest(stage=stage, name=name), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    self.ready(root) if stage == 'execute' else None
                    f = self.put(root, name)
                    result = subprocess.run([sys.executable, '-B', '-c', script, str(DRIVER.resolve()),
                                             str(root), stage], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    self.assertIn('REFUSED BEFORE POPEN', result.stdout)
                    self.assertEqual(f.read_bytes(), b'preserve earlier evidence\n')


class Container(unittest.TestCase):
    def test_direct_container_argv_preserves_all_six_internal_argument_arrays(self):
        root = Path('/new')
        jobs = p.selected_jobs(Staging().jobs(), root)
        retained = json.loads(Path(__file__).with_name('receipts').joinpath('execution_plan.json').read_text())
        for job in retained['postprocess']:
            old_root = str(Path(job['argv'][4]).parents[2])
            jobs.append(dict(job, argv=[v.replace(old_root, str(root)) for v in job['argv']]))
        for job in jobs:
            original = copy.deepcopy(job['argv'])
            argv = p.numerical_argv(root, '/verified/runtime', job['argv'])
            start = argv.index(str(p.IMAGE))
            self.assertEqual(argv[start+1], '/opt/relion/bin/'+Path(original[0]).name)
            self.assertEqual(argv[start+2:], original[1:])
            self.assertEqual(job['argv'], original)
            self.assertNotIn(str(p.RUNNER), argv)
            self.assertNotIn('--nv', argv)
        opts = p.container_options(root)
        binds = [opts[i+1] for i, v in enumerate(opts) if v == '--bind']
        self.assertEqual(binds, [f'{p.HISTORY}:{p.HISTORY}:ro', f'{p.PLAN.parent}:{p.PLAN.parent}:ro',
                                 '/new:/new:rw', '/new/sources:/new/sources:ro'])
        self.assertEqual(len({b.split(':')[1] for b in binds}), len(binds))
        self.assertIn('--contain', opts)
        self.assertEqual(opts[opts.index('--no-mount')+1], 'hostfs,bind-paths')
        self.assertEqual(opts[opts.index('--home')+1], '/new/home:/new/home')
        self.assertEqual(opts[opts.index('--workdir')+1], '/new/container_work')
        self.assertEqual(opts[opts.index('--pwd')+1], str(p.PROJECT))

    def test_runtime_environment_cannot_inject_bind_overlay_home_or_gpu(self):
        injected = {k: 'untrusted' for k in ('SINGULARITY_BIND', 'SINGULARITY_BINDPATH',
                    'APPTAINER_BIND', 'APPTAINER_BINDPATH', 'SINGULARITYENV_HOME',
                    'APPTAINERENV_HOME', 'SINGULARITY_NV', 'APPTAINER_NV',
                    'SINGULARITY_OVERLAY', 'RELION_CONTAINER_RUN_ARGS', 'LD_PRELOAD', 'PYTHONPATH')}
        with patch.dict(p.os.environ, injected):
            env = p.environment(Path('/new'))
        self.assertFalse(set(injected) & set(env))
        self.assertEqual(env['SINGULARITY_TMPDIR'], '/new/tmp')
        self.assertEqual(env['SINGULARITY_CACHEDIR'], '/new/tmp')

    def runtime_checks(self, version=None, helptext=None, hashes=None, stderr=''):
        return [subprocess.CompletedProcess([], 0, version or p.RUNTIME_VERSION+'\n', ''),
                subprocess.CompletedProcess([], 0, helptext if helptext is not None else
                    '--cleanenv --contain --no-mount --home --workdir --pwd --bind --env', ''),
                subprocess.CompletedProcess([], 0, hashes if hashes is not None else
                    ''.join(f'{h}  {name}\n' for name, h in p.INTERNAL_BINARIES.items()), stderr)]

    def test_supported_runtime_and_exact_internal_binary_hashes_are_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(p, 'executable', return_value=Path('/verified/runtime')), \
                 patch.object(p, 'digest', side_effect=lambda path: p.CONFIG_SHA256 if path == p.RUNTIME_CONFIG else p.RUNTIME_SHA256), \
                 patch.object(p.subprocess, 'run', side_effect=self.runtime_checks()) as run:
                receipt = p.verify_container(root)
                self.assertEqual(receipt['options'], p.container_options(root))
                self.assertEqual(run.call_count, 3)
                self.assertEqual(run.call_args.args[0][-3:], ['/usr/bin/sha256sum', *p.INTERNAL_BINARIES])
                self.assertTrue(all((root/n).is_dir() for n in ('home', 'tmp', 'container_work')))

    def test_unsupported_runtime_options_binary_or_warning_fail_closed(self):
        for change, calls in (({'version': 'apptainer version 1.4'}, 2), ({'helptext': '--bind'}, 2),
                              ({'hashes': 'wrong  /opt/relion/bin/relion_reconstruct\n'}, 3),
                              ({'stderr': 'WARNING: destination is already in the mount point list'}, 3)):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                with patch.object(p, 'executable', return_value=Path('/verified/runtime')), \
                     patch.object(p, 'digest', side_effect=lambda path: p.CONFIG_SHA256 if path == p.RUNTIME_CONFIG else p.RUNTIME_SHA256), \
                     patch.object(p.subprocess, 'run', side_effect=self.runtime_checks(**change)) as run, \
                     patch.object(p.subprocess, 'Popen') as launch:
                    with self.assertRaises(RuntimeError):
                        p.verify_container(Path(d))
                    self.assertEqual(run.call_count, calls)
                    launch.assert_not_called()

    def test_runtime_or_configuration_identity_change_refused_before_container(self):
        for changed in ('runtime', 'config'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as d:
                def digest(path):
                    if path == p.RUNTIME_CONFIG:
                        return 'changed' if changed == 'config' else p.CONFIG_SHA256
                    return 'changed' if changed == 'runtime' else p.RUNTIME_SHA256
                with patch.object(p, 'executable', return_value=Path('/verified/runtime')), \
                     patch.object(p, 'digest', side_effect=digest), patch.object(p.subprocess, 'run') as run:
                    with self.assertRaisesRegex(RuntimeError, 'configuration identity'):
                        p.verify_container(Path(d))
                    run.assert_not_called()

    def test_unsupported_executable_and_overlapping_scratch_are_refused(self):
        for root in (p.HISTORY, p.PROJECT/'scratch', p.PLAN.parent, p.PLAN.parent/'scratch', Path('/home/alex')):
            with self.assertRaises(ValueError):
                p.container_options(root)
        with self.assertRaises(ValueError):
            p.container_options(Path('/new,ambiguous'))
        with self.assertRaises(ValueError):
            p.numerical_argv(Path('/new'), '/runtime', ['/other/relion_reconstruct', '--ctf'])


if __name__ == '__main__':
    unittest.main()
