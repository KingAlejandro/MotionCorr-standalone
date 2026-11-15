#!/usr/bin/env python3
"""Local network-cleanup semantics and required EER dependency controls (#235)."""
import builtins
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tools/profiling')]
import mcprof
import test_truncated_gain_defect as gain


class Hygiene(unittest.TestCase):
    def test_selftest_avoids_network_tmpdir(self):
        with tempfile.TemporaryDirectory(prefix='network-tmp-') as network:
            real_rmdir = os.rmdir
            def late_file(path, *args, **kwargs):
                # Model the final network rmdir seeing an unlinked/open or
                # late-created file. Do not suppress the real ENOTEMPTY.
                full = Path(path)
                if kwargs.get('dir_fd') is not None:
                    full = Path(os.readlink('/dev/fd/' + str(kwargs['dir_fd']))) / path
                if str(full).startswith(network) and full.exists():
                    (full / '.late-file').touch()
                return real_rmdir(path, *args, **kwargs)
            class Scratch(unittest.TestCase):
                def runTest(self):
                    with tempfile.TemporaryDirectory() as tmp:
                        Path(tmp, 'data').write_text('fixture')
            original = tempfile.tempdir
            try:
                tempfile.tempdir = network
                with patch.dict(os.environ, {'TMPDIR': network}), \
                     patch.object(mcprof.unittest.defaultTestLoader, 'discover',
                                  return_value=unittest.TestSuite([Scratch()])), \
                     patch('os.rmdir', side_effect=late_file):
                    self.assertEqual(mcprof.cmd_selftest(SimpleNamespace(verbose=False), []), 0)
                    self.assertEqual(os.environ['TMPDIR'], network)
                    self.assertEqual(tempfile.tempdir, network)
            finally:
                tempfile.tempdir = original

    def test_supplied_eer_without_pillow_fails(self):
        real_import = builtins.__import__
        def no_pillow(name, *args, **kwargs):
            if name == 'PIL':
                raise ImportError('controlled missing Pillow')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=no_pillow):
            failures = gain.eer_section(SimpleNamespace(eer_movie='movie.eer', eer_gain='gain.tiff'), Path('.'))
        self.assertTrue(failures, 'required EER section silently passed')
        self.assertIn('NOT RUN', failures[0])


if __name__ == '__main__':
    unittest.main()
