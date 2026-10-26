#!/usr/bin/env python3
"""One bounded phase; refuses output reuse and never kills child processes."""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, subprocess, time, shutil
R=pathlib.Path('/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026')
UUID='GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8388608),b''): h.update(b)
 return h.hexdigest()
def cmd(args): return subprocess.check_output(args,text=True)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def affinity(pid):
 return sorted(os.sched_getaffinity(int(pid)))
def tree(pid):
 ids=[pid]
 try:
  for c in pathlib.Path(f'/proc/{pid}/task/{pid}/children').read_text().split():ids+=tree(int(c))
 except FileNotFoundError:pass
 return ids
def cpu_ticks():
 return {int(x[0][3:]):list(map(int,x[1:9])) for line in pathlib.Path('/proc/stat').read_text().splitlines() if (x:=line.split()) and x[0].startswith('cpu') and x[0][3:].isdigit() and int(x[0][3:]) in range(80,88)}
def admission(case,binary,expected_binary):
 before=cpu_ticks();time.sleep(.5);after=cpu_ticks()
 busy={c:1-(sum(after[c][3:5])-sum(before[c][3:5]))/max(1,sum(after[c])-sum(before[c])) for c in before}
 lease=json.loads(cmd(['lslocks','--json','-o','PID,COMMAND,PATH'])).get('locks',[])
 conflicts=[]
 for x in lease:
  if x['pid']==os.getpid() or not any(t in x.get('path','') for t in ['motioncorr','mc254']):continue
  try:mask=affinity(x['pid'])
  except ProcessLookupError:continue
  x['affinity']=mask
  if set(mask)&set(range(80,88)):conflicts.append(x)
 # Thread snapshot and CPU-load admission are separate from lease checks.
 processes=cmd(['ps','-eLo','pid,tid,psr,pcpu,comm'])
 compute_conflicts=[]
 for line in processes.splitlines()[1:]:
  fields=line.split()
  if len(fields)!=5:continue
  pid,tid,psr,pcpu,name=fields
  if any(t in name.lower() for t in ['motioncorr','llama','gromacs']):
   try:mask=affinity(tid)
   except ProcessLookupError:continue
   if set(mask)&set(range(80,88)):compute_conflicts.append({'thread':fields,'affinity':mask})
 scratch=int(cmd(['du','-sb',str(R)]).split()[0]);free=shutil.disk_usage(R).free
 frozen=json.loads((R/'inventory.json').read_text())
 checks={path:sha(path)==v['sha256'] for path,v in frozen['hashes'].items() if path.endswith('gain.mrc') or case in path}
 checks['star']=sha(R/case/'movies.star')==frozen['star_hashes'][case]
 checks['binary']=sha(binary)==expected_binary
 smi=cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader'])
 record={'utc':now(),'cpu_busy_fraction_half_second':busy,'lease_snapshot':lease,'overlap_lease_conflicts':conflicts,'compute_conflicts':compute_conflicts,'thread_snapshot':processes,'scratch_bytes':scratch,'scratch_cap_bytes':20*1024**3,'required_increment_headroom_bytes':1024**3,'free_bytes':free,'hash_checks':checks,'gpu_compute':smi,'parent_affinity':affinity(os.getpid())}
 record['admitted']=all(checks.values()) and not conflicts and not compute_conflicts and max(busy.values())<.2 and scratch+1024**3<=20*1024**3 and free>1024**3 and UUID not in smi and record['parent_affinity']==list(range(80,88))
 return record
p=argparse.ArgumentParser();p.add_argument('phase',choices=['baseline','off','off-v2','capture']);a=p.parse_args()
locks=[]
for path in ['/tmp/motioncorr-cuda-boundary-cpu80-87.lock','/tmp/motioncorr-gpu2-correctness.lock']:
 f=open(path,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
# Exclude active benchmark, without retaining its lease.
with open('/tmp/motioncorr-bench.lock','a') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert set(os.sched_getaffinity(0))==set(range(80,88))
assert UUID not in cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid','--format=csv,noheader']), 'foreign GPU2 compute present'
phase=R/a.phase;phase.mkdir(exist_ok=False)
(phase/'gpu-pre.txt').write_text(cmd(['nvidia-smi','-q']))
(phase/'affinity-pre.txt').write_text(cmd(['ps','-eLo','pid,tid,psr,pcpu,comm']))
for case in ['00021','00046']:
 for layout in (['G'] if a.phase=='capture' else ['G','L']):
  for backend in ['cpu','cuda']:
   label=f'{case}-{layout}-{backend}';d=phase/label;d.mkdir()
   binary=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr') if a.phase=='baseline' else R/'build2/motioncorr'
   expected_binary=json.loads((R/'diagnostic-pins.json').read_text())['binary_sha256'] if a.phase!='baseline' else json.loads((R/'inventory.json').read_text())['hashes'][str(binary)]['sha256']
   pre=admission(case,binary,expected_binary)
   (d/'ADMISSION.json').write_text(json.dumps(pre,indent=2)+'\n')
   if not pre['admitted']:raise SystemExit('per-producer admission declined; retained, no launch/retry')
   args=[str(binary),'--i','movies.star','--o',str(d/'out')+'/', '--j','8','--use_own','--dose_weighting','--dose_per_frame','1.277','--bfactor','150','--seed','1','--expected_frames','24','--gainref','Movies/gain.mrc','--ingest','float']
   if layout=='L': args+=['--patch_x','5','--patch_y','5']
   if backend=='cuda':args+=['--gpu','0','--ingest_witness',str(d/'ingest.txt')]
   env=os.environ.copy();env.pop('MC_BOUNDARY_DIR',None)
   env.update(CUDA_VISIBLE_DEVICES=UUID if backend=='cuda' else '',CUDA_DEVICE_ORDER='PCI_BUS_ID',OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='1',LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64')
   if a.phase=='capture':(d/'capture').mkdir();env['MC_BOUNDARY_DIR']=str(d/'capture')
   rec={'start':now(),'binary':str(binary),'binary_sha256':sha(binary),'args':args,'cwd':str(R/case),'affinity':sorted(os.sched_getaffinity(0)),'env':{k:env.get(k) for k in ['CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH','MC_BOUNDARY_DIR']},'star_sha256':sha(R/case/'movies.star'),'production_source':'e77a51a220cb0d91f4ac3c7fac211876d0c6833f','hook_source':None if a.phase=='baseline' else '7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd','harness_sha256':sha(__file__),'source_binding':json.loads((R/'diagnostic-pins.json').read_text()) if a.phase!='baseline' else None,'device_samples':[],'child_affinities':[]}
   (d/'START.json').write_text(json.dumps(rec,indent=2)+'\n')
   with open(d/'stdout.txt','w') as out,open(d/'time.txt','w') as err:
    child=subprocess.Popen(['/usr/bin/time','-v']+args,cwd=R/case,env=env,stdout=out,stderr=err)
    while child.poll() is None:
     for pid in tree(child.pid):
      try:
       for t in pathlib.Path(f'/proc/{pid}/task').iterdir():
        mask=affinity(t.name);rec['child_affinities'].append({'pid':pid,'tid':int(t.name),'mask':mask})
      except (FileNotFoundError,ProcessLookupError):pass
     smi=cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader'])
     if smi.strip():rec['device_samples'].append({'utc':now(),'smi':smi})
     time.sleep(.25)
    rec.update(rc=child.returncode,end=now())
   rec['hashes']={str(x.relative_to(d)):{'bytes':x.stat().st_size,'sha256':sha(x)} for x in d.rglob('*') if x.is_file() and x.name!='START.json'}
   (d/'RUN.json').write_text(json.dumps(rec,indent=2)+'\n')
   print(label,rec['rc'],flush=True)
   if rec['rc']!=0: raise SystemExit(rec['rc'])
   if not rec['child_affinities'] or any(x['mask']!=list(range(80,88)) for x in rec['child_affinities']):raise SystemExit('child affinity witness failed; outputs retained')
(phase/'gpu-post.txt').write_text(cmd(['nvidia-smi','-q']))
(phase/'COMPLETE').write_text(now()+'\n')
