#!/usr/bin/env python3
"""Host regressions for declaration support; no native test is executed.

SPDX-License-Identifier: GPL-2.0-or-later
FIT_REGISTRATION_CHECKER may select the historical checker for a negative control.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('registration_subject',
    os.environ.get('FIT_REGISTRATION_CHECKER', str(HERE/'check_registration.py')))
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
with tarfile.open(HERE/'native_attempt02/evidence.tar.gz') as archive:
    RETAINED = archive.extractfile('local/CTestTestfile.cmake').read().decode()
    COLLECTED = json.load(archive.extractfile('remote/collection.stdout'))


class RegistrationChecks(unittest.TestCase):
    def check(self, text, collected=COLLECTED, reject=False):
        real_run = subprocess.run
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[0] == 'ctest':
                return subprocess.CompletedProcess(argv, 0, json.dumps(collected), '')
            # Run the real existing required-test validator on declarations.
            return real_run(argv, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work/'CTestTestfile.cmake').write_text(text)
            with patch.object(sys, 'argv', ['checker', str(ROOT), str(work), str(work)]), \
                    patch.object(subject.subprocess, 'run', side_effect=run), \
                    contextlib.redirect_stdout(io.StringIO()):
                if reject:
                    with self.assertRaises((AssertionError, ValueError)):
                        subject.main()
                    return
                subject.main()
            report = json.loads((work/'registration-check.json').read_text())
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['count'], 84)
            self.assertEqual([r['exit'] for r in report['commands']], [0, 1, 1, 1, 1])
            inventory = json.loads((work/'declared-collection.json').read_text())
            self.assertEqual([t['name'] for t in inventory['tests']],
                             [t['name'] for t in collected['tests']])
            self.assertEqual(len(calls), 6)

    def test_retained_cmake_328_bracket_names(self):
        self.assertIn('add_test([=[RunnerFitBoundary]=]', RETAINED)
        self.check(RETAINED)

    def test_ordinary_quoted_names(self):
        text = re.sub(r'\[=\[([^\]]+)\]=\]', r'"\1"', RETAINED)
        self.check(text)

    def test_ordinary_unquoted_names(self):
        text = re.sub(r'\[=\[([^\]]+)\]=\]', r'\1', RETAINED)
        self.check(text)

    def test_other_bracket_delimiter(self):
        self.check(RETAINED.replace('[=[', '[==[').replace(']=]', ']==]'))

    def test_missing_declaration(self):
        text = '\n'.join(line for line in RETAINED.splitlines()
                         if not line.startswith('add_test([=[RunnerFitBoundary]=]'))
        self.check(text, reject=True)

    def test_required_name_missing_from_both_inventories(self):
        text = '\n'.join(line for line in RETAINED.splitlines()
                         if not line.startswith('add_test([=[RunnerFitBoundary]=]'))
        collected = dict(tests=[t for t in COLLECTED['tests'] if t['name'] != 'RunnerFitBoundary'])
        self.check(text, collected, reject=True)

    def test_duplicate_declaration(self):
        line = next(line for line in RETAINED.splitlines() if line.startswith('add_test('))
        self.check(RETAINED+'\n'+line, reject=True)

    def test_duplicate_in_both_inventories(self):
        # Historical equality and required-name checks accepted this duplicate.
        text = re.sub(r'\[=\[([^\]]+)\]=\]', r'"\1"', RETAINED)
        line = next(line for line in text.splitlines() if line.startswith('add_test('))
        collected = dict(tests=COLLECTED['tests']+[COLLECTED['tests'][0]])
        self.check(text+'\n'+line, collected, reject=True)

    def test_duplicate_canonical_name(self):
        self.check(RETAINED, dict(tests=COLLECTED['tests']+[COLLECTED['tests'][0]]), reject=True)

    def test_malformed_declarations(self):
        line = next(line for line in RETAINED.splitlines() if line.startswith('add_test('))
        for invalid in ['add_test([=[Broken] /bin/true)', 'add_test("Broken /bin/true)',
                        'add_test(Name)', 'add_test(Name "")', 'add_test(Name /bin/true',
                        'add_test("" /bin/true)', 'add_test([=[Name]=]suffix /bin/true)']:
            with self.subTest(invalid=invalid):
                self.check(RETAINED.replace(line, invalid, 1), reject=True)

    def test_empty_declarations(self):
        self.check('# no declarations\n', dict(tests=[]), reject=True)


if __name__ == '__main__':
    unittest.main()
