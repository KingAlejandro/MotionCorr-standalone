#!/usr/bin/env python3
"""One native process/movie; bounded CPU slots and per-seed CUDA advisory locks.

Run on cpu64 with --backend cpu; on 4GPUs with --backend cuda. Generation and
fixture transfer are separate. A receipt is the ready marker. All exits persist.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

GPU_UUIDS=['GPU-eddb42fe-4f9a-adde-76d3-b924e14add54','GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d','GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598','GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d']
CONDITIONS=['dose1','dose05','dose2','dose4','outmodel','nonsquare','pedestal0','pedestal32','contrast025','contrast4']


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''): h.update(block)
    return h.hexdigest()


def lock_gpu():
    busy=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines()
    for i in [2,3,1,0]:
        if GPU_UUIDS[i] in busy: continue
        f=open(f'/tmp/motioncorr-gpu{i}-correctness.lock','a')
        try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: f.close(); continue
        return f,i,GPU_UUIDS[i]
    return None


def run_seed(args,fixture,out,device):
    r=json.loads((fixture/'RECEIPT.json').read_text())
    if digest(fixture/'movie.mrcs')!=r['files']['movie.mrcs']: raise ValueError('movie hash mismatch')
    arms=[(dc,False) for dc in args.dc_arms]
    if args.backend=='cpu' and (args.double_conditions is None or fixture.name.rsplit('-s',1)[0] in args.double_conditions): arms += [('none',True)]
    rows=[]
    for dc,double in arms:
        name=args.backend+'-'+('double' if double else dc)
        arm=out/name; arm.mkdir(exist_ok=False)
        env=os.environ.copy(); env['OMP_NUM_THREADS']='8'; env['OPENBLAS_NUM_THREADS']='1'
        env['MC_DIAG_CCF_DC']=dc; env['MC_DIAG_CCF_DOUBLE']='1' if double else '0'
        env['MC_DIAG_MODEL_OUT']=str(arm/'runtime.json')
        cmd=['taskset','-c',args.cpus,str(args.binary),'--i','input.star','--o',str(arm/'output'),'--use_own','--j','8',
             '--patch_x','5','--patch_y','5','--group_frames','1','--bin_factor','1','--seed','1','--skip_defect',
             '--save_noDW','--first_frame_sum','1','--last_frame_sum',str(r['recipe']['frames']),'--skip_logfile',
             '--ingest','float','--ingest_witness',str(arm/'ingest.txt')]
        if device is not None:
            env['CUDA_VISIBLE_DEVICES']=device[2]; cmd+=['--gpu','0']
        start=time.time()
        with (arm/'stdout.log').open('w') as log:
            proc=subprocess.run(cmd,cwd=fixture,env=env,stdout=log,stderr=subprocess.STDOUT)
        row=dict(arm=name,argv=cmd,exit=proc.returncode,seconds=time.time()-start,
                 env={k:v for k,v in env.items() if k.startswith(('MC_DIAG_','CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS'))},
                 gpu_uuid=device[2] if device else None,binary_sha256=args.binary_sha256,
                 input_receipt_sha256=digest(fixture/'RECEIPT.json'),movie_sha256=r['files']['movie.mrcs'])
        (arm/'RUN.json').write_text(json.dumps(row,indent=2)+'\n'); rows.append(row)
        print(f'{fixture.name} {name} exit={proc.returncode} seconds={row["seconds"]:.2f}',flush=True)
    (out/(args.backend+'.done.json')).write_text(json.dumps(rows,indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True); ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--backend',choices=['cpu','cuda'],required=True); ap.add_argument('--cpus',required=True)
    ap.add_argument('--max-idle-seconds',type=int,default=3600)
    # Defaults reproduce the 900-arm census; the synthetic-combined study narrows them.
    ap.add_argument('--dc-arms',nargs='+',default=['none','global','local','both'],choices=['none','global','local','both'])
    ap.add_argument('--double-conditions',nargs='*',default=None,help='CPU double-CCF arm only for these conditions (default: every condition)')
    ap.add_argument('--results',default='results'); ap.add_argument('--conditions',nargs='+',default=CONDITIONS)
    args=ap.parse_args(); args.root=args.root.resolve(); args.binary=args.binary.resolve()
    args.binary_sha256=digest(args.binary)
    results=args.root/args.results; results.mkdir(exist_ok=True)
    start_idle=time.time()
    while True:
        pending=False; found=False
        for c in args.conditions:
            for seed in range(10):
                name=f'{c}-s{seed:02d}'; fixture=args.root/'fixtures'/name
                out=results/name; out.mkdir(exist_ok=True)
                if (out/(args.backend+'.done.json')).exists(): continue
                pending=True
                if not (fixture/'RECEIPT.json').exists(): continue
                # Separate per-seed CPU ownership for multiple eight-core workers.
                guard=open(out/(args.backend+'.lock'),'a')
                try: fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError: guard.close(); continue
                if (out/(args.backend+'.done.json')).exists(): guard.close(); continue
                if any(out.glob(args.backend+'-*/RUN.json')):
                    guard.close(); raise RuntimeError(f'partial seed retained, explicit reconciliation required: {name}')
                device=lock_gpu() if args.backend=='cuda' else None
                if args.backend=='cuda' and device is None: guard.close(); continue
                try: run_seed(args,fixture,out,device)
                finally:
                    if device: device[0].close()
                    guard.close()
                found=True; start_idle=time.time(); break
            if found: break
        if not pending: return
        if not found:
            if time.time()-start_idle>args.max_idle_seconds: raise TimeoutError('fixture/resource wait expired; receipts retained')
            time.sleep(5)

if __name__=='__main__': main()
