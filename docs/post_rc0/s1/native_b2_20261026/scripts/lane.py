"""cpu64 CPUs32-47 lease guard, append-open all known overlapping leases."""
import fcntl,json,os,re,subprocess,sys,time
from pathlib import Path
locks=[]
for p in Path('/tmp').glob('motioncorr*.lock'):
 m=re.search(r'cpu-?(\d+)(?:-(\d+))?',p.name)
 if p.name=='motioncorr-cpu64-bench.lock' or (m and int(m[1])<=47 and int(m[2] or m[1])>=32):locks.append(p)
locks.append(Path('/tmp/motioncorr-b2-cpu32-47.lock'))
handles=[]
for p in sorted(set(locks)):
 f=p.open('a+')
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('LEASE HELD: '+str(p))
 handles.append(f)
print(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),locks=[str(p) for p in sorted(set(locks))],cpus='32-47',command=sys.argv[1:])),flush=True)
subprocess.run(['bash','-c','date -u; uptime; free -h; df -h /tmp; ps -eo pid,psr,pcpu,args --sort=-pcpu | head -12'],check=True)
env=dict(os.environ,OMP_NUM_THREADS='16',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
raise SystemExit(subprocess.run(['taskset','-c','32-47',*sys.argv[1:]],env=env).returncode)
