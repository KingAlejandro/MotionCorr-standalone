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
def admission(binary,expected_binary,expected_files):
 before=cpu_ticks();time.sleep(.5);after=cpu_ticks()
 busy={c:1-(sum(after[c][3:5])-sum(before[c][3:5]))/max(1,sum(after[c])-sum(before[c])) for c in before}
 lease=json.loads(cmd(['lslocks','--json','-o','PID,COMMAND,PATH'])).get('locks',[])
 conflicts=[]
 for x in lease:
  if x['pid']==os.getpid() or not any(t in (x.get('path') or '') for t in ['motioncorr','mc254']):continue
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
 checks={str(path):sha(path)==expected for path,expected in expected_files.items()}
 checks['binary']=sha(binary)==expected_binary
 smi=cmd(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader'])
 record={'utc':now(),'cpu_busy_fraction_half_second':busy,'lease_snapshot':lease,'overlap_lease_conflicts':conflicts,'compute_conflicts':compute_conflicts,'thread_snapshot':processes,'scratch_bytes':scratch,'scratch_cap_bytes':20*1024**3,'required_increment_headroom_bytes':1024**3,'free_bytes':free,'hash_checks':checks,'gpu_compute':smi,'parent_affinity':affinity(os.getpid())}
 record['admitted']=all(checks.values()) and not conflicts and not compute_conflicts and max(busy.values())<.2 and scratch+1024**3<=20*1024**3 and free>1024**3 and UUID not in smi and record['parent_affinity']==list(range(80,88))
 return record
