#!/usr/bin/env python3
"""One #269 movie with the census command line and NO MC_DIAG_* variables (toggle-off control).

usage: control_movie.py FIXTURE_DIR OUTDIR BINARY CPUS [GPU_UUID]
"""
import json, os, pathlib, subprocess, sys, time
fixture=pathlib.Path(sys.argv[1]).resolve(); out=pathlib.Path(sys.argv[2]).resolve(); binary=pathlib.Path(sys.argv[3]).resolve(); cpus=sys.argv[4]; uuid=sys.argv[5] if len(sys.argv)>5 else None
r=json.loads((fixture/'RECEIPT.json').read_text()); out.mkdir(parents=True)
env={k:v for k,v in os.environ.items() if not k.startswith('MC_DIAG_')}; env['OMP_NUM_THREADS']='8'; env['OPENBLAS_NUM_THREADS']='1'
cmd=['taskset','-c',cpus,str(binary),'--i','input.star','--o',str(out/'output'),'--use_own','--j','8','--patch_x','5','--patch_y','5','--group_frames','1','--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum',str(r['recipe']['frames']),'--skip_logfile','--ingest','float','--ingest_witness',str(out/'ingest.txt')]
if uuid: env['CUDA_VISIBLE_DEVICES']=uuid; cmd+=['--gpu','0']
t=time.time()
with (out/'stdout.log').open('w') as log: rc=subprocess.run(cmd,cwd=fixture,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
(out/'RUN.json').write_text(json.dumps(dict(argv=cmd,exit=rc,seconds=time.time()-t,gpu_uuid=uuid),indent=2)+'\n'); print('exit',rc)
