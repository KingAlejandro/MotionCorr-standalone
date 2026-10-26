#!/usr/bin/env python3
"""One bounded phase; refuses output reuse and never kills child processes."""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, subprocess, time
R=pathlib.Path('/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026')
UUID='GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8388608),b''): h.update(b)
 return h.hexdigest()
def cmd(args): return subprocess.check_output(args,text=True)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
p=argparse.ArgumentParser();p.add_argument('phase',choices=['baseline','off','off-v2','capture']);a=p.parse_args()
locks=[]
for path in ['/tmp/motioncorr-cuda-boundary-cpu80-87.lock','/tmp/motioncorr-gpu2-correctness.lock']:
 f=open(path,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
# Exclude active benchmark, without retaining its lease.
with open('/tmp/motioncorr-bench.lock','a') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert set(os.sched_getaffinity(0))==set(range(80,88))
assert not cmd(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader']).strip(), 'foreign GPU compute present'
phase=R/a.phase;phase.mkdir(exist_ok=False)
(phase/'gpu-pre.txt').write_text(cmd(['nvidia-smi','-q']))
(phase/'affinity-pre.txt').write_text(cmd(['ps','-eLo','pid,tid,psr,pcpu,comm']))
for case in ['00021','00046']:
 for layout in (['G'] if a.phase=='capture' else ['G','L']):
  for backend in ['cpu','cuda']:
   label=f'{case}-{layout}-{backend}';d=phase/label;d.mkdir()
   binary=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr') if a.phase=='baseline' else R/'build2/motioncorr'
   args=[str(binary),'--i','movies.star','--o',str(d/'out')+'/', '--j','8','--use_own','--dose_weighting','--dose_per_frame','1.277','--bfactor','150','--seed','1','--expected_frames','24','--gainref','Movies/gain.mrc','--ingest','float']
   if layout=='L': args+=['--patch_x','5','--patch_y','5']
   if backend=='cuda':args+=['--gpu','0','--ingest_witness',str(d/'ingest.txt')]
   env=os.environ.copy();env.pop('MC_BOUNDARY_DIR',None)
   env.update(CUDA_VISIBLE_DEVICES=UUID if backend=='cuda' else '',CUDA_DEVICE_ORDER='PCI_BUS_ID',OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='1',LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64')
   if a.phase=='capture':(d/'capture').mkdir();env['MC_BOUNDARY_DIR']=str(d/'capture')
   rec={'start':now(),'binary':str(binary),'binary_sha256':sha(binary),'args':args,'cwd':str(R/case),'affinity':sorted(os.sched_getaffinity(0)),'env':{k:env.get(k) for k in ['CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH','MC_BOUNDARY_DIR']},'star_sha256':sha(R/case/'movies.star'),'hook_source':'7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd','device_samples':[]}
   (d/'START.json').write_text(json.dumps(rec,indent=2)+'\n')
   with open(d/'stdout.txt','w') as out,open(d/'time.txt','w') as err:
    child=subprocess.Popen(['/usr/bin/time','-v']+args,cwd=R/case,env=env,stdout=out,stderr=err)
    while child.poll() is None:
     smi=cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader'])
     if smi.strip():rec['device_samples'].append({'utc':now(),'smi':smi})
     time.sleep(.25)
    rec.update(rc=child.returncode,end=now())
   rec['hashes']={str(x.relative_to(d)):{'bytes':x.stat().st_size,'sha256':sha(x)} for x in d.rglob('*') if x.is_file() and x.name!='START.json'}
   (d/'RUN.json').write_text(json.dumps(rec,indent=2)+'\n')
   print(label,rec['rc'],flush=True)
   if rec['rc']!=0: raise SystemExit(rec['rc'])
(phase/'gpu-post.txt').write_text(cmd(['nvidia-smi','-q']))
(phase/'COMPLETE').write_text(now()+'\n')
