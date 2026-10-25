import pathlib,os,fcntl,time,sys,json,hashlib,tarfile,subprocess,resource
n=pathlib.Path(sys.argv[1]);pin=sys.argv[2];fd=[]
for name in ['/tmp/motioncorr-cpu64-bench.lock','/tmp/motioncorr-w4-analysis-cpu62.lock']:
 f=os.open(name,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fd.append(f)
assert os.sched_getaffinity(0)=={62}
def cpu():
 v=list(map(int,next(x for x in pathlib.Path('/proc/stat').read_text().splitlines() if x.startswith('cpu62 ')).split()[1:]))[:8];return sum(v),v[3]+v[4]
a=cpu();time.sleep(3);b=cpu();busy=1-(b[1]-a[1])/(b[0]-a[0]);assert busy<.5
m=dict((x.split(':')[0],x.split(':')[1].strip()) for x in pathlib.Path('/proc/meminfo').read_text().splitlines());assert int(m['MemAvailable'].split()[0])>2*1024*1024
assert os.statvfs('/tmp').f_bavail*os.statvfs('/tmp').f_frsize>256<<20
n.mkdir();data=sys.stdin.buffer.read();assert hashlib.sha256(data).hexdigest()==pin;(n/'input.tar').write_bytes(data)
with tarfile.open(n/'input.tar') as t:
 assert all(x.isfile() and '..' not in pathlib.PurePosixPath(x.name).parts and not pathlib.PurePosixPath(x.name).is_absolute() for x in t.getmembers());t.extractall(n,filter='data')
p=n/'consumer';assert hashlib.sha256((p/'dc_snapshot_consumer.py').read_bytes()).hexdigest()=='5b5dfd32892bef042dd530dcadf7bc5f5ae9c6f63a65165206d05cbdc2471c6f'
resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(16<<20,16<<20))
env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
cmd=['/usr/bin/timeout','--signal=TERM','--kill-after=5s','120s','/usr/bin/time','-v','-o',str(n/'time-v.log'),'/usr/bin/python3','-I','-B',str(p/'dc_snapshot_consumer.py'),'--eval-dir',str(p/'collected-snapshot'),'--evaluations',str(p/'EVALUATIONS.json'),'--queue',str(p/'queue.json'),'--run-exits',str(p/'RUN-EXITS.txt'),'--tier-a-summary',str(p/'A-summary.json'),'--out',str(p/'run-once')]
t=time.time();q=subprocess.run(cmd,capture_output=True,text=True,env=env);r={'argv':cmd,'exit':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'wall_s':time.time()-t,'affinity':sorted(os.sched_getaffinity(0)),'busy':busy,'memory_available':m['MemAvailable'],'ram_cap_bytes':2<<30,'input_sha256':pin,'scientific_acceptance':'NOT_EVALUATED','new_native_jobs':0};(n/'RESULT.json').write_text(json.dumps(r,indent=2)+'
');print(json.dumps(r));raise SystemExit(q.returncode)
