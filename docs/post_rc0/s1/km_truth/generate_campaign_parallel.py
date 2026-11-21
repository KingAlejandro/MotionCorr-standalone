#!/usr/bin/env python3
"""Four independent counting generators in one eight-core affinity; retain every seed."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time
ROOT=Path('/home/ubuntu/mc-km-truth-20261021')
sys.path[:0]=[str(ROOT/'v2/test-data'),str(ROOT/'deps')]
import generate_realistic_motion as gen
CONDITIONS=['dose1','dose05','dose2','dose4','outmodel','nonsquare','pedestal0','pedestal32','contrast025','contrast4']


def headroom():
    with (ROOT/'generation-cleanup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for movie in (ROOT/'fixtures').glob('*/movie.mrcs'):
            if (movie.parent/'GPU_COPY_VERIFIED.json').exists() and (ROOT/'results'/movie.parent.name/'cpu.done.json').exists():
                receipt=json.loads((movie.parent/'RECEIPT.json').read_text())
                if gen.digest(movie)!=receipt['files']['movie.mrcs']: raise ValueError('changed duplicate')
                movie.unlink()  # retained, hash-verified original is on 4GPUs
        return shutil.disk_usage(ROOT).free>48*(1<<30)


def one(item):
    condition,seed,expect=item
    name=f'{condition}-s{seed:02d}';out=ROOT/'fixtures'/name
    if (out/'RECEIPT.json').exists(): return name,'retained'
    while not headroom(): time.sleep(10)
    start=time.time();gen.generate(gen.recipe(condition,seed),Path(expect),out)
    return name,time.time()-start


def main():
    os.chdir(ROOT)
    for c in CONDITIONS:
        r=gen.recipe(c)
        key='outmodel' if c=='outmodel' else ('nonsquare' if c=='nonsquare' else 'inmodel')
        expect=ROOT/'expectations'/(key+'.npy')
        if not expect.with_suffix('.json').exists():
            if expect.exists(): raise RuntimeError('partial expectation remains')
            proof=gen.expected(r,expect)
            expect.with_suffix('.json').write_text(json.dumps(dict(recipe=r,proof=proof),indent=2)+'\n')
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            for name,seconds in pool.map(one,[(c,s,str(expect)) for s in range(10)]):
                print(name,seconds,flush=True)
    (ROOT/'generation.done').write_text('100 fixtures generated\n')

if __name__=='__main__': main()
