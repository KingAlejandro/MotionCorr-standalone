import pathlib,subprocess,json,datetime,hashlib
p=pathlib.Path('/tmp/motioncorr-20261025-parent');f=p/'r12-native-execution.json';assert not f.exists();s='/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb';ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs']
code=r'''import os,pathlib,hashlib,tarfile,shutil,json,subprocess,fcntl,time
p=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb');v=p/'tools-v2.4-run';assert not v.exists();assert not (p/'c1-item12').exists()
f=os.open('/tmp/motioncorr-c1-cpu8-9.lock',os.O_RDWR|os.O_APPEND);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);assert os.sched_getaffinity(0)=={8,9}
def sample():
 d={}
 for l in pathlib.Path('/proc/stat').read_text().splitlines():
  if l.startswith(('cpu8 ','cpu9 ')):
   a=l.split();x=list(map(int,a[1:]))[:8];d[a[0]]=(sum(x),x[3]+x[4])
 return d
a=sample();time.sleep(3);b=sample();busy={k:1-(b[k][1]-x[1])/(b[k][0]-x[0]) for k,x in a.items()};assert max(busy.values())<.5
q=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],capture_output=True,text=True,check=True);assert 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d' not in q.stdout
m=dict((l.split(':')[0],l.split(':')[1].strip()) for l in pathlib.Path('/proc/meminfo').read_text().splitlines());assert int(m['MemAvailable'].split()[0])>64*1024*1024
assert os.statvfs(p).f_bavail*os.statvfs(p).f_frsize>16<<30
v.mkdir()
for line in (p/'tools-v2.3-run.sha256').read_text().splitlines():
 h,n=line.split(None,1);n=n.strip();src=p/'tools-v2.3-run'/n;assert hashlib.sha256(src.read_bytes()).hexdigest()==h;shutil.copy2(src,v/n)
pack=p/'r12-fixed-files-da2d202b.tar';assert hashlib.sha256(pack.read_bytes()).hexdigest()=='260062ce133d228c7844f942a293546ac36efa2be0e346a81ba5d54c9c3c067c'
with tarfile.open(pack) as t:
 assert {x.name for x in t.getmembers()}=={'c1_item12.py','c1_item12.diff','make_c1_item12.py','test_c1_item12_binding.py'};assert all(x.isfile() for x in t.getmembers());t.extractall(v,filter='data')
(p/'tools-v2.4-run.sha256').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.name+'\n' for x in sorted(v.iterdir()) if x.is_file()))
(p/'tools-v2.4-run.PROVENANCE').write_text('sourcee77 unchanged; toolingda2d202bf0caf9ee0859de68e872cbfbc92810fd; threepatchedfiles+oneimporttest; Linux5/5 parentreview; oldV23 unchanged\n')
env=os.environ.copy();env.update(C1_SCR=str(p),C1_SHA='e77a51a220cb0d91f4ac3c7fac211876d0c6833f',PYTHONDONTWRITEBYTECODE='1')
rec={'source_sha':env['C1_SHA'],'tool_source_commit':'da2d202bf0caf9ee0859de68e872cbfbc92810fd','tool_manifest_sha256':hashlib.sha256((p/'tools-v2.4-run.sha256').read_bytes()).hexdigest(),'affinity':sorted(os.sched_getaffinity(0)),'busy':busy,'memory_available':m['MemAvailable'],'gpu_apps_pre':q.stdout,'state':'RUNNING','stages':[],'no_timing_claim':True}
# An actual deployed import, not the mirror layout, before native work.
help_cmd='source "$C1_SCR/tools-v2.4-run/c1_env.sh" && "$C1_PY" -I -B "$C1_SCR/tools-v2.4-run/c1_item12.py" --help'
h=subprocess.run(['bash','-c',help_cmd],env=env,capture_output=True,text=True,timeout=30);rec['deployed_import']={'exit':h.returncode,'stdout':h.stdout,'stderr':h.stderr};assert h.returncode==0,h.stderr
for row in ['12','12ds']:
 cmd=['bash',str(v/'c1_stage.sh'),'i5-20261025-r'+row,'bash',str(v/'c1_item.sh'),row];t=time.time();r=subprocess.run(cmd,env=env,capture_output=True,text=True);rec['stages'].append({'argv':cmd,'exit':r.returncode,'wall_s':time.time()-t,'stdout':r.stdout,'stderr':r.stderr});(p/'r12-i5-20261025.json').write_text(json.dumps(rec,indent=2)+'\n')
 if r.returncode:rec['state']='STOPPED_NO_RETRY';break
else:rec['state']='STAGES_EXIT0_NEEDS_PARENT_GRADE'
(p/'r12-i5-20261025.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec));raise SystemExit(0 if rec['state'].startswith('STAGES') else 1)
'''
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha':'e77a51a220cb0d91f4ac3c7fac211876d0c6833f','tool_commit':'da2d202bf0caf9ee0859de68e872cbfbc92810fd','argv':ssh+['taskset -c 8-9 python3 -'],'stdin':code,'state':'LAUNCHING_ONCE'};f.write_text(json.dumps(r,indent=2)+'\n')
v=subprocess.run(r['argv'],input=code,capture_output=True,text=True);r.update(exit=v.returncode,stdout=v.stdout,stderr=v.stderr,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='RETURNED_NEEDS_GRADE');f.write_text(json.dumps(r,indent=2)+'\n');print('outer exit',v.returncode);print(v.stdout[-2200:]);print(v.stderr[-1200:])
