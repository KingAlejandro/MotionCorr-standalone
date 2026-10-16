import fcntl,json,os,subprocess,time
from pathlib import Path
root=Path('/workspace/scratch/28038873ca11')
out=root/'stages-stream';out.mkdir(exist_ok=False)
env=dict(os.environ,OMP_NUM_THREADS='4',OMP_DYNAMIC='false',OMP_PROC_BIND='close',OMP_PLACES='cores',OPENBLAS_NUM_THREADS='1')
manifest={'scope':'one diagnostic profile per arm, not a replicated speed verdict','commands':[]}
with open('/tmp/motioncorr-bench.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 for arm,build in [('base','build-reference'),('candidate','build-stream')]:
  cmd=['taskset','-c','0-3',str(root/build/'motioncorr'),'--i',str(root/'data/tutorial.tiff'),'--o',str(out/arm),'--use_own','--j','4','--angpix','0.885','--voltage','300','--bfactor','150','--seed','1','--patch_x','5','--patch_y','5','--gainref',str(root/'data/gain.mrc'),'--dose_weighting','--dose_per_frame','1.277','--save_noDW','--even_odd_split','--profile',str(out/(arm+'.jsonl'))]
  with (out/(arm+'.log')).open('w') as log:rc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  manifest['commands'].append({'arm':arm,'command':cmd,'rc':rc})
  (out/'commands.json').write_text(json.dumps(manifest,indent=2)+'\n')
  if rc:raise SystemExit(rc)
