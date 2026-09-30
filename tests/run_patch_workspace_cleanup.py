#!/usr/bin/env python3
"""Exercise checked movie-workspace cleanup in the real runner, before publication.
Returned CUDA codes are interposed after a successful real free; no GPU is poisoned.
"""
import argparse,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--workdir',type=Path,required=True);p.add_argument('--mutant-binary',type=Path);a=p.parse_args()
a.workdir.mkdir(parents=True,exist_ok=False)
records=[]
for mode in ('recoverable','fatal'):
 out=a.workdir/mode;out.mkdir()
 cmd=[str(a.binary.resolve()),'--i','movies.star','--o',str(out.resolve())+'/', '--use_own','--dose_weighting','--dose_per_frame','1.277','--patch_x','5','--patch_y','5','--bfactor','150','--gainref','Movies/gain.mrc','--seed','1','--gpu','0','--j','6','--max_io_threads','6','--ingest','nvcomp']
 env=dict(os.environ,MC_WORKSPACE_CLEANUP_FAULT=mode)
 r=subprocess.run(cmd,cwd=a.input_dir,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
 (a.workdir/(mode+'.log')).write_text(r.stdout)
 assert '[workspacefault] after real movie-workspace cudaFree:' in r.stdout, 'fault did not reach actual workspace release'
 assert 'workspace cleanup failed before reconstruction' in r.stdout, 'missing actual runner refusal'
 assert r.returncode!=0, 'cleanup failure published success'
 assert not list(out.rglob('*.mrc')) and not list(out.rglob('*.star')), 'failed movie published products'
 assert 'remaining-owned=0 stale-releases=0' in r.stdout, 'owned allocation cleanup incomplete'
 records.append({'case':mode,'returncode':r.returncode,'publication':'refused','owned_cleanup':'PASS','scope':'returned-code injection, not physical poisoning'})
if a.mutant_binary:
 out=a.workdir/'mutant';out.mkdir();cmd[0]=str(a.mutant_binary.resolve());cmd[cmd.index('--o')+1]=str(out.resolve())+'/'
 r=subprocess.run(cmd,cwd=a.input_dir,env=dict(os.environ,MC_WORKSPACE_CLEANUP_FAULT='recoverable'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
 (a.workdir/'mutant.log').write_text(r.stdout)
 assert '[workspacefault]' in r.stdout, 'negative control injection missing'
 assert r.returncode==0 and list(out.rglob('*.mrc')) and list(out.rglob('*micrographs.star')), 'negative control did not discriminate removed checked-release gate'
 records.append({'case':'ignored-recoverable-cleanup-mutant','rejected_by_original_gate':True})
(a.workdir/'result.json').write_text(json.dumps(records,indent=2));print('WORKSPACE_CLEANUP_PASS')
