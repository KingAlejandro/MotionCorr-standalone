#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Data-only v6.1 checks (AMENDMENT-v6.1.md): fake Popen/process tables/signals, no worker, query or job process.

Run under a nonblocking lifetime lease in a fresh UUID scratch namespace. These checks do not
admit the provider-bound real-worker suite and cannot qualify process cleanup or Linux/GPU use.
"""
import argparse
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location('v6_static_target', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class PauseReached(BaseException): pass


class Root:
    pid = 900001
    returncode = None
    mc_birth = 17
    def __init__(self): self.events = []; self.returncode = None
    def poll(self): raise AssertionError('root must not be polled/reaped before cleanup')
    def wait(self, timeout=None):
        self.events.append(['wait', timeout]); self.returncode = 0; return 0
    def send_signal(self, sig): self.events.append(['root', int(sig)])


class Table:
    def __init__(self, **over): self.row = dict(pid=900001, ppid=os.getpid(), pgid=900001, start=17, state='Z', **over)
    def read(self, pid): return dict(self.row)
    def group_live(self, pgid): return False


class Own:
    mode = 'synthetic-not-native'
    def __init__(self, fail=0, errors=()):
        self.table = Table(); self.errors = list(errors); self.calls = 0; self.fail = fail; self.identities = {}; self.active = True
    def refresh(self):
        self.calls += 1
        if self.calls == self.fail: raise RuntimeError('synthetic refresh error')
    def known_live(self): return []
    def verified_group(self, g): return True
    def watch(self, pid): self.identities[pid] = 17
    def activate(self, **kw): pass
    def start(self): pass
    def is_alive(self): return self.active
    def stop(self): self.active = False
    def join(self, timeout): pass
    def restore(self): pass


class Checks(unittest.TestCase):
    def worker(self, tmp):
        a = M.parse(['--root', tmp, '--queue', 'q', '--queue-sha256', 'x', '--runs-dir', tmp,
                     '--binaries', 'b', '--binaries-sha256', 'y', '--uuid', 'SYNTHETIC-NO-GPU', '--expected-jobs', '1',
                     '--cpu', '0', '--gpu-index', '2', '--prefix', '', '--cleanup-grace', '0'])
        w = M.Worker(a); w.binding = dict(source_sha='synthetic'); w.table = Table()
        w.smi.query = lambda: dict(target_pids=[], utc='synthetic')
        w.smi.admission_problems = lambda _: []
        return w

    def test_hold_before_io_and_broken_stderr(self):
        with tempfile.TemporaryDirectory() as t:
            w = self.worker(t); events = []
            def signals(s, h): events.append(('ignore', s, h))
            def fail_write(*a):
                self.assertTrue(w.holding)
                self.assertEqual(len(events), 3)
                events.append(('io',))
                raise OSError(errno.ENOSPC, 'synthetic full storage')
            class Broken:
                def write(self, x): raise OSError(errno.EIO, 'synthetic stderr failure')
                def flush(self): raise OSError(errno.EIO, 'synthetic stderr failure')
            with patch.object(M.signal, 'signal', signals), patch.object(M.signal, 'pause', side_effect=PauseReached), \
                    patch.object(M, '_atomic_write', fail_write), patch.object(M.sys, 'stderr', Broken()):
                with self.assertRaises(PauseReached): w.hold_lease('synthetic unresolved work')
            self.assertTrue(w.holding)
            self.assertEqual({x[1] for x in events[:3]}, {signal.SIGTERM, signal.SIGINT, signal.SIGHUP})
            self.assertTrue(w.write_errors)

    def test_atomic_write_failure_keeps_previous_record(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'RUN.json'; M._atomic_write(p, 'old\n')
            with patch.object(M.os, 'replace', side_effect=OSError(errno.EIO, 'synthetic rename failure')):
                with self.assertRaises(OSError): M._atomic_write(p, 'new\n')
            self.assertEqual(p.read_text(), 'old\n')
            self.assertEqual([x.name for x in Path(t).iterdir()], ['RUN.json'])

    def test_receipt_fallback_and_run_write_never_raise(self):
        with tempfile.TemporaryDirectory() as t:
            w = self.worker(t); out = io.StringIO()
            with patch.object(M, '_atomic_write', side_effect=OSError(errno.EIO, 'synthetic write error')), \
                    patch.object(M.sys, 'stderr', out):
                self.assertIsNone(w.receipt('STOP', reason='synthetic'))
                self.assertFalse(w.write(Path(t), dict(id='J', status='CLEANUP_FAILED')))
            rows = [json.loads(x) for x in out.getvalue().splitlines()]
            self.assertEqual([x['kind'] for x in rows], ['STOP', 'RUN_WRITE_FAILED'])

    def test_uncertain_branches_are_separate(self):
        for name, own in [('initial', Own(fail=1)), ('loop', Own(fail=2)), ('errors', Own(errors=['bad observer']))]:
            with self.subTest(branch=name):
                with patch.object(M, 'signal_job_group') as sig:
                    _, errors = M.terminate_owned(own, Root(), 0)
                self.assertEqual(sig.call_count, 1)
                self.assertTrue(errors)

    def test_original_group_term_kill_before_wait(self):
        root = Root(); calls = []
        with patch.object(M.os, 'getsid', return_value=root.pid), patch.object(M.os, 'killpg', side_effect=lambda g, s: calls.append([g, int(s)])):
            M.signal_job_group(root, 0, [], Table())
        self.assertEqual(calls, [[root.pid, int(signal.SIGTERM)], [root.pid, int(signal.SIGKILL)]])
        self.assertEqual(root.events, [['wait', 0]])

    def test_reaped_or_foreign_group_never_signalled(self):
        cases = [('birth', dict(start=18), 900001, None), ('ppid', dict(ppid=1), 900001, None),
                 ('pgid', dict(pgid=900002), 900001, None), ('sid', {}, 900002, None),
                 ('own-group', {}, 900001, 900001), ('reaped', {}, 900001, None)]
        for label, over, sid, mygroup in cases:
            with self.subTest(case=label):
                root = Root(); table = Table(); table.row.update(over)
                if label == 'reaped': root.returncode = 0
                with patch.object(M.os, 'getsid', return_value=sid), patch.object(M.os, 'getpgrp', return_value=mygroup or 800000), \
                        patch.object(M.os, 'killpg') as group:
                    M.signal_job_group(root, 0, [], table)
                group.assert_not_called()

    def run_job(self, tmp, uncertain=False, outputs=False, witness=False, write_error=False):
        w = self.worker(tmp); own = Own(); root = Root()
        job = dict(id='J', args=[], arm='plain', tier='C', backend='cuda', build='cuda-exp', group='g', cwd=tmp, inputs={})
        original_open = open
        def maybe_open(p, *a, **kw):
            if witness and str(p).endswith('/stderr.log') and kw.get('errors'): raise OSError('synthetic witness fault')
            return original_open(p, *a, **kw)
        with patch.object(M.subprocess, 'Popen', return_value=root), patch.object(M, 'terminate_owned', return_value=([], ['uncertain'] if uncertain else [])), \
                patch.object(M.campaign, 'bench_status', return_value='synthetic'), \
                patch.object(M.campaign, 'sha256', side_effect=OSError('synthetic outputs fault') if outputs else None, return_value='synthetic'), \
                patch('builtins.open', maybe_open):
            if write_error:
                with patch.object(M, '_atomic_write', side_effect=OSError(errno.EIO, 'synthetic records failure')), patch.object(M.sys, 'stderr', io.StringIO()):
                    rec, outcome = w.run_job(job, dict(path='NO-BINARY-LAUNCHED', sha256='synthetic'), own)
            else: rec, outcome = w.run_job(job, dict(path='NO-BINARY-LAUNCHED', sha256='synthetic'), own)
        return w, rec, outcome

    def test_cleanup_uncertainty_outranks_both_stage_faults(self):
        for fault in ['outputs', 'witness']:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as t:
                w, rec, outcome = self.run_job(t, uncertain=True, **{fault: True})
                self.assertEqual(outcome, 'CLEANUP_FAILED')
                self.assertEqual(rec['status'], 'CLEANUP_FAILED')
                self.assertIn(fault + '_error' if fault == 'outputs' else 'dc_witness_error', rec)
                self.assertFalse(w.job_cleanup_verified)

    def test_outputs_fault_alone_is_jobstage_with_record(self):
        with tempfile.TemporaryDirectory() as t:
            w, rec, outcome = self.run_job(t, outputs=True)
            self.assertEqual(outcome, 'JOB_STAGE'); self.assertIn('outputs_error', rec)
            self.assertTrue((Path(t) / 'J/RUN.json').exists()); self.assertTrue(w.job_cleanup_verified)

    def test_run_write_safe_outcome_only_after_cleanup(self):
        for uncertain in [False, True]:
            with self.subTest(uncertain=uncertain), tempfile.TemporaryDirectory() as t:
                w, rec, outcome = self.run_job(t, uncertain=uncertain, write_error=True)
                self.assertEqual(outcome, 'CLEANUP_FAILED' if uncertain else 'RECORD_WRITE')
                self.assertEqual(w.job_cleanup_verified, not uncertain)

    def test_zero_job_activation_failure_final(self):
        with tempfile.TemporaryDirectory() as t:
            w = self.worker(t); own = Own()
            with patch.object(M, 'ProcessOwnership', return_value=own), patch.object(own, 'activate', side_effect=RuntimeError('activation error')), \
                    patch.object(M.fcntl, 'flock'):
                code = w.locked_main([dict(id='J')], {}, io.StringIO())
            self.assertEqual(code, 75)
            final = list(Path(t).glob('FINAL-*.json')); self.assertEqual(len(final), 1)
            self.assertEqual(json.loads(final[0].read_text())['code'], 75)

    def test_all_normal_record_errors_are_typed_79_after_cleanup(self):
        for target in ['RUN', 'FINAL', 'ALL']:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as t:
                w = self.worker(t); own = Own(); out = io.StringIO(); atomic = M._atomic_write
                def failing(path, text):
                    if target == 'ALL' or path.name.startswith(target): raise OSError(errno.EIO, 'synthetic storage fault')
                    return atomic(path, text)
                def job(*a):
                    w.launched = 1
                    w.write(Path(t), dict(status='EXITED', id='J'))
                    return dict(status='EXITED'), 'RECORD_WRITE' if target != 'FINAL' else 'OK'
                with patch.object(M, 'ProcessOwnership', return_value=own), patch.object(w, 'run_job', job), \
                        patch.object(M.campaign, 'usage_bytes', return_value=0), patch.object(M, '_atomic_write', failing), \
                        patch.object(M.fcntl, 'flock'), patch.object(M.sys, 'stderr', out):
                    code = w.locked_main([dict(id='J', build='cuda-exp')], {'cuda-exp': {}}, io.StringIO())
                self.assertEqual(code, 79)
                self.assertTrue('RECORD_WRITE_FAILED' in out.getvalue() or any('RECORD_WRITE_FAILED' in p.read_text() for p in Path(t).glob('STOP-*')))

    def test_sighup_handler_installed_inside_lease_backstop(self):
        with tempfile.TemporaryDirectory() as t:
            w = self.worker(t); events = []
            with patch.object(w, 'bind', return_value=([], {}, [])), patch.object(w, 'locked_main', return_value=0), \
                    patch.object(M.signal, 'signal', side_effect=lambda sig, fn: events.append(sig)):
                self.assertEqual(w.main(), 0)
            self.assertIn(signal.SIGHUP, events)

    def test_embedded_mock_scripts_compile_without_execution(self):
        harness = load(TOOLS / 'test_gpu_worker_v6_1.py')
        for name in ['IDENT', 'MOCK_JOB', 'FAKE_SMI', 'FAULT_ENTRY', 'LAUNCHER', 'EMULATE']:
            with self.subTest(script=name): compile(getattr(harness, name), name, 'exec')

    def test_k22_exact_fixture_interface_and_own_group_exclusion(self):
        harness = load(TOOLS / 'test_gpu_worker_v6_1.py')
        with patch.object(M.subprocess, 'Popen', side_effect=AssertionError('forbidden Popen')), \
                patch.object(M.os, 'kill', side_effect=AssertionError('forbidden PID signal')), \
                patch.object(M.os, 'killpg', side_effect=AssertionError('forbidden real group signal')), \
                patch.object(M.signal, 'signal', side_effect=AssertionError('forbidden handler')):
            ok, detail = harness.k22(Path(TARGET))
        self.assertTrue(ok, detail)
        self.assertNotIn(detail['own_group'], detail['groups_signalled'])
        self.assertIn(900002, detail['groups_signalled'])

    def test_k36_healthy_and_late_error_interleavings(self):
        harness = load(TOOLS / 'test_gpu_worker_v6_1.py')
        ok, detail = harness.k36(Path(TARGET))
        self.assertTrue(ok, detail)
        self.assertEqual(detail['cases']['healthy']['fallback_calls'], 0)
        for mode in ['refresh', 'verify_true', 'verify_false']:
            self.assertEqual(detail['cases'][mode]['fallback_calls'], 1)
            self.assertTrue(detail['cases'][mode]['uncertainty_retained'])

    def test_new_version_controls_are_excluded_without_owner_rule_change(self):
        runner = load(TOOLS / 'run_v6_1_controls.py')
        rows = [dict(pid=11, ppid=1, uid=502, start=[4, 5], cmd='claude --resume=synthetic-owner'),
                dict(pid=12, ppid=11, uid=502, cmd='python run_v6_1_controls.py')]
        self.assertTrue(runner.admission(rows, 12, 11, [4, 5], 'synthetic-owner')[0])
        for cmd in ['python test_gpu_worker_v6_1.py', 'python run_v6_1_controls.py BASE',
                    'python /tmp/gpu_worker_v6_1_controls/attempt/mock_job']:
            with self.subTest(cmd=cmd):
                ok, reason, _ = runner.admission(rows + [dict(pid=13, ppid=11, uid=502, cmd=cmd)],
                                                  12, 11, [4, 5], 'synthetic-owner')
                self.assertFalse(ok)
                self.assertIn('control process', reason)

    def test_nonprovider_ancestor_is_refused_without_spoof(self):
        runner = load(TOOLS / 'run_v6_1_controls.py')
        rows = [dict(pid=11, ppid=1, uid=502, start=[4, 5], cmd='codex app-server'),
                dict(pid=12, ppid=11, uid=502, cmd='python run_v6_1_controls.py')]
        ok, why, _ = runner.admission(rows, 12, 11, [4, 5], 'synthetic-no-claude-session')
        self.assertFalse(ok); self.assertIn('lacks the exact --resume token', why)


def main():
    global M, TARGET
    ap = argparse.ArgumentParser(); ap.add_argument('--worker', default=str(TOOLS / 'gpu_worker_v6_1.py')); ap.add_argument('--json', required=True)
    a = ap.parse_args(); TARGET = a.worker; M = load(a.worker)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    Path(a.json).write_text(json.dumps(dict(schema='dc262-v6.1-data-only/1', worker_sha256=hashlib.sha256(Path(a.worker).read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), tests=result.testsRun,
        failures=[dict(test=str(t), trace=s) for t, s in result.failures], errors=[dict(test=str(t), trace=s) for t, s in result.errors],
        result='PASS' if result.wasSuccessful() else 'FAIL', limits='Synthetic Popen/process tables/signals only; process cleanup, real-worker suite, Linux and GPU UNRUN.'), indent=1)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': sys.exit(main())
