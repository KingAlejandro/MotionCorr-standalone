"""Fresh real CPU64 resource admission around the one late68 evaluator caller."""
import datetime,fcntl,json,os,pathlib,subprocess,sys,time
ns=pathlib.Path(sys.argv[1]);root=ns/'raw';tools=ns/'tools'
assert os.sched_getaffinity(0)=={62}
locks=[]
for p in ['/tmp/motioncorr-cpu64-bench.lock','/tmp/motioncorr-dc-late68-cpu62.lock']:
 fd=os.open(p,os.O_CREAT|os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW,0o666);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(fd)
def sample():
 line=next(x for x in pathlib.Path('/proc/stat').read_text().splitlines() if x.startswith('cpu62 '));v=list(map(int,line.split()[1:]))[:8];return sum(v),v[3]+v[4]
a=sample();time.sleep(3);b=sample();busy=1-(b[1]-a[1])/(b[0]-a[0]);assert busy<.5
active=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:argv=(p/'cmdline').read_bytes().split(b'\0')
 except (PermissionError,FileNotFoundError,ProcessLookupError):continue
 if any(pathlib.PurePath(x.decode(errors='replace')).name in {'evaluate.py','evaluate-late68-v1.py','matrix.py'} for x in argv if x) and b'motioncorr' in b' '.join(argv).lower():active.append(p.name)
assert not active,active
mem=pathlib.Path('/proc/meminfo').read_text();ram=int(mem.split('MemAvailable:')[1].split()[0])*1024;assert ram>16<<30
st=os.statvfs(ns);free=st.f_bavail*st.f_frsize;assert free>16<<30
env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
versions=subprocess.check_output([sys.executable,'-I','-B','-c','import sys,numpy;print(sys.version);print(numpy.__version__)'],text=True,env=env)
ad={'scope':'dc-late68-evaluator-only','captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cpu_core':62,'cpu_lock_held':True,'busy_check_clear':True,'cpu_busy_fraction':busy,'active_evaluator_processes':len(active),'available_ram_bytes':ram,'ram_cap_bytes':8<<30,'scratch_budget_bytes':16<<30,'scratch_free_bytes':free,'python_executable':sys.executable,'versions':versions,'host':subprocess.check_output(['hostname'],text=True).strip(),'uid':os.getuid(),'claim':'existing-output evaluation, not native execution/performance/science qualification'}
ap=ns/'EVAL-ADMISSION.json'
with ap.open('x') as f:json.dump(ad,f,indent=2);f.write('\n')
cmd=[sys.executable,'-I','-B',str(tools/'run_late68_once.py'),'--root',str(root),'--admission',str(ap)]
q=subprocess.run(cmd,env=env,cwd=ns,capture_output=True,text=True)
rec={'scope':'one exact68existingCPU record evaluation','argv':cmd,'exit':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'admission':ad,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (ns/'PARENT-EVAL-EXECUTION.json').open('x') as f:json.dump(rec,f,indent=2);f.write('\n')
print(json.dumps(rec));raise SystemExit(0 if q.returncode==0 else q.returncode)
