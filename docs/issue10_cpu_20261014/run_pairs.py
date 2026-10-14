#!/usr/bin/env python3
"""Bounded CPU-only issue-10 experiment; run after builds/tests finish.
Inputs: tutorial.tiff, gain.mrc and generated synthetic_512x512_16frames.mrcs.
Preserves every output and profile; compares every MRC/STAR after each pair.
"""
import argparse, hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--base',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--repeats',type=int,default=3)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
repo=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('treecmp',repo/'docs/issue85_laneC/compare_output_trees.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def compare(x,y):
    left={p.relative_to(x):p for p in x.rglob('*') if p.suffix in ('.mrc','.star')}
    right={p.relative_to(y):p for p in y.rglob('*') if p.suffix in ('.mrc','.star')}
    assert left and left.keys()==right.keys(), 'missing product inventory'
    results=[]
    for rel,p in sorted(left.items()):
        q=right[rel];u=p.read_bytes();v=q.read_bytes()
        if p.suffix=='.mrc':
            import struct
            u=mod._normalised_header(u[:1024],struct.unpack_from('<i',u,220)[0])+u[1024:]
            v=mod._normalised_header(v[:1024],struct.unpack_from('<i',v,220)[0])+v[1024:]
        else:
            u=mod._normalise_text(p,x,u);v=mod._normalise_text(q,y,v)
        results.append({'file':str(rel),'equal':u==v,'base_sha256':hashlib.sha256(u).hexdigest(),'candidate_sha256':hashlib.sha256(v).hexdigest()})
    return results
manifest={'binaries':{k:{'path':str(getattr(a,k).resolve()),'sha256':digest(getattr(a,k))} for k in ('base','candidate')},'inputs':{p.name:digest(p) for p in a.data.iterdir() if p.suffix in ('.tiff','.mrc','.mrcs')},'runs':[],'comparisons':[]}
for data in ('synthetic','tutorial'):
 for mode in ('global','patch_all'):
  for j in (1,4):
   case=f'{data}-{mode}-j{j}'
   for rep in range(a.repeats):
    dirs={}
    for arm in (('base','candidate') if rep%2==0 else ('candidate','base')):
     stem=f'{case}-r{rep}-{arm}';out=a.out/stem;dirs[arm]=out
     movie=a.data/('tutorial.tiff' if data=='tutorial' else 'synthetic_512x512_16frames.mrcs')
     cmd=['taskset','-c','0' if j==1 else '0-3',str(getattr(a,arm).resolve()),'--i',str(movie.resolve()),'--o',str(out.resolve()),'--use_own','--j',str(j),'--angpix','0.885' if data=='tutorial' else '1.0','--voltage','300','--bfactor','150','--seed','1','--patch_x','1' if mode=='global' else '5','--patch_y','1' if mode=='global' else '5','--profile',str((a.out/(stem+'.jsonl')).resolve())]
     if data=='tutorial':cmd+=['--gainref',str((a.data/'gain.mrc').resolve())]
     if mode=='patch_all':cmd+=['--dose_weighting','--dose_per_frame','1.277','--save_noDW','--even_odd_split']
     env=dict(os.environ,OMP_NUM_THREADS=str(j),OMP_DYNAMIC='false',OMP_PROC_BIND='close',OMP_PLACES='cores',OPENBLAS_NUM_THREADS='1')
     with (a.out/(stem+'.log')).open('w') as log:
      r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
     assert r.returncode==0,(stem,r.returncode)
     profile=[json.loads(s) for s in (a.out/(stem+'.jsonl')).read_text().splitlines()]
     manifest['runs'].append({'case':case,'rep':rep,'arm':arm,'command':cmd,'environment':{k:env[k] for k in ('OMP_NUM_THREADS','OMP_DYNAMIC','OMP_PROC_BIND','OMP_PLACES','OPENBLAS_NUM_THREADS')},'profile':profile})
     (a.out/'results.json').write_text(json.dumps(manifest,indent=2))
     print(stem,profile[-1],flush=True)
    results=compare(dirs['base'],dirs['candidate'])
    manifest['comparisons'].append({'case':case,'rep':rep,'products':results})
    (a.out/'results.json').write_text(json.dumps(manifest,indent=2))
    assert all(r['equal'] for r in results),(case,rep,'product difference')
