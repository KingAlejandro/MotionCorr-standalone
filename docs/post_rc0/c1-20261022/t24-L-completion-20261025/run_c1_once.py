import pathlib,subprocess,json,hashlib,datetime,time,shlex
p=pathlib.Path('/tmp/motioncorr-20261025-parent');f=p/'c1-i4-execution.json';assert not f.exists()
scr='/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb';ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs']
r={'source_sha':'e77a51a220cb0d91f4ac3c7fac211876d0c6833f','tools':'unchanged tools-v2.3-run','script_sha256':hashlib.sha256((p/'c1-i4-L.sh').read_bytes()).hexdigest(),'pins_sha256':hashlib.sha256((p/'C1-I4-PINS.json').read_bytes()).hexdigest(),'authority':'25 Oct user C1 native authority; parent owns GPU3/CPU8-9 for bounded correctness; no timing claim; existing result inventory complete; Gemini M1-M4 closed','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'steps':[],'state':'PREPARING','native_count_max':3,'reuse':'4 prior exact-source L arms, not reruns','budget':'3 tutorial24 native processes; original native-driver timeout7200s each; parent checks liveness/status, no blind retry; new output expected<8GiB within existing160GiB task scratch cap'}
def save():f.write_text(json.dumps(r,indent=2)+'\n')
def step(name,cmd,stdin=None,timeout=30):
 t=time.time();v=subprocess.run(cmd,input=stdin,capture_output=True,text=True,timeout=timeout);r['steps'].append({'name':name,'argv':cmd,'stdin':stdin,'exit':v.returncode,'wall_s':time.time()-t,'stdout':v.stdout,'stderr':v.stderr});save()
 if v.returncode:raise RuntimeError(name+' exited '+str(v.returncode))
 return v.stdout
save()
try:
 code="""import pathlib,json,os,time,fcntl,subprocess
files=['/tmp/motioncorr-c1-cpu8-9.lock','/tmp/motioncorr-gpu3-correctness.lock'];fds=[]
for n in files:
 f=os.open(n,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fds.append(f)
def sample():
 out={}
 for l in pathlib.Path('/proc/stat').read_text().splitlines():
  if l.startswith(('cpu8 ','cpu9 ')):
   a=l.split();v=list(map(int,a[1:]))[:8];out[a[0]]=(sum(v),v[3]+v[4])
 return out
a=sample();time.sleep(3);b=sample();busy={k:1-(b[k][1]-v[1])/(b[k][0]-v[0]) for k,v in a.items()};assert all(v<0.5 for v in busy.values()),busy
q=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],capture_output=True,text=True,check=True);assert 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d' not in q.stdout
m=dict((l.split(':')[0],l.split(':')[1].strip()) for l in pathlib.Path('/proc/meminfo').read_text().splitlines());assert int(m['MemAvailable'].split()[0])>64*1024*1024
s=os.statvfs('/mnt/clathrin');assert s.f_bavail*s.f_frsize>16<<30
p=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb');assert not (p/'t24-i4-20261025').exists();assert not (p/'c1-i4-20261025-L.sh').exists();assert not (p/'c1-i4-20261025-pins.json').exists()
print(json.dumps({'cpu_mask':'8-9','busy':busy,'free_lease_probes':files,'compute_apps':q.stdout,'mem_available':m['MemAvailable'],'scratch_free_bytes':s.f_bavail*s.f_frsize,'other_lanes_untouched':True}))
"""
 step('fresh-resource-admission',ssh+['taskset -c 8-9 python3 -'],code,timeout=15)
 for local,remote in [('C1-I4-PINS.json','c1-i4-20261025-pins.json'),('c1-i4-L.sh','c1-i4-20261025-L.sh')]:step('transfer-'+local,['scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=10',str(p/local),'4GPUs:'+scr+'/'+remote])
 check="import hashlib,pathlib; p=pathlib.Path('"+scr+"'); assert hashlib.sha256((p/'c1-i4-20261025-L.sh').read_bytes()).hexdigest()=='"+r['script_sha256']+"'; assert hashlib.sha256((p/'c1-i4-20261025-pins.json').read_bytes()).hexdigest()=='"+r['pins_sha256']+"'; print('exact wrapper/pins')"
 step('verify-transfer',ssh+['python3 -'],check)
 r['state']='LAUNCHING_ONCE';save()
 step('bounded-L-completion-once',ssh+['taskset -c 8-9 bash '+shlex.quote(scr+'/c1-i4-20261025-L.sh')],timeout=None)
 r['state']='CHAIN_EXIT0_NEEDS_PARENT_GRADE'
except Exception as e:r['error']=repr(e);r['state']='STOPPED_NO_RETRY'
finally:
 r['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps({k:r[k] for k in ['state','script_sha256','finished_utc']}));print(r.get('error',''))
