"""Combine exact frozen736 and newly evaluated68, then unchanged reviewed v2.2."""
import datetime,fcntl,hashlib,json,os,pathlib,shutil,subprocess,sys,time
late=pathlib.Path(sys.argv[1]);dest=pathlib.Path(sys.argv[2])
old=pathlib.Path('/tmp/motioncorr-dc-consumer-attempt2-20261025-dcdd56d4-153e-4f2a-9af7-8b60867f922a/consumer')
assert os.sched_getaffinity(0)=={62}
fds=[]
for p in ['/tmp/motioncorr-cpu64-bench.lock','/tmp/motioncorr-dc-late68-cpu62.lock']:
 fd=os.open(p,os.O_CREAT|os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW,0o666);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);fds.append(fd)
def sample():
 l=next(x for x in pathlib.Path('/proc/stat').read_text().splitlines() if x.startswith('cpu62 '));v=list(map(int,l.split()[1:]))[:8];return sum(v),v[3]+v[4]
a=sample();time.sleep(3);b=sample();busy=1-(b[1]-a[1])/(b[0]-a[0]);assert busy<.5
ram=int(pathlib.Path('/proc/meminfo').read_text().split('MemAvailable:')[1].split()[0])*1024;assert ram>2<<30
st=os.statvfs('/tmp');assert st.f_bavail*st.f_frsize>1<<30
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
adapter=old/'adapter/summarize_v2_2.py';assert sha(adapter)=='c2f391822b880fba20b7a9571e4d5150fa3b365bd18afff2e44f90fef939ef45'
em=old/'EVALUATIONS.json';assert sha(em)=='4ec94412fb98e6b1e4fda26b8b510e8f23c235a22ad162774e448c2a228d988a'
frozen=load(em)['sha256'];assert len(frozen)==736
receipt=load(late/'raw/LATE68-RESULT.json');assert receipt['child_exit']==0 and receipt['recorded_all_68'] and len(receipt['records'])==68
new=receipt['records'];assert not set(new)&set(frozen)
states={}
for ident,r in new.items():
 states[r['state']]=states.get(r['state'],0)+1
 assert r['state'] in {'EVALUATED','CONTROL_ONLY'}
 assert sha(late/'raw/eval/B'/f'{ident}.json')==r['sha256']
assert states=={'EVALUATED':66,'CONTROL_ONLY':2},states
dest.mkdir();ev=dest/'eval';(ev/'B').mkdir(parents=True)
pins={}
for ident,digest in frozen.items():
 src=old/'collected-snapshot/B'/f'{ident}.json';assert sha(src)==digest;target=ev/'B'/src.name;shutil.copyfile(src,target);target.chmod(0o444);pins[ident]=digest
for ident,r in new.items():
 src=late/'raw/eval/B'/f'{ident}.json';target=ev/'B'/src.name;assert not target.exists();shutil.copyfile(src,target);target.chmod(0o444);pins[ident]=r['sha256']
assert len(pins)==len(list((ev/'B').glob('*.json')))==804
(dest/'COMBINED-804-MANIFEST.json').write_text(json.dumps({'count':804,'frozen736_manifest_sha256':sha(em),'late68_receipt_sha256':sha(late/'raw/LATE68-RESULT.json'),'sha256':pins,'native_jobs':0,'old_record_re_evaluations':0},indent=2)+'\n')
cmd=[sys.executable,'-I','-B',str(adapter),str(ev),str(dest/'summary')]
q=subprocess.run(cmd,capture_output=True,text=True)
(dest/'adapter.stdout').write_text(q.stdout);(dest/'adapter.stderr').write_text(q.stderr)
summary=load(dest/'summary/tierB-v2.json') if (dest/'summary/tierB-v2.json').exists() else None
rec={'scope':'new804recordTierBsummary; old371/878snapshots unchanged; no new native job','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'affinity':[62],'cpu_busy_fraction':busy,'mem_available_bytes':ram,'late68_terminal_states':states,'adapter_sha256':sha(adapter),'adapter_exit':q.returncode,'adapter_stdout':q.stdout,'adapter_stderr':q.stderr,'summary_state':summary.get('state') if summary else None,'counts':{k:len(summary[k]) for k in ['rows','pairs','regressions','record_audit']} if summary else None,'summary_sha256':sha(dest/'summary/tierB-v2.json') if summary else None,'campaign_grade':'NOT_ASSIGNED_TIERC_STILL_UNGRADED'}
(dest/'RESULT.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec))
raise SystemExit(0 if summary and q.returncode in {0,2} else 1)
