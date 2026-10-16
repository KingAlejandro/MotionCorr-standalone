#!/usr/bin/env python3
"""Receipt provenance tests; all workload launches are mocked (no measurements)."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

DRIVERS = Path(__file__).resolve().parents[1]
REPO = DRIVERS.parents[1]
sys.path[:0] = [str(DRIVERS), str(REPO / 'tools/profiling')]
from lib import identity, provenance


def load(name):
    spec = importlib.util.spec_from_file_location(name, DRIVERS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Sources(unittest.TestCase):
    def test_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('base', 'candidate', 'tutorial.tiff', 'gain.mrc', 'synthetic_512x512_16frames.mrcs'):
                (root / name).write_bytes(name.encode())
            venue = {'masks': {1: '44', 4: '44-47'}, 'requested_affinity': {1: [44], 4: [44, 45, 46, 47]}}
            # Driver revision deliberately differs from both attested builds.
            driver, base, candidate = 'd' * 40, 'a' * 40, 'b' * 40
            def output(command, **kwargs):
                if command[0] == 'git':
                    return driver + '\n'
                return json.dumps([44] if command[2] == '44' else [44, 45, 46, 47]).encode()

            products = load('run_products')
            argv = ['run_products', '--base', str(root / 'base'), '--candidate', str(root / 'candidate'),
                    '--data', str(root), '--out', str(root / 'products'),
                    '--base-source-sha', base, '--candidate-source-sha', candidate]
            child = SimpleNamespace(pid=123, returncode=None)
            usage = SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0)
            argv += ['--cpus-j1', '44', '--cpus-j4', '44-47']
            with patch.object(sys, 'argv', argv), patch.object(products, 'validate', return_value=venue), \
                 patch.object(products.fcntl, 'flock'), patch.object(products.platform, 'platform', return_value='mock host'), patch.object(provenance, 'compilers_running', return_value=False), \
                 patch.object(products.subprocess, 'check_output', side_effect=output), \
                 patch.object(products.subprocess, 'Popen', return_value=child), \
                 patch.object(products.os, 'wait4', return_value=(123, 0, usage)), \
                 patch.object(identity, 'compare_trees', side_effect=lambda a, b: {'identical': True, 'root_a': a, 'root_b': b}), \
                 patch.object(identity, 'inventory', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                products.main()
            receipt = json.loads((root / 'products/identity-results.json').read_text())
            self.assertEqual(receipt['driver_source'], driver)
            self.assertEqual(receipt['binaries']['base']['source']['commit'], base)
            self.assertEqual(receipt['binaries']['candidate']['source']['commit'], candidate)
            self.assertNotEqual(receipt['binaries']['base']['sha256'], receipt['binaries']['candidate']['sha256'])

            kernel = load('run_kernel')
            pairs = b'\n'.join(json.dumps({'reference_seconds': 1, 'candidate_seconds': 1, 'bitwise_equal': True}).encode() for _ in range(6))
            argv = ['run_kernel', '--binary', str(root / 'candidate'), '--source-sha', candidate, '--out', str(root / 'kernel')]
            argv += ['--cpus-j1', '44', '--cpus-j4', '44-47']
            with patch.object(sys, 'argv', argv), patch.object(kernel, 'validate', return_value=venue), \
                 patch.object(kernel.fcntl, 'flock'), patch.object(kernel.subprocess, 'check_output', side_effect=output), \
                 patch.object(kernel.subprocess, 'run', return_value=SimpleNamespace(stdout=pairs, stderr=b'', returncode=0)), \
                 contextlib.redirect_stdout(io.StringIO()):
                kernel.main()
            receipt = json.loads((root / 'kernel/results.json').read_text())['receipt']
            self.assertEqual(receipt['driver_source'], driver)
            self.assertEqual(receipt['source']['commit'], candidate)

    def test_missing_or_invalid_sha_fails_before_venue(self):
        for name, argv in [('run_kernel', ['--binary', '/unused']),
                           ('run_kernel', ['--binary', '/unused', '--source-sha', 'HEAD']),
                           ('run_products', ['--base', '/a', '--candidate', '/b', '--data', '/d', '--out', '/o']),
                           ('run_products', ['--base', '/a', '--candidate', '/b', '--data', '/d', '--out', '/o',
                                             '--base-source-sha', 'HEAD', '--candidate-source-sha', 'b' * 40])]:
            module = load(name)
            argv += ['--cpus-j1', '44', '--cpus-j4', '44-47']
            with patch.object(sys, 'argv', [name] + argv), patch.object(module, 'validate') as venue, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                module.main()
            self.assertEqual(raised.exception.code, 2)
            venue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
