#!/usr/bin/env python3
"""Harmless host controls for the tools-v2 T24 comparison/attribution and GPU3 lane helpers (mock reports, mock programs; no device, no native run).

Covers the parent's findings: invalid comparator output must never read as identity or as an empty difference; a valid numeric difference must be
preserved; N-only reproduction is labelled as the combined composition; the lane runner stops on lease contention and on a foreign occupant before launch,
uses LOCK_NB, and propagates a failed post-run health check as rc 37 while the lease is still held.
usage: python3 test_c1_t24_failclosed.py
"""
import fcntl, importlib, json, os, pathlib, stat, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
TMP = pathlib.Path(tempfile.mkdtemp(prefix='mc-c1-t24-test-'))
(TMP / 'scr').mkdir(); os.symlink(REPO, TMP / 'scr/src')
(TMP / 'frozen/multigpu/G').mkdir(parents=True); (TMP / 'frozen/multigpu/L').mkdir(parents=True); (TMP / 'data').mkdir()
MOVIES = [f'Movies/20170629_{i:05d}_frameImage.tiff' for i in range(24)]
for cfg in 'GL': (TMP / f'frozen/multigpu/{cfg}/manifest.json').write_text(json.dumps({'movies': MOVIES, 'joint_star': 'corrected_micrographs.star'}))
(TMP / 'data/movies.star').write_text('x')
os.environ.update(C1_SCR=str(TMP / 'scr'), C1_TUTORIAL=str(TMP / 'data'), C1_FROZEN_RC0=str(TMP / 'frozen'), QF_W=str(TMP / 'scr'), QF_CPUS='0',
                  QF_GPU_UUID='GPU-test', QF_GPU_LOCK=str(TMP / 'gpu.lock'), C1_GPU_UUID='GPU-test', C1_PY=sys.executable)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / 'docs/rc0/qf/tools'))
t24 = importlib.import_module('c1_tutorial24'); lane = importlib.import_module('c1_lane'); qual = importlib.import_module('qual_lib')
P = lambda i: f'Movies/20170629_{i:05d}_frameImage.mrc'


def report(prods=(), status=None, **kw):
    prods = list(prods); status = status or ('FAIL' if prods else 'PASS')
    side = {'movie_count': 24, 'mrc_count': 24, 'star_count': 24}
    r = {'status': status, 'base': side, 'candidate': side, 'different_files': prods, 'different_products': prods,
         'comparison_scope': 'products', 'mrc_sha256': {P(i): {} for i in range(24)}}
    r.update(kw); return r


class Classify(unittest.TestCase):
    man = {'movies': MOVIES, 'joint_star': 'corrected_micrographs.star'}

    def test_valid_pass_and_numeric_difference_are_preserved(self):
        self.assertEqual(t24.classify(0, report(), self.man)['state'], 'IDENTICAL')
        c = t24.classify(1, report([P(3), P(1)]), self.man)
        self.assertEqual((c['state'], c['products']), ('DIFFERENT', [P(1), P(3)]))

    def test_invalid_reports_are_never_identity_or_difference(self):
        bad = {
            'reason error': (1, {'status': 'FAIL', 'reason': 'candidate has missing STAR'}),
            'no report': (1, None), 'rc 2': (2, report()), 'rc 0 but FAIL': (0, report([P(1)])), 'rc 1 but PASS': (1, report()),
            'bad status': (1, report([P(1)], status='MAYBE')), 'fewer movies': (1, report([P(1)], base={'movie_count': 23, 'mrc_count': 23, 'star_count': 23})),
            'wrong scope': (1, report([P(1)], comparison_scope='complete non-PDF tree')),
            'duplicate product': (1, report([P(1), P(1)])), 'foreign product': (1, report(['Movies/other.mrc'])),
            'products not in files': (1, report([P(1)], different_files=[P(2)])),
            'products not list': (1, report([P(1)], different_products='Movies/x.mrc')),
            'missing mrc map': (1, report([P(1)], mrc_sha256={})), 'PASS lists differences': (0, report([P(1)], status='PASS')),
        }
        for name, (rc, rep) in bad.items():
            with self.subTest(name):
                self.assertEqual(t24.classify(rc, rep, self.man)['state'], 'INVALID')


class Attribution(unittest.TestCase):
    def setUp(self):
        (t24.T24 / 'compare').mkdir(parents=True, exist_ok=True)
        for f in (t24.T24 / 'compare').glob('*'): f.unlink()

    def put(self, label, state, products=(), reasons=()):
        (t24.T24 / 'compare' / f'{label}.class.json').write_text(json.dumps({'state': state, 'products': list(products), 'reasons': list(reasons)}))

    def arms(self, f_c1, f_arm, arm_c1):
        self.put('F-fresh_vs_c1-G', 'DIFFERENT' if f_c1 else 'IDENTICAL', f_c1)
        self.put('F-fresh_vs_F-retained-G', 'IDENTICAL')
        for a in ('N', 'only254', 'only260', 'only270'):
            self.put(f'F-fresh_vs_{a}-G', 'DIFFERENT' if f_arm.get(a) else 'IDENTICAL', f_arm.get(a, []))
            self.put(f'{a}_vs_c1-G', 'DIFFERENT' if arm_c1.get(a) else 'IDENTICAL', arm_c1.get(a, []))

    def test_parent_scenarios_all_arms_invalid_do_not_reproduce(self):
        self.put('F-fresh_vs_c1-G', 'DIFFERENT', [P(1)])
        for a in ('N', 'only254', 'only260', 'only270'):
            self.put(f'F-fresh_vs_{a}-G', 'INVALID', reasons=['candidate has missing STAR']); self.put(f'{a}_vs_c1-G', 'INVALID', reasons=['truncated'])
        r = t24.attribute('G'); self.assertEqual(r['status'], 'INVALID'); self.assertNotIn('product_attribution', r)
        self.put('F-fresh_vs_c1-G', 'INVALID', reasons=['C1 tree is truncated'])
        r = t24.attribute('G'); self.assertEqual(r['status'], 'INVALID'); self.assertTrue(r['problems'])

    def test_missing_files_are_invalid(self):
        self.assertEqual(t24.attribute('G')['status'], 'INVALID')

    def test_single_fix_combined_and_unattributed_are_distinguished(self):
        self.arms([P(1), P(2), P(3)],
                  {'N': [P(1), P(2)], 'only254': [P(1)], 'only260': [P(2)], 'only270': []},
                  {'N': [P(3)], 'only254': [P(2), P(3)], 'only260': [P(1), P(3)], 'only270': [P(1), P(2), P(3)]})
        r = t24.attribute('G'); a = r['product_attribution']
        self.assertEqual(r['status'], 'COMPLETE')
        self.assertTrue(a[P(1)]['classification'].startswith('SINGLE_FIX_REPRODUCES:only254'))
        self.assertTrue(a[P(2)]['classification'].startswith('SINGLE_FIX_REPRODUCES:only260'))
        self.assertTrue(a[P(3)]['classification'].startswith('UNATTRIBUTED'))
        self.assertTrue(any(P(3) in b for b in r['blockers']) and r['N_vs_C1_unexpected_changes'] == [P(3)])

    def test_n_only_reproduction_is_labelled_combined_not_unique(self):
        self.arms([P(5)], {'N': [P(5)], 'only254': [P(5)], 'only260': [], 'only270': []},
                  {'N': [], 'only254': [P(5)], 'only260': [P(5)], 'only270': [P(5)]})
        r = t24.attribute('G'); c = r['product_attribution'][P(5)]['classification']
        self.assertTrue(c.startswith('COMBINED_NUMERICS_COMPOSITION_ONLY'), c); self.assertEqual(r['blockers'], [])
        self.assertIn('not attribution to an individual fix', r['note'])

    def test_transitivity_inconsistency_is_a_blocker(self):
        self.arms([P(7)], {'N': [P(7)], 'only254': [], 'only260': [], 'only270': []}, {'N': [], 'only254': [], 'only260': [P(7)], 'only270': [P(7)]})
        r = t24.attribute('G'); self.assertTrue(any('inconsistency' in b for b in r['blockers']))


class LaneRunner(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp(dir=TMP)); (self.d / 'bin').mkdir()
        lane.TIME_PREFIX = lambda p: []
        lane.TASKSET = str(self.d / 'bin/taskset'); self.sh('bin/taskset', '#!/bin/sh\nshift 2\nexec "$@"\n')
        self.sh('bin/health', '#!/bin/sh\ncase "$1" in *-post) exit ${MOCK_POST:-0};; *) exit ${MOCK_PRE:-0};; esac\n')
        lane.HEALTH_CMD = [str(self.d / 'bin/health')]
        self.sh('bin/nvidia-smi', '#!/bin/sh\n[ -n "$MOCK_FOREIGN" ] && echo "GPU-test, 4242, 100"\nexit 0\n')
        self.marker = self.d / 'launched'; self.sh('bin/child', f'#!/bin/sh\necho x >> {self.marker}\nexit ${{MOCK_CHILD:-0}}\n')
        os.environ['PATH'] = f"{self.d / 'bin'}{os.pathsep}{os.environ['PATH'].split(os.pathsep, 1)[-1] if str(self.d) in os.environ['PATH'] else os.environ['PATH']}"
        pathlib.Path(os.environ['QF_GPU_LOCK']).touch()

    def sh(self, name, body):
        p = self.d / name; p.write_text(body); p.chmod(p.stat().st_mode | stat.S_IXUSR)

    def run_(self, **env):
        for k in ('MOCK_POST', 'MOCK_PRE', 'MOCK_FOREIGN', 'MOCK_CHILD'): os.environ.pop(k, None)
        os.environ.update(env)
        return lane.run_case_nb('t', self.d / 'bin/child', [], self.d, self.d / 'logs', True)

    def test_healthy_run_launches_once(self):
        r = self.run_(); self.assertEqual(r['rc'], 0); self.assertEqual(self.marker.read_text().count('x'), 1)
        self.assertEqual((r['health_pre']['rc'], r['health_post']['rc']), (0, 0))

    def test_lease_contention_stops_before_launch_and_uses_nonblocking(self):
        calls = []; real = lane.fcntl.flock
        def spy(fd, op): calls.append(op); return real(fd, op)
        lane.fcntl.flock = spy
        fd = os.open(os.environ['QF_GPU_LOCK'], os.O_RDWR); real(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            r = self.run_()
        finally:
            lane.fcntl.flock = real; real(fd, fcntl.LOCK_UN); os.close(fd)
        self.assertIsNone(r['rc']); self.assertIn('contended', r['error']); self.assertFalse(self.marker.exists())
        self.assertTrue(calls[0] & fcntl.LOCK_NB and calls[0] & fcntl.LOCK_EX, calls)

    def test_foreign_occupant_stops_before_launch(self):
        r = self.run_(MOCK_FOREIGN='1'); self.assertIsNone(r['rc']); self.assertIn('foreign', r['error']); self.assertFalse(self.marker.exists())

    def test_pre_health_failure_stops_before_launch(self):
        r = self.run_(MOCK_PRE='6'); self.assertIsNone(r['rc']); self.assertIn('pre-run', r['error']); self.assertFalse(self.marker.exists())

    def test_post_health_failure_after_successful_child_is_rc37_with_lease_held(self):
        seen = []
        def post_with_lock(label):
            fd = os.open(os.environ['QF_GPU_LOCK'], os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); seen.append('lease NOT held during health check')
            except BlockingIOError:
                seen.append('held')
            finally: os.close(fd)
            return (6, 'x') if label.endswith('-post') else (0, 'ok')
        real = lane.health; lane.health = post_with_lock
        try: r = self.run_()
        finally: lane.health = real
        self.assertEqual((r['rc'], r['child_rc']), (37, 0)); self.assertEqual(seen, ['held', 'held'])
        r2 = self.run_(MOCK_POST='6', MOCK_CHILD='3'); self.assertEqual((r2['rc'], r2['child_rc']), (3, 3))   # an existing failure is not masked


if __name__ == '__main__':
    unittest.main(verbosity=2)
