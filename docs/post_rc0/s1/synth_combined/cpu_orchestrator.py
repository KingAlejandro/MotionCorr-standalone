#!/usr/bin/env python3
"""cpu64: stream verified fixtures from 4GPUs under a disk cap, run seed-0 image controls,
and drop a local movie only after its CPU arms and (seed 0) controls are done.
The originals on 4GPUs are never touched. Receipt appears last, so workers wait for it."""
import json, os, pathlib, shutil, subprocess, sys, time
ROOT = pathlib.Path('/home/ubuntu/mc-synth-combined'); FIX = ROOT/'fixtures'
CONDS = ['pedestal32', 'dose1', 'dose05', 'dose2', 'dose4', 'outmodel', 'nonsquare', 'pedestal0', 'contrast025', 'contrast4']
MAX_IN_FLIGHT = 10
ENV = dict(os.environ, PYTHONPATH='/home/ubuntu/mc-km-truth-20261021/deps', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='4')
names = [f'{c}-s{s:02d}' for c in CONDS for s in range(10)]


def resident(): return [n for n in names if (FIX/n/'movie.mrcs').exists()]


def done(n):
    ok = (ROOT/'results-comb'/n/'cpu.done.json').exists()
    if n.endswith('-s00'): ok = ok and (ROOT/'controls'/f'{n}.json').exists()
    return ok


def main():
    """Fixtures are pushed from 4GPUs (push_fixtures.sh); this only runs seed-0 controls and releases movies."""
    (ROOT/'controls').mkdir(exist_ok=True)
    penv = dict(ENV, PYTHONPATH=ENV['PYTHONPATH']+':'+str(ROOT/'repo/tools')+':'+str(ROOT/'repo/test-data'))
    while True:
        for n in names:
            if not (FIX/n/'RECEIPT.json').exists(): continue
            if n.endswith('-s00') and not (ROOT/'controls'/f'{n}.json').exists():
                p = subprocess.run(['python3', str(ROOT/'repo/tools/image_batch.py'), 'controls', str(ROOT), n, str(ROOT/'controls'/f'{n}.json')], env=penv)
                print('controls', n, p.returncode, flush=True)
                if p.returncode: (ROOT/'controls'/f'{n}.json').write_text(json.dumps(dict(error='controls failed', returncode=p.returncode)))
            if done(n) and (FIX/n/'movie.mrcs').exists():
                shutil.rmtree(FIX/n); print('released', n, flush=True)
        if all(done(n) for n in names) and not resident(): break
        time.sleep(20)
    print('all released', flush=True)

if __name__ == '__main__': main()
