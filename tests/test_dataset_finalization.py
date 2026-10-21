#!/usr/bin/env python3
"""#240: strict compilation and exit/status precedence through finalization."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/multi_gpu'))
import run_dataset as dataset


class Finalization(unittest.TestCase):
    def test_no_finally_return(self):
        source = Path(dataset.__file__).read_text()
        with warnings.catch_warnings():
            warnings.simplefilter('error', SyntaxWarning)
            compile(source, dataset.__file__, 'exec')
        # Equivalent powered control on Python <3.14 as well.
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Try):
                self.assertFalse(any(isinstance(n, ast.Return)
                                     for stmt in node.finalbody for n in ast.walk(stmt)))

    def run_case(self, kind, restore_fails=False, interrupt_after_pass=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); binary = root/'binary'; binary.write_text('binary')
            star = root/'input.star'; star.write_text('input')
            out = root/'out'
            ownership = Mock(ident=None, errors=[], mode='fake')
            ownership.known_live.return_value = []
            if restore_fails: ownership.restore.side_effect = RuntimeError('restore')
            if kind == 'exception': ownership.activate.side_effect = ValueError('try')
            if kind == 'baseexception': ownership.activate.side_effect = KeyboardInterrupt('try')
            if kind == 'signal': ownership.activate.side_effect = dataset.run_multi_gpu.LauncherInterrupted(15)
            sampler = Mock(ident=None, errors=[])
            sampler.is_alive.return_value = False
            sampler.report.return_value = {'status':'UNAVAILABLE'}
            def launch(cmd, **kwargs):
                worker = str(cmd[1]).endswith('run_multi_gpu.py')
                if worker:
                    (out/'workers/shards').mkdir(parents=True)
                    manifest = out/'workers/shards/shard_manifest.json'
                    manifest.write_text(json.dumps({'input_sha256':hashlib.sha256(star.read_bytes()).hexdigest()}))
                    (out/'workers/status.json').write_text(json.dumps({
                        'verdict':'PASS','manifest':str(manifest),'n_workers':1,'cpu_masks':[]}))
                else:
                    (out/'aggregate.json').write_text(json.dumps({
                        'verdict':'FAIL' if kind=='report' else 'PASS',
                        'dataset_ready':kind!='report'}))
                return Mock(pid=123, wait=Mock(return_value=(7 if kind=='worker' and worker else
                                                          9 if kind=='aggregate' and not worker else 0)))
            with patch.object(dataset, 'ProcessOwnership', return_value=ownership), \
                 patch.object(dataset, 'OwnedTreeSampler', return_value=sampler), \
                 patch.object(dataset.subprocess, 'Popen', side_effect=launch), \
                 patch.object(dataset, 'cleanup', return_value='cleaned'), \
                 patch.object(dataset.run_multi_gpu, '_install_signal_handlers', return_value={}), \
                 patch.object(dataset.run_multi_gpu, '_restore_signal_handlers') as restore_handlers, \
                 patch.object(dataset.run_multi_gpu, '_ignore_launcher_signals'):
                entrypoint = dataset.main
                if interrupt_after_pass:
                    # Inject a BaseException inside the try after PASS, to check
                    # the old finally-return suppression precedence explicitly.
                    source = Path(dataset.__file__).read_text().replace(
                        "status['dataset_ready']=True;status['verdict']='PASS'",
                        "status['dataset_ready']=True;status['verdict']='PASS';raise KeyboardInterrupt('after PASS')")
                    namespace = vars(dataset).copy()
                    exec(compile(source, dataset.__file__, 'exec'), namespace)
                    namespace.update({key:getattr(dataset,key) for key in
                                      ('ProcessOwnership','OwnedTreeSampler','cleanup')})
                    entrypoint = namespace['main']
                try:
                    result = entrypoint(['--binary',str(binary),'--star',str(star),'--out',str(out)])
                except KeyboardInterrupt:
                    result = 'KeyboardInterrupt'
                restore_handlers.assert_called_once_with({})
            status = json.loads((out/'dataset_status.json').read_text())
            self.assertIn('tree_rss', status)
            self.assertIn('process_ownership_errors', status)
            self.assertIsInstance(status['dataset_wall_s'], float)
            return result, status

    def test_exit_and_status_precedence(self):
        for kind, rc in [('healthy',0), ('worker',7), ('aggregate',9), ('report',3),
                         ('exception',3), ('signal',143), ('baseexception','KeyboardInterrupt')]:
            for fails in (False, True):
                with self.subTest(kind=kind, restore_fails=fails):
                    result, status = self.run_case(kind, fails)
                    self.assertEqual(result, 3 if kind=='healthy' and fails else rc)
                    self.assertEqual(status['dataset_ready'], kind=='healthy' and not fails)
                    self.assertEqual(status['verdict'], 'PASS' if kind=='healthy' and not fails else 'FAIL')
                    self.assertEqual(status.get('cleanup_error'), 'RuntimeError: restore' if fails else None)
                    if kind in ('exception','signal'): self.assertEqual(status['cleanup'], 'cleaned')

    def test_pending_exception_after_pass(self):
        for fails in (False, True):
            with self.subTest(restore_fails=fails):
                result, status = self.run_case('healthy', fails, interrupt_after_pass=True)
                self.assertEqual(result, 3 if fails else 'KeyboardInterrupt')
                self.assertEqual(status['verdict'], 'FAIL' if fails else 'PASS')


if __name__ == '__main__': unittest.main()
