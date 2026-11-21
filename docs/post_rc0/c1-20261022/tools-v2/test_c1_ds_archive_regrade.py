#!/usr/bin/env python3
"""Harmless synthetic controls for c1_ds_archive_regrade.py (24 tiny float32 MRCs, no GPU, no native run).

usage: C1_TEST_REPO=<exact checkout> <python with numpy> test_c1_ds_archive_regrade.py
Each case builds a fresh one-worker dataset arm laid out as run_dataset.py/merge_workers.py leave it, then mutates one thing.
BASE control: the unmodified comparator CLI on the same merged tree reports INVALID (the observed i6 failure); the regrader passes it.
"""
import hashlib, json, os, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get('C1_TEST_REPO', HERE.parents[3]))
TOOLS = REPO / 'docs/post_rc0/c1-20261022/tools-v2'
REGRADE = HERE / 'c1_ds_archive_regrade.py'
CMP = REPO / 'docs/issue85_laneC/compare_output_trees.py'
N = 24
MOVIES = [f'Movies/20170629_{i:05d}_frameImage.tiff' for i in range(N)]
STEMS = [Path(m).stem for m in MOVIES]
SHA = lambda b: hashlib.sha256(b).hexdigest()


def mrc(seed, shape=(2, 2, 1), mode=2):
    nx, ny, nz = shape
    h = bytearray(1024)
    struct.pack_into('<4i', h, 0, nx, ny, nz, mode)
    struct.pack_into('<3i', h, 64, 1, 2, 3)
    struct.pack_into('<3f', h, 76, 0.0, 10.0, 5.0)
    h[208:212] = b'MAP '; h[212:214] = b'DA'
    struct.pack_into('<f', h, 216, 1.0)
    struct.pack_into('<i', h, 220, 0)
    return bytes(h) + b''.join(struct.pack('<f', seed + 0.25 * j) for j in range(nx * ny * nz))


def movie_star(movie, root):
    return f'data_general\n\n_rlnImageSizeX 2\n_rlnMicrographMovieName {movie}\n_rlnMicrographName {root}/Movies/{Path(movie).stem}.mrc\n'


def joint_star(root):
    rows = ''.join(f'{root}/Movies/{s}.mrc {root}/Movies/{s}.star\n' for s in STEMS)
    return f'data_micrographs\n\nloop_\n_rlnMicrographName #1\n_rlnMicrographMetadata #2\n{rows}'


def write_products(root, files, tag):
    (root / 'Movies').mkdir(parents=True, exist_ok=True)
    for i, (m, s) in enumerate(zip(MOVIES, STEMS)):
        files[f'Movies/{s}.mrc'] = mrc(i)
        files[f'Movies/{s}.star'] = movie_star(m, root).encode()
        files[f'Movies/{s}.log'] = f'log {s} {tag}\n'.encode()
        files[f'Movies/{s}_shifts.eps'] = b'%!PS eps\n'
    files['corrected_micrographs.star'] = joint_star(root).encode()


def dump(root, files):
    for rel, b in files.items():
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)


class Case:
    """arm = T24/c1-ds-G with out/{workers/w0, merged, ...}; base = T24/c1-G/out."""

    def __init__(self, tmp):
        self.tmp = tmp; self.scr = tmp / 'scr'; self.t24 = self.scr / 't24'; self.arm = self.t24 / 'c1-ds-G'; self.out = self.arm / 'out'
        self.base = self.t24 / 'c1-G/out'; self.merged = self.out / 'merged'; self.wdir = self.out / 'workers/w0'
        self.frozen = tmp / 'frozen'; self.data = tmp / 'data'; self.scr.mkdir(); os.symlink(REPO, self.scr / 'src')
        (self.frozen / 'multigpu/G').mkdir(parents=True); (self.frozen / 'multigpu/L').mkdir(parents=True); self.data.mkdir()
        (self.data / 'movies.star').write_text('x')
        man = {'movies': MOVIES, 'joint_star': 'corrected_micrographs.star', 'expected_shape_xyz': [2, 2, 1]}
        for c in 'GL': (self.frozen / f'multigpu/{c}/manifest.json').write_text(json.dumps(man))
        # standalone arm
        bf = {}; write_products(self.base, bf, 'base'); dump(self.base, bf)
        # worker w0: products + the worker aggregates the launcher/binary leave
        wf = {}; write_products(self.wdir, wf, 'w0')
        wf['command.json'] = b'{"cmd": []}\n'; wf['launcher.console.log'] = b'console\n'
        dump(self.wdir, wf); self.wfiles = wf
        # merged = hardlink-equivalent copies of the worker products + the aggregate STAR the binary writes + provenance archive
        mf = {}; write_products(self.merged, mf, 'w0')
        mf = {k: v for k, v in mf.items() if k != 'corrected_micrographs.star'}
        mf['corrected_micrographs.star'] = joint_star(self.merged).encode(); mf['logfile.pdf'] = b'%PDF-1.4\n%%EOF\n'
        for n in ('command.json', 'corrected_micrographs.star', 'launcher.console.log'): mf[f'_workers/w0/{n}'] = wf[n]
        mf['_workers/merge.log'] = b'{"verdict": "PASS"}\n'
        dump(self.merged, mf)
        sm = {'canonical_movies': MOVIES, 'shards': [{'index': 0, 'movies': MOVIES}], 'input_sha256': 'f' * 64}
        smp = self.out / 'workers/shards/shard_manifest.json'; smp.parent.mkdir(parents=True, exist_ok=True); smp.write_text(json.dumps(sm))
        outs = {rel: {'sha256': SHA(b), 'key': [1, 2, len(b), 3, 4]} for rel, b in wf.items() if rel not in ('command.json', 'launcher.console.log')}
        self.put('workers/status.json', {'verdict': 'PASS', 'n_workers': 1, 'manifest': str(smp), 'manifest_sha256': SHA(smp.read_bytes()),
                                         'workers': [{'index': 0, 'returncode': 0, 'exit_digest': {'status': 'complete', 'outputs': outs}}]})
        self.put('dataset_status.json', {'verdict': 'PASS', 'dataset_ready': True, 'workers_complete': True})
        self.put('aggregate.json', {'verdict': 'PASS', 'dataset_ready': True, 'n_movies_expected': N, 'merged_into': str(self.merged),
                                    'per_worker_aggregates_preserved': ['_workers/w0/command.json', '_workers/w0/corrected_micrographs.star', '_workers/w0/launcher.console.log']})
        # the historical failing comparison, produced by the real comparator
        (self.t24 / 'compare').mkdir()
        rep = self.t24 / 'compare/c1-ds-G_vs_c1-standalone-G.json'
        self.cmp_cli = subprocess.run([sys.executable, '-I', str(CMP), str(self.base), str(self.merged), '--manifest', str(self.frozen / 'multigpu/G/manifest.json'),
                                       '--products-only', '--json-out', str(rep)], capture_output=True, text=True)
        (self.arm / 'DATASET.json').write_text(json.dumps({
            'arm': 'c1', 'cfg': 'G', 'verdict': 'FAIL', 'problems': ['products vs the standalone c1-G arm: INVALID'],
            'products_vs_standalone': {'state': 'INVALID', 'label': 'c1-ds-G_vs_c1-standalone-G', 'base': str(self.base), 'candidate': str(self.merged)}}))

    def put(self, rel, obj): (self.out / rel).write_text(json.dumps(obj))

    def jedit(self, rel, fn):
        p = self.out / rel; d = json.loads(p.read_text()); fn(d); p.write_text(json.dumps(d))

    def env(self):
        e = dict(os.environ)
        e.update(C1_SCR=str(self.scr), C1_TUTORIAL=str(self.data), C1_FROZEN_RC0=str(self.frozen), QF_W=str(self.scr), QF_CPUS='0', QF_GPU_UUID='GPU-test',
                 QF_GPU_LOCK=str(self.tmp / 'gpu.lock'), C1_GPU_UUID='GPU-test', C1_PY=sys.executable, C1_TOOLS=str(TOOLS))
        return e

    def run(self):
        r = subprocess.run([sys.executable, str(REGRADE), str(self.arm), '--out-dir', str(self.tmp / 'regrade')], capture_output=True, text=True, env=self.env(),
                           cwd=str(self.tmp))
        rp = self.tmp / 'regrade/REGRADE.json'
        return r, (json.loads(rp.read_text()) if rp.exists() else None)


class T(unittest.TestCase):
    def case(self):
        d = Path(tempfile.mkdtemp(prefix='mc-ds-regrade-')); self.addCleanup(shutil.rmtree, d, True); return Case(d)

    def expect(self, c, verdict, rc, needle=None):
        r, rec = c.run()
        self.assertIsNotNone(rec, r.stdout + r.stderr)
        self.assertEqual((rec['verdict'], r.returncode), (verdict, rc), json.dumps(rec['reasons']) + r.stderr)
        if needle: self.assertTrue(any(needle in x for x in rec['reasons']) or needle in json.dumps(rec['different_products']), (needle, rec['reasons']))
        return rec

    def test_base_unmodified_comparator_fails_on_archive_star_and_regrade_passes(self):
        c = self.case()
        self.assertEqual(c.cmp_cli.returncode, 1)
        self.assertIn("extra=['_workers/w0/corrected_micrographs.star']", c.cmp_cli.stderr)
        rec = self.expect(c, 'PASS', 0)
        self.assertEqual(len(rec['canonical_products']), 49)
        self.assertEqual(rec['comparator']['scope'], 'products'); self.assertTrue(rec['comparator']['archive_hidden_from_comparator'])
        self.assertEqual(rec['archive']['_workers/w0/corrected_micrographs.star']['archived_sha256'], rec['archive']['_workers/w0/corrected_micrographs.star']['worker_original_sha256'])
        self.assertTrue(any(r['path'] == '_workers/w0/corrected_micrographs.star' for r in rec['merged_inventory']))      # full inventory kept
        self.assertEqual(rec['historical']['verdict'], 'FAIL')
        self.assertEqual(json.loads((c.arm / 'DATASET.json').read_text())['verdict'], 'FAIL')      # historical result untouched

    def test_archive_negatives_are_invalid(self):
        cases = {
            'extra archived STAR': lambda c: (c.merged / '_workers/w0/extra.star').write_text('data_x\n'),
            'extra archived MRC': lambda c: (c.merged / '_workers/w0/gain.mrc').write_bytes(mrc(9)),
            'archived product duplicate': lambda c: ((c.merged / '_workers/w0/Movies').mkdir(), shutil.copy(c.merged / f'Movies/{STEMS[0]}.star', c.merged / f'_workers/w0/Movies/{STEMS[0]}.star')),
            'archive STAR content mismatch': lambda c: (c.merged / '_workers/w0/corrected_micrographs.star').write_bytes(b'data_micrographs\n'),
            'archive STAR missing': lambda c: (c.merged / '_workers/w0/corrected_micrographs.star').unlink(),
            'archive for a nonexistent worker': lambda c: ((c.merged / '_workers/w1').mkdir(), shutil.copy(c.merged / '_workers/w0/corrected_micrographs.star', c.merged / '_workers/w1/corrected_micrographs.star')),
            'unlisted non-STAR archive file': lambda c: (c.merged / '_workers/w0/junk.txt').write_text('x'),
            'archive symlink': lambda c: ((c.merged / '_workers/w0/launcher.console.log').unlink(), os.symlink(c.wdir / 'launcher.console.log', c.merged / '_workers/w0/launcher.console.log')),
            'command.json content mismatch': lambda c: (c.merged / '_workers/w0/command.json').write_text('{}'),
            'merge.log missing': lambda c: (c.merged / '_workers/merge.log').unlink(),
            'worker original changed after exit': lambda c: (c.wdir / 'corrected_micrographs.star').write_bytes(b'tampered'),
            'aggregate.json list differs': lambda c: c.jedit('aggregate.json', lambda d: d.update(per_worker_aggregates_preserved=['_workers/w0/corrected_micrographs.star'])),
            'archive STAR with no exit digest': lambda c: c.jedit('workers/status.json', lambda d: d['workers'][0]['exit_digest']['outputs'].pop('corrected_micrographs.star')),
            'other retained dataset problem': lambda c: (c.arm / 'DATASET.json').write_text(json.dumps({**json.loads((c.arm / 'DATASET.json').read_text()), 'problems': ['cleanup {}', 'products vs the standalone x']})),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                c = self.case(); mutate(c)
                self.expect(c, 'INVALID', 2)

    def test_product_negatives_are_not_hidden_by_the_archive_allowance(self):
        def pixel(c):
            p = c.merged / f'Movies/{STEMS[3]}.mrc'; b = bytearray(p.read_bytes()); b[-1] ^= 1; p.write_bytes(bytes(b))
        def header(c):
            p = c.merged / f'Movies/{STEMS[4]}.mrc'; b = bytearray(p.read_bytes()); b[100] ^= 1; p.write_bytes(bytes(b))
        def star(c):
            p = c.merged / f'Movies/{STEMS[5]}.star'; p.write_bytes(p.read_bytes() + b'_rlnX 1\n')
        def joint(c): (c.merged / 'corrected_micrographs.star').write_bytes((c.merged / 'corrected_micrographs.star').read_bytes() + b'#c\n')
        different = {'pixel': (pixel, 3, '.mrc'), 'header': (header, 4, '.mrc'), 'movie STAR': (star, 5, '.star'), 'joint STAR': (joint, None, 'corrected_micrographs.star')}
        for name, (mutate, i, tail) in different.items():
            with self.subTest(name):
                c = self.case(); mutate(c)
                rec = self.expect(c, 'FAIL', 1)
                self.assertEqual(len(rec['different_products']), 1); self.assertTrue(rec['different_products'][0].endswith(tail))
        invalid = {
            'extra STAR outside the archive': lambda c: (c.merged / 'Movies/extra.star').write_text('data_x\n'),
            'extra MRC outside the archive': lambda c: (c.merged / 'extra.mrc').write_bytes(mrc(9)),
            'wrong canonical path': lambda c: ((c.merged / 'Movies/sub').mkdir(), (c.merged / f'Movies/{STEMS[2]}.star').rename(c.merged / f'Movies/sub/{STEMS[2]}.star')),
            'missing product MRC': lambda c: (c.merged / f'Movies/{STEMS[6]}.mrc').unlink(),
            'unsupported MRC mode': lambda c: (c.merged / f'Movies/{STEMS[7]}.mrc').write_bytes(mrc(7, mode=1)),
            'wrong MRC dimensions': lambda c: (c.merged / f'Movies/{STEMS[8]}.mrc').write_bytes(mrc(8, shape=(2, 2, 2))),
            'product symlink': lambda c: ((c.merged / f'Movies/{STEMS[9]}.star').unlink(), os.symlink(c.base / f'Movies/{STEMS[9]}.star', c.merged / f'Movies/{STEMS[9]}.star')),
            'archive hidden only on the candidate': lambda c: ((c.base / '_workers/w0').mkdir(parents=True), (c.base / '_workers/w0/corrected_micrographs.star').write_text('data_x\n')),
        }
        for name, mutate in invalid.items():
            with self.subTest(name):
                c = self.case(); mutate(c); self.expect(c, 'INVALID', 2)

    def test_load_module_registers_before_exec_and_cleans_up(self):
        """v1.1 portability control: a file-loaded module whose body runs @dataclass over string annotations (as compare_output_trees.py does) must import.
        The v1 loader fails this on Python < 3.14 (AttributeError in dataclasses._is_type); 3.14+ defers annotations and cannot show it."""
        sys.path.insert(0, str(HERE)); import c1_ds_archive_regrade as m, importlib.util
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, True)
        good = d / 'dc_good.py'; good.write_text('from __future__ import annotations\nfrom dataclasses import dataclass\nfrom typing import Optional\n'
                                                 '@dataclass(frozen=True)\nclass Info:\n    n: int\n    later: Optional[Later] = None\nclass Later: pass\n')
        mod = m.load_module('dc_good_ro', good)
        self.assertEqual(mod.Info(3).n, 3); self.assertIs(sys.modules['dc_good_ro'], mod)
        bad = d / 'dc_bad.py'; bad.write_text('raise RuntimeError("boom")\n')
        with self.assertRaises(RuntimeError): m.load_module('dc_bad_ro', bad)
        self.assertNotIn('dc_bad_ro', sys.modules)                       # no half-initialised module left behind
        sentinel = object(); sys.modules['dc_bad_ro'] = sentinel
        with self.assertRaises(RuntimeError): m.load_module('dc_bad_ro', bad)
        self.assertIs(sys.modules['dc_bad_ro'], sentinel)               # a previous entry is restored
        del sys.modules['dc_bad_ro']
        retained_v1 = REPO / 'docs/post_rc0/c1-20261022/native-remaining-20261025/grader-review/c1_ds_archive_regrade.v1.py'
        v1 = importlib.util.spec_from_file_location('regrade_v1', retained_v1); v1m = importlib.util.module_from_spec(v1); v1.loader.exec_module(v1m)
        if sys.version_info < (3, 14):                                    # the control is capable of failing: the retained v1 loader does
            with self.assertRaises(AttributeError): v1m.load_module('dc_good_v1', good)
        self.assertEqual(m.VERSION, 'c1-ds-archive-regrade-v1.1')

    def test_rglob_patch_is_restored(self):
        sys.path.insert(0, str(HERE)); import c1_ds_archive_regrade as m, pathlib
        orig = pathlib.Path.rglob; d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, True)
        (d / '_workers').mkdir(); (d / '_workers/a.star').write_text(''); (d / 'b.star').write_text('')
        with m.hide_verified_archive(d):
            self.assertEqual([p.name for p in d.resolve().rglob('*.star')], ['b.star'])
            e = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, e, True); (e / '_workers').mkdir(); (e / '_workers/a.star').write_text('')
            self.assertEqual([p.name for p in e.resolve().rglob('*.star')], ['a.star'])      # another root is untouched
        self.assertIs(pathlib.Path.rglob, orig)


if __name__ == '__main__':
    unittest.main(verbosity=2)
