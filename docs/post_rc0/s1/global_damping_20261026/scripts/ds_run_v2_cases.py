#!/usr/bin/env python3
"""#267 eight-case native runs with the exact run_v2.py command line, plus a DC toggle.

usage: ds_run_v2_cases.py ROOT OUTNAME BACKEND BINARY DC CPUS "EXTRA ARGS" 
Derived from docs/post_rc0/c1-20261022/tools/c1_run_v2_cases.py (same command line, env and loop).
The only change: EXTRA ARGS (shell-split, may be empty) is appended to every case's command.
DS_ONLY_CASES (comma list, env, optional) restricts the loop to those cases (diagnostic single-case runs); unset runs all eight.
With EXTRA empty the argv is identical to the original driver's (checked by the retained diff).
Fixtures are read from ROOT/v2fixtures; outputs go to ROOT/OUTNAME. DC=unset leaves
every MC_DIAG_* variable absent (toggle-off control).
"""
import json, os, pathlib, subprocess, sys, time
root=pathlib.Path(sys.argv[1]).resolve(); outname=sys.argv[2]; backend=sys.argv[3]; binary=pathlib.Path(sys.argv[4]).resolve()
import shlex
dc=sys.argv[5]; cpus=sys.argv[6]; extra=shlex.split(sys.argv[7]); uuid=None
fixtures=root/'v2fixtures'; out=root/outname; out.mkdir(exist_ok=False)
rows=[]
for name in [c for c in ['zero','integer','fractional','affine','pedestal','noisy','flat','repeated'] if c in os.environ.get('DS_ONLY_CASES', c).split(',')]:
 p=3 if name in ['affine','pedestal','noisy'] else 1
 cmd=['taskset','-c',cpus,str(binary),'--i',name+'.star','--o',str(out/name),'--use_own','--j','2','--patch_x',str(p),'--patch_y',str(p),'--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','5','--skip_logfile']+extra
 env=os.environ.copy(); env['OMP_NUM_THREADS']='2'   # C1: 2-CPU lane
 for k in list(env):
  if k.startswith('MC_DIAG_'): del env[k]
 if dc!='unset':
  env['MC_DIAG_CCF_DC']=dc; env['MC_DIAG_CCF_DOUBLE']='0'; env['MC_DIAG_MODEL_OUT']=str(out/(name+'.runtime.json'))
 if backend=='cuda': cmd+=['--gpu','0']; env['CUDA_VISIBLE_DEVICES']=uuid
 start=time.time()
 with (out/(name+'.stdout')).open('w') as f: rc=subprocess.run(cmd,cwd=fixtures,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 rows.append(dict(case=name,backend=backend,dc=dc,patches=p,argv=cmd,exit=rc,seconds=time.time()-start,gpu_uuid=uuid,extra=extra))
 (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,rc,flush=True)
