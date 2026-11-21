#!/usr/bin/env python3
"""Harmless host controls for the tools-v2 T24 comparison/attribution and GPU3 lane helpers (mock reports, mock programs; no device, no native run).

Covers the parent's findings: invalid comparator output must never read as identity or as an empty difference; a valid numeric difference must be
preserved; N-only reproduction is labelled as the combined composition; the lane runner stops on lease contention and on a foreign occupant before launch,
uses LOCK_NB, and propagates a failed post-run health check as rc 37 while the lease is still held.
usage: python3 test_c1_t24_failclosed.py
"""
import fcntl, importlib, importlib.util, json, os, pathlib, stat, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = pathlib.Path(os.environ['C1_TEST_REPO']) if os.environ.get('C1_TEST_REPO') else HERE.parents[3]      # remote runs point this at the exact checkout
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
    side = {'movie_count': 24, 'mrc_count': 24, 'star_count': 25}      # 24 per-movie STAR + the joint STAR, as the comparator reports
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
            'bad status': (1, report([P(1)], status='MAYBE')), 'fewer movies': (1, report([P(1)], base={'movie_count': 23, 'mrc_count': 23, 'star_count': 24})),
            'star count 24 (not n+1)': (1, report([P(1)], base={'movie_count': 24, 'mrc_count': 24, 'star_count': 24})),
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

    def put(self, label, state, products=(), reasons=(), base=None, cand=None, report=True):
        cfg = label[-1]; T = t24.T24.name
        def trees(lab):
            x, y = lab.rsplit('-', 1)[0].split('_vs_'); d = lambda a: f'/{T}/{a}-{cfg}/out'
            return (f'/multigpu/{cfg}/s0', d(x)) if y == 'F-retained' else (d(x), d(y))      # the lane control compares retained F (base) with F-fresh (candidate)
        b, c = trees(label)
        rep = t24.T24 / 'compare' / f'{label}.json'
        if report: rep.write_text(json.dumps({'stub': label}))
        import hashlib
        h = hashlib.sha256(rep.read_bytes()).hexdigest() if rep.exists() else None
        (t24.T24 / 'compare' / f'{label}.class.json').write_text(json.dumps({'state': state, 'products': list(products), 'reasons': list(reasons), 'label': label,
                                                                           'base': base or b, 'candidate': cand or c, 'report_sha256': h}))

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

    def test_lane_control_must_be_identical(self):
        self.arms([P(1)], {'N': [P(1)], 'only254': [P(1)], 'only260': [], 'only270': []}, {'N': [], 'only254': [], 'only260': [P(1)], 'only270': [P(1)]})
        self.assertEqual(t24.attribute_exit(t24.attribute('G')), 0)                      # healthy baseline for the cases below
        self.put('F-fresh_vs_F-retained-G', 'DIFFERENT', [P(9)])
        r = t24.attribute('G'); self.assertEqual(r['status'], 'COMPLETE')
        self.assertTrue(any('lane control' in b for b in r['blockers'])); self.assertEqual(t24.attribute_exit(r), 1)
        self.put('F-fresh_vs_F-retained-G', 'INVALID', reasons=['truncated'])
        r = t24.attribute('G'); self.assertEqual((r['status'], t24.attribute_exit(r)), ('INVALID', 2))
        (t24.T24 / 'compare' / 'F-fresh_vs_F-retained-G.class.json').unlink()
        r = t24.attribute('G'); self.assertEqual((r['status'], t24.attribute_exit(r)), ('INVALID', 2))

    def test_class_schema_and_bindings_are_validated(self):
        def fresh(): self.arms([P(1)], {'N': [P(1)], 'only254': [], 'only260': [], 'only270': []}, {'N': [], 'only254': [P(1)], 'only260': [P(1)], 'only270': [P(1)]})
        fresh(); self.assertEqual(t24.attribute('G')['status'], 'COMPLETE')
        for name, mutate in {
            'identical with products': lambda: self.put('N_vs_c1-G', 'IDENTICAL', [P(2)]),
            'different without products': lambda: self.put('N_vs_c1-G', 'DIFFERENT', []),
            'products duplicated': lambda: self.put('N_vs_c1-G', 'DIFFERENT', [P(2), P(2)]),
            'wrong base binding': lambda: self.put('N_vs_c1-G', 'IDENTICAL', base='/t24-i2/only254-G/out'),
            'wrong candidate binding': lambda: self.put('N_vs_c1-G', 'IDENTICAL', cand='/t24-i2/F-fresh-G/out'),
            'report missing': lambda: (t24.T24 / 'compare' / 'N_vs_c1-G.json').unlink(),
            'report changed after classification': lambda: (t24.T24 / 'compare' / 'N_vs_c1-G.json').write_text('{"tampered": 1}'),
            'products key absent': lambda: (t24.T24 / 'compare' / 'N_vs_c1-G.class.json').write_text(json.dumps({'state': 'DIFFERENT', 'label': 'N_vs_c1-G'})),
        }.items():
            with self.subTest(name):
                fresh(); mutate(); r = t24.attribute('G')
                self.assertEqual(r['status'], 'INVALID', (name, r)); self.assertEqual(t24.attribute_exit(r), 2)

    def test_transitivity_inconsistency_is_a_blocker(self):
        self.arms([P(7)], {'N': [P(7)], 'only254': [], 'only260': [], 'only270': []}, {'N': [], 'only254': [], 'only260': [P(7)], 'only270': [P(7)]})
        r = t24.attribute('G'); self.assertTrue(any('inconsistency' in b for b in r['blockers']))


class ActualCli(unittest.TestCase):
    """The actual `compare` wrapper against the actual comparator on tiny trees (tests/test_compare_output_trees.py builder; 24 movies of 4x3 pixels)."""
    @classmethod
    def setUpClass(cls):
        import struct
        spec = importlib.util.spec_from_file_location('tree_fixture', REPO / 'tests/test_compare_output_trees.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        cls.root = pathlib.Path(tempfile.mkdtemp(dir=TMP))
        b = m.TestOutputTreeComparator(); b.manifest = {'schema_version': 1, 'movies': [f'Movies/m{i:02}.tiff' for i in range(24)], 'expected_shape_xyz': [4, 3, 1],
                                                      'joint_star': 'corrected_micrographs.star'}
        for d in ('base', 'cand', 'cand_diff', 'cand_trunc'): b._write_tree(cls.root / d)
        p = cls.root / 'cand_diff/Movies/m00.mrc'; x = bytearray(p.read_bytes()); struct.pack_into('<f', x, 1032, 123.0); p.write_bytes(x)
        p = cls.root / 'cand_trunc/Movies/m00.mrc'; p.write_bytes(p.read_bytes()[:-4])
        (cls.root / 'scr').mkdir(); os.symlink(REPO, cls.root / 'scr/src'); (cls.root / 'frozen/multigpu/G').mkdir(parents=True); (cls.root / 'data').mkdir()
        (cls.root / 'data/movies.star').write_text('unused: this fixture manifest pins no input hash')
        (cls.root / 'manifest.json').write_text(json.dumps(b.manifest)); (cls.root / 'frozen/multigpu/G/manifest.json').write_text(json.dumps(b.manifest))
        cls.env = dict(os.environ, C1_SCR=str(cls.root / 'scr'), C1_TUTORIAL=str(cls.root / 'data'), C1_FROZEN_RC0=str(cls.root / 'frozen'), QF_W=str(cls.root / 'scr'),
                       QF_CPUS='0', QF_GPU_UUID='GPU-test', QF_GPU_LOCK=str(cls.root / 'gpu.lock'), OPENBLAS_NUM_THREADS='1')

    def cli(self, cand, label):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'c1_tutorial24.py'), 'compare', str(self.root / 'base'), str(self.root / cand), label],
                           env=self.env, capture_output=True, text=True)
        c = json.loads((self.root / 'scr/t24/compare' / f'{label}.class.json').read_text())
        return r, c

    def test_identical_different_invalid_through_the_real_wrapper_and_comparator(self):
        r, c = self.cli('cand', 'identical-G'); self.assertEqual((r.returncode, c['state']), (0, 'IDENTICAL'), r.stdout + r.stderr)
        r, c = self.cli('cand_diff', 'diff-G'); self.assertEqual((r.returncode, c['state'], c['products']), (1, 'DIFFERENT', ['Movies/m00.mrc']), r.stdout + r.stderr)
        r, c = self.cli('cand_trunc', 'trunc-G'); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'), r.stdout + r.stderr)
        run = json.loads((self.root / 'scr/t24/compare/diff-G.run.json').read_text())
        self.assertEqual(run['rc'], 1); self.assertTrue(run['report_sha256'] and run['comparator_sha256'] and run['cmd'])     # provenance retained

    def test_report_binding_survives_a_real_classification(self):
        self.cli('cand', 'bind-G'); c = json.loads((self.root / 'scr/t24/compare/bind-G.class.json').read_text())
        self.assertEqual(c['label'], 'bind-G'); self.assertTrue(c['base'].endswith('/base') and c['candidate'].endswith('/cand') and c['report_sha256'])


class LaneHashCli(unittest.TestCase):
    """lane-hash against a retained baseline that has hashes (comparator report) and STAR files but no MRC images, as the RC0 QF trees do."""
    @classmethod
    def setUpClass(cls):
        import shutil, struct
        spec = importlib.util.spec_from_file_location('tree_fixture2', REPO / 'tests/test_compare_output_trees.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        cls.root = r = pathlib.Path(tempfile.mkdtemp(dir=TMP)); cls.m = m
        b = m.TestOutputTreeComparator(); b.manifest = {'schema_version': 1, 'movies': [f'Movies/m{i:02}.tiff' for i in range(24)], 'expected_shape_xyz': [4, 3, 1],
                                                      'joint_star': 'corrected_micrographs.star'}
        cls.builder = b
        b._write_tree(r / 'orig'); b._write_tree(r / 'orig2')       # each tree is written natively: STAR paths must lie inside their own root
        (r / 'manifest.json').write_text(json.dumps(b.manifest))
        (r / 'scr').mkdir(); os.symlink(REPO, r / 'scr/src'); (r / 'frozen/multigpu/G').mkdir(parents=True); (r / 'data').mkdir()
        (r / 'data/movies.star').write_text('unused'); (r / 'frozen/multigpu/G/manifest.json').write_text(json.dumps(b.manifest))
        cls.env = dict(os.environ, C1_SCR=str(r / 'scr'), C1_TUTORIAL=str(r / 'data'), C1_FROZEN_RC0=str(r / 'frozen'), QF_W=str(r / 'scr'), QF_CPUS='0',
                       QF_GPU_UUID='GPU-test', QF_GPU_LOCK=str(r / 'gpu.lock'), OPENBLAS_NUM_THREADS='1')
        CMP = REPO / 'docs/issue85_laneC/compare_output_trees.py'
        subprocess.run([sys.executable, '-I', str(CMP), str(r / 'orig'), str(r / 'orig2'), '--manifest', str(r / 'manifest.json'), '--products-only', '--json-out', str(r / 'retained.json')], check=True,
                       capture_output=True)
        b._write_tree(r / 'retained_tree')                                      # retained baseline tree: STAR/eps/log only
        for p in list((r / 'retained_tree').rglob('*.mrc')) + list((r / 'retained_tree').rglob('*.pdf')): p.unlink()
        cls.struct, cls.shutil = struct, shutil

    def fresh(self, name, mutate=None):
        d = self.root / name; self.builder._write_tree(d)
        if mutate: mutate(d)
        return d

    def cli(self, fresh, label, retained_json=None, retained_tree=None):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'c1_tutorial24.py'), 'lane-hash', 'G', str(retained_tree or self.root / 'retained_tree'),
                            str(retained_json or self.root / 'retained.json'), str(fresh), label], env=self.env, capture_output=True, text=True)
        return r, json.loads((self.root / 'scr/t24/compare' / f'{label}.class.json').read_text())

    def test_identical_when_hashes_and_star_match_and_retained_has_no_mrc(self):
        self.assertEqual(len(list((self.root / 'retained_tree').rglob('*.mrc'))), 0)
        r, c = self.cli(self.fresh('f_ok'), 'lh-ok-G'); self.assertEqual((r.returncode, c['state']), (0, 'IDENTICAL'), r.stdout + r.stderr)

    def test_one_pixel_difference_is_different(self):
        def flip(d):
            p = d / 'Movies/m00.mrc'; b = bytearray(p.read_bytes()); self.struct.pack_into('<f', b, 1032, 123.0); p.write_bytes(b)
        r, c = self.cli(self.fresh('f_px', flip), 'lh-px-G'); self.assertEqual((r.returncode, c['state'], c['products']), (1, 'DIFFERENT', ['Movies/m00.mrc']), r.stdout + r.stderr)

    def test_star_difference_is_different(self):
        def edit(d):
            p = d / 'Movies/m01.star'; p.write_bytes(p.read_bytes() + b'# changed\n')
        r, c = self.cli(self.fresh('f_star', edit), 'lh-star-G'); self.assertEqual((r.returncode, c['state'], c['products']), (1, 'DIFFERENT', ['Movies/m01.star']), r.stdout + r.stderr)

    def test_invalid_inputs_are_invalid_never_identical(self):
        def trunc(d): p = d / 'Movies/m00.mrc'; p.write_bytes(p.read_bytes()[:-4])
        r, c = self.cli(self.fresh('f_tr', trunc), 'lh-trunc-G'); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'))
        def missing_star(d): (d / 'Movies/m02.star').unlink()
        r, c = self.cli(self.fresh('f_ms', missing_star), 'lh-ms-G'); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'))
        bad = json.loads((self.root / 'retained.json').read_text()); k = sorted(bad['mrc_sha256'])[0]
        for name, mutate in {'hash missing': lambda d: d['mrc_sha256'].pop(k), 'base != candidate': lambda d: d['mrc_sha256'][k].update(candidate_payload='0' * 64),
                             'malformed hash': lambda d: d['mrc_sha256'][k].update(base_payload='xyz', candidate_payload='xyz'), 'not a PASS': lambda d: d.update(status='FAIL')}.items():
            with self.subTest(name):
                d = json.loads((self.root / 'retained.json').read_text()); mutate(d); jp = self.root / f'ret-{name.replace(" ", "_").replace("!=", "ne")}.json'; jp.write_text(json.dumps(d))
                r, c = self.cli(self.fresh('f_' + jp.stem), 'lh-' + jp.stem + '-G', retained_json=jp); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'), c['reasons'])
        r, c = self.cli(self.fresh('f_nr'), 'lh-noretained-G', retained_json=self.root / 'does-not-exist.json'); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'))
        (self.root / 'rt2').mkdir(); r, c = self.cli(self.fresh('f_rt'), 'lh-notree-G', retained_tree=self.root / 'rt2'); self.assertEqual((r.returncode, c['state']), (2, 'INVALID'))

    def test_class_file_binds_to_attribute_expectations(self):
        r, c = self.cli(self.fresh('f_bind'), 'lh-bind-G')
        self.assertEqual((c['label'], c['base'], c['candidate'].endswith('f_bind')), ('lh-bind-G', str(self.root / 'retained_tree'), True))
        self.assertTrue(c['report_sha256'])


@unittest.skipUnless(sys.platform.startswith('linux'), 'process-group ownership needs /proc (Linux); run on 4GPUs')
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

    def own_pid_script(self, name, body):
        pid = self.d / f'{name}.pid'; self.sh(f'bin/{name}', f'#!/bin/sh\n{body.format(pid=pid)}\n'); return self.d / f'bin/{name}', pid

    @staticmethod
    def alive(pid):
        try: os.kill(pid, 0)
        except ProcessLookupError: return False
        try: return open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'
        except OSError: return os.path.exists(f'/proc/{pid}')

    def test_timeout_terminates_reaps_and_cleans_before_health_and_lease_release(self):
        child, pidf = self.own_pid_script('grand', 'sleep 120 &\necho $! > {pid}\nsleep 120')
        seen = []; real = lane.health
        def spy(label):
            if label.endswith('-post'): seen.append(self.alive(int(pidf.read_text())))      # descendant must already be gone
            return 0, 'ok'
        lane.health = spy
        try:
            r = lane.run_case_nb('t', child, [], self.d, self.d / 'logs', True, timeout=2)
        finally: lane.health = real
        gp = int(pidf.read_text())
        self.assertIsNone(r['rc']); self.assertIn('timeout', r['error']); self.assertIn('process group terminated', r['error'])
        self.assertIn(gp, r['cleanup']['members_before']); self.assertEqual(r['cleanup']['remaining'], [])
        self.assertFalse(self.alive(gp)); self.assertEqual(seen, [False])
        self.assertTrue(r['cleanup']['sigterm'])

    def test_descendant_outliving_a_successful_child_is_terminated_and_fails(self):
        child, pidf = self.own_pid_script('orphan', 'sleep 120 &\necho $! > {pid}\nexit 0')
        r = lane.run_case_nb('t', child, [], self.d, self.d / 'logs', True, timeout=20)
        gp = int(pidf.read_text()); self.assertEqual((r['rc'], r['child_rc']), (38, 0)); self.assertIn('outlived', r['error'])
        self.assertIn(gp, r['cleanup']['members_before']); self.assertFalse(self.alive(gp))

    def test_clean_child_reports_no_cleanup_needed(self):
        r = self.run_(); self.assertEqual(r['cleanup']['members_before'], []); self.assertEqual(r['rc'], 0)

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
