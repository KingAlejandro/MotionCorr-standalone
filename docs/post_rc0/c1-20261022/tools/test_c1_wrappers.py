#!/usr/bin/env python3
"""Harmless host checks of the C1 lane wrappers (no GPU, no native execution; every external program is a mock).

Derived from the parent's reproducer (/tmp/motioncorr-orchestrator-20261022/check_c1_wrapper_failures.py), which found that the first C1 wrappers
returned the test status although the post-run health check failed, and that c1_sticky.sh nested the driver's own GPU lease.
Asserts: a failed post-check yields exit 37 for ctest/item/v2/sticky/health wrappers; a failed pre-check stops the run (exit 3, nothing executed);
the original nonzero status is kept; the sticky wrapper takes no lock and refuses to run without a parent-granted 4-CPU window.
usage: python3 test_c1_wrappers.py
"""
import os, pathlib, shutil, subprocess, sys, tempfile, unittest

SRC = pathlib.Path(__file__).resolve().parent


class Wrappers(unittest.TestCase):
    def setUp(self):
        self.W = W = pathlib.Path(tempfile.mkdtemp(prefix='mc-c1-wrapper-test-'))
        self.addCleanup(shutil.rmtree, W, True)
        (W / 'bin').mkdir(); (W / 'tools').mkdir(); (W / 'scratch/src/tools').mkdir(parents=True)
        for d in ('build-cuda', 'build-nvcomp', 'v2/v2fixtures'): (W / 'scratch' / d).mkdir(parents=True)
        for name, body in {
            'flock': '#!/bin/sh\nexit 0\n',
            'taskset': '#!/bin/sh\nshift 2\nexec "$@"\n',
            'git': '#!/bin/sh\ncase "$*" in "rev-parse HEAD") echo FROZEN;; "status --porcelain") :;; *) exit 91;; esac\n',
            'ctest': '#!/bin/sh\ncase "$*" in *" -N"*) echo "  Test #1: Example";; *) echo "mock ctest ok";; esac\nexit 0\n',
            'sha256sum': '#!/bin/sh\necho 0000 "$@"\n',
        }.items():
            (W / 'bin' / name).write_text(body); (W / 'bin' / name).chmod(0o755)
        (W / 'bin/mockpy').write_text('#!/bin/sh\nexit ${MOCK_PY_RC:-0}\n'); (W / 'bin/mockpy').chmod(0o755)
        (W / 'scratch/build-cuda/motioncorr').write_text('x'); (W / 'scratch/src/tools/validate_test_collection.py').write_text('')
        (W / 'tools/c1_env.sh').write_text(f'''export C1_SCR={W / 'scratch'}
export C1_SHA=FROZEN
export C1_PY={W / 'bin/mockpy'}
export C1_CPUS=0
export C1_GPU_UUID=GPU-test-harness-only
export C1_GPU_LOCK={W / 'fake-gpu-lock'}
''')
        occ = '#!/bin/sh\ncase "$1" in\n  *-post) exit ${MOCK_POST_RC:-0};;\n  *) exit ${MOCK_PRE_RC:-0};;\nesac\n'
        (W / 'tools/c1_occupancy.sh').write_text(occ); (W / 'tools/c1_occupancy.sh').chmod(0o755)
        for n in ('c1_ctest.sh', 'c1_item.sh', 'c1_v2.sh', 'c1_sticky.sh', 'c1_health.sh'):
            shutil.copy(SRC / n, W / 'tools' / n)

    def run_(self, script, *args, **env):
        e = dict(os.environ, PATH=f"{self.W / 'bin'}{os.pathsep}{os.environ['PATH']}", **env)
        return subprocess.run(['bash', str(self.W / 'tools' / script), *args], env=e, capture_output=True, text=True, timeout=30)

    def test_ctest_post_health_failure_is_exit_37(self):
        r = self.run_('c1_ctest.sh', 'cuda', MOCK_POST_RC='37')
        self.assertEqual(r.returncode, 37, r.stdout + r.stderr)
        self.assertEqual((self.W / 'scratch/ctest-cuda.exit').read_text().strip(), '0')       # the test run itself passed
        self.assertEqual((self.W / 'scratch/ctest-cuda.health-post.exit').read_text().strip(), '37')

    def test_ctest_pre_health_failure_runs_nothing(self):
        r = self.run_('c1_ctest.sh', 'cuda', MOCK_PRE_RC='3')
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.W / 'scratch/ctest-cuda.exit').exists())

    def test_ctest_healthy_is_zero(self):
        self.assertEqual(self.run_('c1_ctest.sh', 'cuda').returncode, 0)

    def test_health_wrapper_precedence(self):
        self.assertEqual(self.run_('c1_health.sh', 'x', 'true', MOCK_POST_RC='37').returncode, 37)
        self.assertEqual(self.run_('c1_health.sh', 'x2', 'sh', '-c', 'exit 5', MOCK_POST_RC='37').returncode, 5)
        r = self.run_('c1_health.sh', 'x3', 'touch', str(self.W / 'ran'), MOCK_PRE_RC='3')
        self.assertEqual(r.returncode, 3); self.assertFalse((self.W / 'ran').exists())

    def test_item_and_v2_post_health(self):
        self.assertEqual(self.run_('c1_item.sh', '12', MOCK_POST_RC='37').returncode, 37)
        self.assertEqual(self.run_('c1_item.sh', '9nvcomp', MOCK_POST_RC='37').returncode, 37)
        self.assertEqual(self.run_('c1_item.sh', '12', MOCK_POST_RC='37', MOCK_PY_RC='1').returncode, 1)
        self.assertEqual(self.run_('c1_v2.sh', 'cuda', MOCK_POST_RC='37').returncode, 37)
        self.assertEqual(self.run_('c1_v2.sh', 'cuda').returncode, 0)

    def test_sticky_takes_no_lock_and_needs_window(self):
        text = (SRC / 'c1_sticky.sh').read_text()
        self.assertNotIn('flock', ''.join(l for l in text.splitlines(True) if not l.lstrip().startswith('#')))
        r = self.run_('c1_sticky.sh', 'cuda')
        self.assertNotEqual(r.returncode, 0); self.assertIn('4-CPU', r.stderr + r.stdout)
        (self.W / 'scratch/src/tests').mkdir(parents=True); (self.W / 'scratch/build-sticky-cuda').mkdir()
        (self.W / 'scratch/build-sticky-cuda/motioncorr_sticky_fault').write_text('x')
        os.chmod(self.W / 'scratch/build-sticky-cuda/motioncorr_sticky_fault', 0o755)
        self.assertEqual(self.run_('c1_sticky.sh', 'cuda', C1_STICKY_CPUS='8-11', MOCK_POST_RC='37').returncode, 37)
        self.assertEqual(self.run_('c1_sticky.sh', 'cuda', C1_STICKY_CPUS='8-9').returncode, 2)   # fewer than 4 CPUs refused


if __name__ == '__main__':
    unittest.main(verbosity=2)
