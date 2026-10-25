#!/usr/bin/env python3
"""Import-only control for the c1_item12.py QF-helper binding (R12/12ds deployment precondition).

The deployed copy sits at $C1_SCR/tools-*-run/c1_item12.py, three directories below the scratch root, so a
repo-relative parents[3] lookup resolves /mnt/rc0/qf/tools. Each case runs `c1_item12.py --help` (argparse exits
before any native work, no GPU, no build, no lock file) with the real qual_lib.py copied into a temporary layout.
The restored-base mutant must fail in the relocated layout, which is what makes the passing cases meaningful.
Run: python3 -B -I test_c1_item12_binding.py
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parents[2]                                   # docs/ (this file is docs/post_rc0/c1-20261022/tools-v2/)
QF = DOCS / 'rc0' / 'qf' / 'tools'
BINDING = re.compile(r"# C1: QF helpers are read in place\..*?SystemExit\(f'c1_item12: QF helpers not found at \{HERE\}'\)\n", re.S)
BASE_LINE = "HERE = Path(__file__).resolve().parents[3] / 'rc0' / 'qf' / 'tools'   # C1: QF helpers are read in place\n"


class Binding(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='c1item12-bind-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.scr = self.tmp / 'mnt' / 'clathrin' / 'scr'                          # stands in for $C1_SCR
        (self.scr / 'src/docs/rc0/qf').mkdir(parents=True)
        shutil.copytree(QF, self.scr / 'src/docs/rc0/qf/tools', ignore=shutil.ignore_patterns('__pycache__', '._*'))
        self.tools = self.scr / 'tools-v2.3-run'
        self.tools.mkdir()
        for f in ('c1_lane.py', 'c1_item12.py'):
            shutil.copy(HERE / f, self.tools / f)

    def run_help(self, script, c1_scr):
        env = {'PATH': os.environ['PATH'], 'QF_W': str(self.scr), 'QF_CPUS': '0', 'QF_GPU_UUID': 'GPU-none',
               'QF_GPU_LOCK': str(self.tmp / 'gpu.lock')}
        if c1_scr is not None:
            env['C1_SCR'] = str(c1_scr)
        return subprocess.run([sys.executable, '-I', '-B', str(script), '--help'], cwd=self.tmp, env=env,
                              capture_output=True, text=True, timeout=60)

    def test_relocated_layout_imports(self):
        r = self.run_help(self.tools / 'c1_item12.py', self.scr)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('usage', r.stdout)

    def test_restored_base_binding_fails_in_relocated_layout(self):
        text = (self.tools / 'c1_item12.py').read_text()
        self.assertEqual(len(BINDING.findall(text)), 1)
        (self.tools / 'c1_item12.py').write_text(BINDING.sub(lambda m: BASE_LINE, text))
        r = self.run_help(self.tools / 'c1_item12.py', self.scr)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No module named 'qual_lib'", r.stderr)

    def test_wrong_c1_scr_fails_closed_without_fallback(self):
        empty = self.tmp / 'empty'
        empty.mkdir()
        r = self.run_help(self.tools / 'c1_item12.py', empty)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('QF helpers not found at ' + str(empty / 'src/docs/rc0/qf/tools'), r.stderr)

    def test_repo_layout_without_c1_scr_still_imports(self):
        r = self.run_help(HERE / 'c1_item12.py', None)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_generator_reproduces_committed_files(self):
        docs = self.tmp / 'docs'
        (docs / 'rc0/qf/tools').mkdir(parents=True)
        shutil.copy(QF / 'item12_retry.py', docs / 'rc0/qf/tools/item12_retry.py')
        gen = docs / 'post_rc0/c1-20261022/tools-v2'
        gen.mkdir(parents=True)
        shutil.copy(HERE / 'make_c1_item12.py', gen / 'make_c1_item12.py')
        r = subprocess.run([sys.executable, '-I', '-B', str(gen / 'make_c1_item12.py')], cwd=gen, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in ('c1_item12.py', 'c1_item12.diff'):
            self.assertEqual((gen / f).read_bytes(), (HERE / f).read_bytes(), f)


if __name__ == '__main__':
    unittest.main()
