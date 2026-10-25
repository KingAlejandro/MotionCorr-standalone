"""One static, hash-checked byte collection; no evaluator or native launch."""
import datetime,hashlib,json,pathlib,shutil,subprocess,time
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
plan=pathlib.Path('/tmp/motioncorr-20261025-dc-late68-plan')
raw=(P/'dc-late68-collection-MANIFEST-frozen.json').read_bytes();m=json.loads(raw)
assert m['schema']=='dc-late68-static-collection-v1'
assert m['ids_sha256']=='b43462cf148c76c7bffd663aba29ee3e42de647804256b0c60637f36063d01a9'
assert m['counts']['RUN']==68 and m['counts']['movie_mrc']==66 and m['hashes_still_needed']==0
files=m['all_files'];assert len({x['stage'] for x in files})==len(files)
assert all(x.get('sha256') and isinstance(x.get('bytes'),int) for x in files)
assert sum(x['bytes'] for x in files)<8<<30
D=pathlib.Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261025')
assert shutil.disk_usage(D).free>16<<30
archive=D/'DC-late68-inputs-v1.tar'
code=r'''
import pathlib,hashlib,json,tarfile,sys,fcntl,os,time,io
M=MANIFEST
assert os.sched_getaffinity(0)=={8,9}
fd=os.open('/tmp/motioncorr-c1-cpu8-9.lock',os.O_CREAT|os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW,0o666)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
def sample():
 d={}
 for l in pathlib.Path('/proc/stat').read_text().splitlines():
  if l.startswith(('cpu8 ','cpu9 ')):
   a=l.split();v=list(map(int,a[1:]))[:8];d[a[0]]=(sum(v),v[3]+v[4])
 return d
a=sample();time.sleep(3);b=sample();busy={k:1-(b[k][1]-v[1])/(b[k][0]-v[0]) for k,v in a.items()};assert max(busy.values())<.5
mem=pathlib.Path('/proc/meminfo').read_text();assert int(mem.split('MemAvailable:')[1].split()[0])>512*1024
st=os.statvfs(M['source_root']);assert st.f_bavail*st.f_frsize>16<<30
for ident in pathlib.Path('/proc').iterdir():
 if not ident.name.isdigit():continue
 try:argv=(ident/'cmdline').read_bytes().split(b'\0')
 except (PermissionError,FileNotFoundError,ProcessLookupError):continue
 assert not any(pathlib.PurePath(x.decode(errors='replace')).name in {'evaluate.py','matrix.py'} for x in argv if x),str(ident)
class DigestReader:
 def __init__(self,f):self.f=f;self.h=hashlib.sha256();self.n=0
 def read(self,n):
  b=self.f.read(n);self.h.update(b);self.n+=len(b);return b
total=0
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for e in M['all_files']:
  name=e['stage'];assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
  p=pathlib.Path(e['source']);assert p.is_file() and not p.is_symlink() and p.stat().st_size==e['bytes'],str(p)
  with p.open('rb') as f:
   reader=DigestReader(f);ti=tarfile.TarInfo(name);ti.size=e['bytes'];ti.mode=0o444;t.addfile(ti,reader)
   assert reader.n==e['bytes'] and reader.h.hexdigest()==e['sha256'] and os.fstat(f.fileno()).st_size==e['bytes'],str(p)
  total+=e['bytes']
print(json.dumps({'state':'COLLECTED_ALL_EXPECTED_HASHES_MATCH','files':len(M['all_files']),'content_bytes':total,'busy':busy,'affinity':[8,9],'new_native_jobs':0,'evaluations':0}),file=sys.stderr)
'''.replace('M=MANIFEST','M=json.loads('+repr(raw.decode())+')')
start={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'byte collection only','manifest_sha256':hashlib.sha256(raw).hexdigest(),'archive':str(archive),'source_cpu_mask':[8,9],'expected_files':len(files),'expected_bytes':sum(x['bytes'] for x in files)}
(P/'dc-late68-collection-start.json').write_text(json.dumps(start,indent=2)+'\n')
with archive.open('xb') as f:
 q=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs','taskset -c 8-9 python3 -'],stdin=subprocess.PIPE,stdout=f,stderr=subprocess.PIPE)
 _,err=q.communicate(code.encode(),timeout=900)
rec=dict(start,exit=q.returncode,stderr=err.decode(),archive_bytes=archive.stat().st_size,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
if q.returncode==0:
 h=hashlib.sha256()
 with archive.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 rec['archive_sha256']=h.hexdigest()
(P/'dc-late68-collection-result.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec,indent=2))
raise SystemExit(0 if q.returncode==0 else 1)
