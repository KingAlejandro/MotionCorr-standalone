#!/usr/bin/env python3
"""Host controls for c1_ingest_poison.py's verdict functions (no GPU): a faithful synthetic faulted run must PASS fault_verdict, and each single-requirement
mutation of it must be rejected; healthy/notarget synthetic runs must pass their own verdicts and be rejected by fault_verdict. usage: python3 test_c1_ingest_poison.py"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c1_ingest_poison as d  # noqa: E402

ARM_LOG = ("ERROR: the CUDA context became unusable during device ingestion of Movies/control.tiff; refusing to report a successful ingest.\n")
CONSOLE = (
    "[ingeststicky] gain-launch index=0\n"
    "[ingeststicky] gain-launch index=1\n"
    "[ingeststicky] launch illegal write before ingest gain launch 1\n"
    "[ingeststicky] fault completion=700 (an illegal memory access was encountered)\n"
    "[ingeststicky] product launch result=700 (an illegal memory access was encountered), unchanged\n"
    "CUDA device became unusable during device movie ingestion for Movies/control.tiff: an illegal memory access was encountered (recorded at ingest:1500). "
    "First failure at ingest:1500. Refusing CPU fallback after a fatal device error.\n"
    "Motion correction failed for 3 movie(s): Movies/control.tiff Movies/after1.tiff Movies/after2.tiff. "
    "Successful per-movie outputs were retained; joint output was not generated.\n"
    "[ingeststicky] exit gain-launches=2 faulted=1\n")


def healthy_console(n):
    return ''.join(f'[ingeststicky] gain-launch index={i}\n' for i in range(3 * n))


class Controls(unittest.TestCase):
    def out(self, files=('Movies/control.log',)):
        t = Path(tempfile.mkdtemp())
        for f in files:
            (t / f).parent.mkdir(parents=True, exist_ok=True)
            (t / f).write_text(ARM_LOG if f.endswith('.log') else 'x')
        return t

    def verdict(self, console=CONSOLE, rc=1, files=('Movies/control.log',), witness='', count=3):
        d.fault_verdict(rc, console, self.out(files), count, witness)

    def test_faithful_passes(self):
        self.verdict()
        d.fault_verdict(1, CONSOLE.replace('[ingeststicky] exit gain-launches=2 faulted=1\n', ''), self.out(), 3, '')   # exit summary may be absent

    def rejects(self, why=None, **kw):
        with self.assertRaises(d.Reject) as cm:
            self.verdict(**kw)
        if why:   # the mutation must be rejected for the requirement it targets, not by an unrelated item
            self.assertIn(why, str(cm.exception))

    def test_each_mutation_is_rejected(self):
        self.rejects(console=CONSOLE.replace('launch illegal write before ingest gain launch 1', 'launch illegal write before ingest gain launch 2'))
        self.rejects(console=CONSOLE.replace('[ingeststicky] launch illegal write before ingest gain launch 1\n', ''))
        self.rejects(console=CONSOLE.replace('[ingeststicky] launch illegal write before ingest gain launch 1\n',
                                             '[ingeststicky] launch illegal write before ingest gain launch 1\n' * 2))
        self.rejects(console=CONSOLE.replace('completion=700 ', 'completion=0 '))
        self.rejects(console=CONSOLE.replace('product launch result=700 ', 'product launch result=0 '))
        self.rejects(rc=0)
        self.rejects(rc=2)
        self.rejects('fatal ingest refusal', console=CONSOLE.replace('Refusing CPU fallback after a fatal device error', 'Refusing'))
        self.rejects('fatal ingest refusal', console=CONSOLE.replace('during device movie ingestion for Movies/control.tiff', 'during device movie ingestion for Movies/other.tiff'))
        self.rejects('fatal ingest refusal', console=CONSOLE.replace('during device movie ingestion', 'during session setup'))     # poisoning not attributed to the ingest boundary
        self.rejects('fallback or decline', console=CONSOLE + 'WARNING: Failed to initialize CUDA movie session, falling back to streaming pipeline.\n')
        self.rejects('fallback or decline', console=CONSOLE + 'nvCOMP ingestion declined (TIFF file identity changed or unavailable)\n')
        # review (Sol) mutants
        self.rejects('missing, duplicate or unexpected', console=CONSOLE + 'Motion correction failed for 1 movie(s): Movies/control.tiff. Successful per-movie outputs were retained; joint output was not generated.\n')   # malformed-for-count extra record
        self.rejects('malformed final movie failure record', console=CONSOLE + 'Motion correction failed for the movies somehow\n')   # malformed extra record beside a correct one
        self.rejects('expected exactly [0, 1]', console=CONSOLE.replace('index=0\n[ingeststicky] gain-launch index=1', 'index=1\n[ingeststicky] gain-launch index=0'))   # reversed indices
        self.rejects('inconsistent interposer exit summary', console=CONSOLE.replace('gain-launches=2 faulted=1', 'gain-launches=3 faulted=1'))
        self.rejects('inconsistent interposer exit summary', console=CONSOLE.replace('gain-launches=2 faulted=1', 'gain-launches=2 faulted=0'))
        self.rejects('inconsistent interposer exit summary', console=CONSOLE + '[ingeststicky] exit gain-launches=2 faulted=1\n')
        self.rejects('completion records', console=CONSOLE + '[ingeststicky] fault completion=0 (no error)\n')
        self.rejects('product ingest launch result records', console=CONSOLE + '[ingeststicky] product launch result=0 (no error), unchanged\n')   # two summaries
        self.rejects('route witness was published', witness=' \n')    # whitespace-only is not empty
        self.rejects('fatal ingest refusal', console=CONSOLE.replace('Refusing CPU fallback after a fatal device error.\n', 'x\n') + 'CUDA device became unusable during session initialization for Movies/after1.tiff: e. Refusing CPU fallback after a fatal device error.\n')   # two lines must not be joined
        self.rejects('route witness was published', witness='Movies/control.tiff\n')    # malformed non-empty witness text
        self.rejects('route witness was published', witness='Movies/control.tiff nvcomp\n')    # fatal ingest cannot publish a successful nvcomp route witness
        self.rejects(console=CONSOLE + 'Device ingestion failed recoverably for Movies/control.tiff; re-reading the movie with the host reader.\n')
        self.rejects(console=CONSOLE + 'Staging this movie as native unsigned 16-bit\n')
        self.rejects(witness='Movies/control.tiff compact\n')
        self.rejects(console=CONSOLE.replace('Movies/after2.tiff.', '.').replace('3 movie(s): Movies/control.tiff Movies/after1.tiff ', '3 movie(s): Movies/control.tiff Movies/after1.tiff'))
        self.rejects(console=CONSOLE.replace('Motion correction failed for 3 movie(s)', 'Motion correction failed for 2 movie(s)'))
        self.rejects(console=CONSOLE.replace('Motion correction failed for', 'Failure for'))
        self.rejects(console=CONSOLE + '[ingeststicky] PRODUCT_KERNEL_AFTER_FAULT\n')
        self.rejects(console=CONSOLE.replace('[ingeststicky] gain-launch index=1\n', ''))
        self.rejects(console=CONSOLE + '[ingeststicky] gain-launch index=2\n')
        self.rejects(files=('Movies/control.log', 'Movies/control.mrc'))
        self.rejects(files=('Movies/control.log', 'corrected_micrographs.star'))

    def test_healthy_and_notarget_runs_are_rejected_by_the_fault_verdict(self):
        out = self.out(('Movies/control.log', 'Movies/control.mrc'))
        for console in (healthy_console(3), ''):
            with self.assertRaises(d.Reject):
                d.fault_verdict(0, console, out, 3, 'Movies/control.tiff nvcomp\n')

    def test_healthy_verdicts(self):
        t = Path(tempfile.mkdtemp())
        for m in d.MOVIES:
            for ext in ('mrc', 'star'):
                (t / 'Movies').mkdir(exist_ok=True)
                (t / 'Movies' / f'{Path(m).stem}.{ext}').write_text('x')
        (t / 'corrected_micrographs.star').write_text('x')
        w = ''.join(f'{m} nvcomp\n' for m in d.MOVIES)
        d.ingest_healthy_verdict(0, healthy_console(3), t, 3, w)
        with self.assertRaises(d.Reject): d.ingest_healthy_verdict(0, healthy_console(3), t, 3, w.replace('nvcomp', 'float', 1))
        with self.assertRaises(d.Reject): d.ingest_healthy_verdict(0, healthy_console(2), t, 3, w)
        with self.assertRaises(d.Reject): d.ingest_healthy_verdict(1, healthy_console(3), t, 3, w)
        d.notarget_verdict(0, '', t, 3, ''.join(f'{m} float\n' for m in d.MOVIES))
        with self.assertRaises(d.Reject): d.notarget_verdict(0, healthy_console(1), t, 3, '')     # ingest was entered
        with self.assertRaises(d.Reject): d.notarget_verdict(0, '', t, 3, w)                       # witness nvcomp

    def test_expect_reject_helper_discriminates(self):
        out = self.out(('Movies/control.log',))
        self.assertEqual(d.expect_reject('x', d.fault_verdict, 0, healthy_console(3), out, 3, '')['verdict'], 'PASS')
        self.assertEqual(d.expect_reject('x', d.fault_verdict, 1, CONSOLE, out, 3, '')['verdict'], 'FAIL')    # a faithful run is NOT rejected -> control FAIL


class PhaseControl(unittest.TestCase):
    """main() with stubbed health/run_arm: a failed post-run health stops the phase; an abort keeps the original error and a saved receipt."""
    def run_main(self, health, run_arm):
        import os, json
        work = Path(tempfile.mkdtemp()) / 'w'
        old = (d.health, d.run_arm, d.prepare_inputs, getattr(os, 'sched_getaffinity', None), dict(os.environ), sys.argv)
        d.health, d.run_arm = health, run_arm
        def prep(w, _t):
            (w / 'input').mkdir(parents=True); (w / 'input-sha256.json').write_text('{}'); return w / 'input'
        d.prepare_inputs = prep
        os.sched_getaffinity = lambda _p: {0}
        os.environ['C1_GPU_UUID'] = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
        sys.argv = ['x', '--binary', __file__, '--workdir', str(work), '--phase', 'pre']
        try:
            try:
                d.main()
                raised = None
            except BaseException as exc:      # noqa: BLE001
                raised = exc
        finally:
            d.health, d.run_arm, d.prepare_inputs = old[:3]
            if old[3] is None: del os.sched_getaffinity
            else: os.sched_getaffinity = old[3]
            os.environ.clear(); os.environ.update(old[4]); sys.argv = old[5]
        res = json.loads((work / 'result.json').read_text()) if (work / 'result.json').exists() else None
        return raised, res

    def test_post_health_failure_stops_the_phase(self):
        calls = []
        def health(label):
            return {'label': label, 'rc': 6 if label.endswith('-post') else 0, 'msg': ''}
        def run_arm(name, *a, **k):
            calls.append(name)
            out = Path(tempfile.mkdtemp())
            return ({'arm': name, 'rc': 0, 'witness': '', 'leftover_pids': []}, '', out)
        raised, res = self.run_main(health, run_arm)
        self.assertIsInstance(raised, SystemExit)
        self.assertEqual(len(calls), 1, 'no later arm may run after a failed post-run health check')
        self.assertEqual(res['arms'][0]['verdict'], 'FAIL')
        self.assertEqual(res['verdict'], 'ABORTED')

    def test_abort_keeps_original_error_and_receipt_even_if_health_raises(self):
        def health(label):
            if label.endswith('-post'): raise TimeoutError('nvidia-smi hung')
            return {'label': label, 'rc': 0, 'msg': ''}
        def run_arm(name, *a, **k):
            raise d.ArmAborted({'arm': name, 'aborted': 'KeyboardInterrupt'}, 'interrupted')
        raised, res = self.run_main(health, run_arm)
        self.assertIsInstance(raised, d.ArmAborted)       # the original error, not the health timeout
        self.assertEqual(res['arms'][0]['verdict'], 'ABORTED')
        self.assertIsNone(res['arms'][0]['health_post']['rc'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
