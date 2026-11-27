import pathlib,subprocess,json,hashlib,uuid,datetime,time,shlex
P=pathlib.Path('/tmp/motioncorr-20261025-parent'); log=P/'guard-execution.json'
assert not log.exists()
base=pathlib.Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-d9b98408/docs/post_rc0/issue264/native/n3-cpu1-regrade-v2/parent-package-v2.2')
r=json.loads((base/'attempt2-PACKAGE-RECEIPT.json').read_text());pkg=base/'attempt2-package.tar'
assert hashlib.sha256(pkg.read_bytes()).hexdigest()==r['package_sha256']
n='/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1-regrade-v2-2-593c9e2cc536-'+str(uuid.uuid4())
rec={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'namespace':n,'source_commit':r['source_commit'],'package_sha256':r['package_sha256'],'manifest_sha256':r['package_manifest_sha256'],'authority':'25 October explicit user VM authority; parent selected read-only guard grade after existing-results inventory; direct route overrides obsolete gateway; CPU13 serial; no native MotionCorr','steps':[],'state':'PREPARING'}
def save():log.write_text(json.dumps(rec,indent=2)+'\n')
def step(name,cmd,stdin=None,timeout=30):
 t=time.time();v=subprocess.run(cmd,input=stdin,capture_output=True,text=True,timeout=timeout)
 rec['steps'].append({'name':name,'argv':cmd,'stdin':stdin,'exit':v.returncode,'wall_s':time.time()-t,'stdout':v.stdout,'stderr':v.stderr});save()
 if v.returncode:raise RuntimeError(name+' exited '+str(v.returncode))
 return v.stdout
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs']
save()
try:
 code="""import os,pathlib,subprocess,json,time,fcntl
locks=['/tmp/motioncorr-dc-eval-cpu13.lock','/tmp/motioncorr-w4-cpu13.lock','/tmp/motioncorr-guard264-cpu13-regrade.lock']
fds=[]
for n in locks:
 f=os.open(n,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fds.append(f)
def cpu():
 v=list(map(int,next(l for l in pathlib.Path('/proc/stat').read_text().splitlines() if l.startswith('cpu13 ')).split()[1:]))[:8];return sum(v),v[3]+v[4]
a=cpu();time.sleep(3);b=cpu();busy=1-(b[1]-a[1])/(b[0]-a[0]);assert busy<=0.5,busy
m=dict((l.split(':')[0],l.split(':')[1].strip()) for l in pathlib.Path('/proc/meminfo').read_text().splitlines());assert int(m['MemAvailable'].split()[0])>262144
s=os.statvfs('/mnt/clathrin');assert s.f_bavail*s.f_frsize>100<<20
print(json.dumps({'cpu13_busy_fraction':busy,'mem_available':m['MemAvailable'],'scratch_free_bytes':s.f_bavail*s.f_frsize,'locks_probed_free':locks,'parent_allocation':'CPU13 one thread;256MiB reserved;20MiB output cap;180s timeout;not benchmark'}))
"""
 step('fresh-admission',ssh+['python3 -'],code,timeout=15)
 step('reserve-new-namespace',ssh+['mkdir -m 700 '+shlex.quote(n)])
 step('transfer-reviewed-package',['scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=10',str(pkg),'4GPUs:'+n+'/package.tar'])
 code="""import pathlib,hashlib,tarfile,sys
p=pathlib.Path(sys.argv[1]);b=(p/'package.tar').read_bytes();assert hashlib.sha256(b).hexdigest()==sys.argv[2]
with tarfile.open(p/'package.tar') as t:
 m=t.getmembers();assert len(m)==10;assert all(x.isfile() and pathlib.PurePosixPath(x.name).name==x.name and x.size<=1048576 for x in m)
 assert sum(x.size for x in m)<=1048576
 (p/'package').mkdir();t.extractall(p/'package',members=m,filter='data')
print('package exact;10 bounded regular basenames extracted')
"""
 step('verify-before-extraction',ssh+['python3 - '+shlex.quote(n)+' '+r['package_sha256']],code)
 # Same immutable command shape. Bootstrap refers only to the sibling namespace, never input root.
 inner='exec /usr/bin/timeout --signal=TERM --kill-after=5s 180s /usr/bin/taskset -c 13 /usr/bin/env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -I -B '+shlex.quote(n+'/package/remote_run_v2_2.py')+' --source-commit '+r['source_commit']+' --package-manifest-sha256 '+r['package_manifest_sha256']+' --out '+shlex.quote(n+'/run')
 wrapper='cd '+shlex.quote(n)+' && date -u +%FT%TZ > parent.started && ('+inner+') > parent.stdout 2> parent.stderr; rc=$?; echo "$rc" > '+shlex.quote(n+'/parent.exit')+'; date -u +%FT%TZ > '+shlex.quote(n+'/parent.finished')+'; exit "$rc"'
 rec['state']='LAUNCHING_ONCE';save();step('reviewed-regrade-once',ssh+[wrapper],timeout=195)
 rec['state']='DRIVER_EXIT0_NOT_YET_INTERPRETED'
except Exception as e:
 rec['error']=repr(e);rec['state']='STOPPED_NO_RETRY'
finally:
 rec['finish_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
 # Collection after any completed/refused operation; does not rerun the driver.
 subprocess.run(['scp','-q','-r','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs:'+n,str(P/'guard-remote')],timeout=30,check=False)
 print(json.dumps({'state':rec['state'],'error':rec.get('error'),'namespace':n,'steps':[(x['name'],x['exit']) for x in rec['steps']]}))
