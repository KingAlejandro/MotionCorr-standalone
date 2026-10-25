"""Receive and verify one static data packet on the admitted cpu64 lane; no evaluator."""
import datetime,fcntl,hashlib,json,os,pathlib,sys,tarfile,time
M=FROZEN_MANIFEST
ns=pathlib.Path(sys.argv[1]);expected_archive_sha=sys.argv[2]
assert os.sched_getaffinity(0)=={62}
fds=[]
for name in ['/tmp/motioncorr-cpu64-bench.lock','/tmp/motioncorr-dc-late68-cpu62.lock']:
 fd=os.open(name,os.O_CREAT|os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW,0o666);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);fds.append(fd)
def sample():
 l=next(x for x in pathlib.Path('/proc/stat').read_text().splitlines() if x.startswith('cpu62 '));v=list(map(int,l.split()[1:]))[:8];return sum(v),v[3]+v[4]
a=sample();time.sleep(3);b=sample();busy=1-(b[1]-a[1])/(b[0]-a[0]);assert busy<.5
mi=pathlib.Path('/proc/meminfo').read_text();ram=int(mi.split('MemAvailable:')[1].split()[0])*1024;assert ram>16<<30
st=os.statvfs('/tmp');free=st.f_bavail*st.f_frsize;assert free>16<<30
ns.mkdir();f=ns/'input.tar';h=hashlib.sha256();n=0
admission={'scope':'input staging only, no numerical evaluation','captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'affinity':[62],'cpu_busy_fraction':busy,'mem_available_bytes':ram,'scratch_free_bytes':free,'scratch_budget_bytes':16<<30}
(ns/'STAGING-ADMISSION.json').write_text(json.dumps(admission,indent=2)+'\n')
with f.open('xb') as out:
 while True:
  buf=sys.stdin.buffer.read(8<<20)
  if not buf:break
  n+=len(buf);assert n<8<<30;h.update(buf);out.write(buf)
assert h.hexdigest()==expected_archive_sha
want={e['stage']:e for e in M['all_files']};assert len(want)==411
root=ns/'raw';root.mkdir()
with tarfile.open(f) as t:
 members=t.getmembers();names=[x.name for x in members];assert len(names)==len(set(names))==411 and set(names)==set(want)
 for x in members:
  assert x.isfile() and not pathlib.PurePosixPath(x.name).is_absolute() and '..' not in pathlib.PurePosixPath(x.name).parts and x.size==want[x.name]['bytes']
 t.extractall(root,filter='data')
total=0
for rel,e in want.items():
 pp=root/rel;assert pp.is_file() and not pp.is_symlink() and pp.stat().st_size==e['bytes'];hh=hashlib.sha256()
 with pp.open('rb') as inp:
  for buf in iter(lambda:inp.read(8<<20),b''):hh.update(buf)
 assert hh.hexdigest()==e['sha256'],rel;total+=e['bytes']
rec={'state':'STAGED_ALL_411_PAYLOAD_HASHES_MATCH','root':str(root),'archive_sha256':h.hexdigest(),'archive_bytes':n,'content_bytes':total,'files':411,'new_native_jobs':0,'evaluations':0,'admission':admission,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(ns/'STAGING-RESULT.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec))
