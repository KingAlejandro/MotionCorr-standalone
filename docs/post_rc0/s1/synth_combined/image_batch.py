#!/usr/bin/env python3
"""Batch driver for tools/check_realistic_image.py.

  image_batch.py eval     ROOT RESULTS_NAME [--workers N]   per-arm image metrics -> <arm>/image.json
  image_batch.py controls ROOT FIXTURE_NAME OUT.json        crop controls from one movie
  image_batch.py effect   ROOT RESULTS_A RESULTS_B OUT.json #270 effect: B (with) minus A (without), per movie
ROOT holds fixtures/<cond>-sNN (RECEIPT.json) and a truth cache truth-<nx>x<ny>.npy.
Run with -I-safe PYTHONPATH pointing at repo/tools and repo/test-data.
"""
import concurrent.futures, json, pathlib, sys
import numpy as np
REPO = pathlib.Path(__file__).resolve().parents[4]
if not (REPO/'tools').exists(): REPO = pathlib.Path(sys.argv[0]).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
import check_realistic_image as img
from motion_field import read_mrc


def recipe(root, name): return json.loads((root/'fixtures'/name/'RECEIPT.json').read_text())['recipe']


def truth(root, r):
    p = root/f"truth-{r['nx']}x{r['ny']}.npy"
    if p.exists(): return np.load(p)
    t = img.truth_scene(r); np.save(p.with_suffix('.tmp.npy'), t); p.with_suffix('.tmp.npy').rename(p); return t


def read_sum(path):
    a, _ = read_mrc(path); return a[0]


def one(args):
    root, run = args
    arm = run.parent; name = arm.parent.name; r = recipe(root, name); out = arm/'image.json'
    m = img.evaluate_sum(r, read_sum(arm/'output/movie.mrc'), truth(root, r))
    m['identity'] = dict(sum=str(arm.relative_to(root)/'output/movie.mrc'))
    out.write_text(json.dumps(m, indent=1, allow_nan=False)+'\n'); return str(arm)


def cmd_eval(root, results, workers=4):
    runs = sorted((root/results).glob('*/*/RUN.json'))
    for rn in runs:   # build truth caches serially before forking
        r = recipe(root, rn.parent.parent.name); truth(root, r)
    runs = [x for x in runs if not (x.parent/'image.json').exists() and json.loads(x.read_text())['exit'] == 0]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool: done = list(pool.map(one, [(root, x) for x in runs]))
    print('evaluated', len(done))


def cmd_controls(root, name, out):
    r = recipe(root, name); t = truth(root, r)
    res = img.evaluate_controls(r, root/'fixtures'/name/'movie.mrcs', t)
    pathlib.Path(out).write_text(json.dumps(dict(fixture=name, **res), indent=1, allow_nan=False)+'\n')


def cmd_effect(root, ra, rb, out):
    rows = []
    for rn in sorted((root/ra).glob('*/*/RUN.json')):
        arm = rn.parent; other = root/rb/arm.parent.name/arm.name
        if not (other/'output/movie.mrc').exists() or not (arm/'output/movie.mrc').exists(): continue
        name = arm.parent.name; r = recipe(root, name); t = truth(root, r)
        a, b = read_sum(arm/'output/movie.mrc'), read_sum(other/'output/movie.mrc')
        rows.append(dict(movie=name, arm=arm.name, bytes_identical=bool(np.array_equal(a, b)),
                         bins=img.paired_effect(r, a, b, t)))
    pathlib.Path(out).write_text(json.dumps(rows, indent=1, allow_nan=False)+'\n'); print('pairs', len(rows))


if __name__ == '__main__':
    c, root = sys.argv[1], pathlib.Path(sys.argv[2]).resolve()
    if c == 'eval': cmd_eval(root, sys.argv[3], int(sys.argv[5]) if len(sys.argv) > 5 else 4)
    elif c == 'controls': cmd_controls(root, sys.argv[3], sys.argv[4])
    elif c == 'effect': cmd_effect(root, sys.argv[3], sys.argv[4], sys.argv[5])
