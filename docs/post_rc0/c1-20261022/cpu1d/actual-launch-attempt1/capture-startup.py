import datetime,hashlib,json,os,sys
from pathlib import Path
sc=Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb');e=sc/'cpu1d-actual-launch-attempt1';capture=e/'startup-capture'
capture.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':os.uname().nodename,'receipts':{},'processes':{},'stages':[]}
def copy(p):
 if not p.is_file():return
 data=p.read_bytes();dest=capture/p.relative_to(sc);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 r['receipts'][str(p.relative_to(sc))]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
for p in sorted((sc/'logs/launch-cpu1d-attempt1').glob('*')):copy(p)
for p in sorted((sc/'logs').glob('chain-cpu1d.*')):copy(p)
copy(sc/'logs/launch-cpu1d-attempt1.outer.out');copy(sc/'cpu1d-prereq.json')
m=json.loads((sc/'cpu1d-startup-freeze1/cpu1d-manifest.json').read_text())
for s in m['stages']:
 name=s['stage'];row={'stage':name,'allowed_exits':s['allowed_exits'],'reserved':(sc/f'logs/{name}.reserved').exists(),'exit':None}
 for p in sorted((sc/'logs').glob(name+'.*')):
  if p.is_dir():
   for c in p.iterdir():copy(c)
  else:copy(p)
 x=sc/f'logs/{name}.exit'
 if x.exists():row['exit']=x.read_text().strip()
 row['status']='RAN' if row['exit'] is not None else ('RUNNING_OR_PARTIAL' if row['reserved'] else 'UNRUN')
 r['stages'].append(row)
# Read /proc only, no process manipulation. Resolve descendants from captured PPIDs.
procs={}
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:
  stat=(d/'stat').read_text();parts=stat.split(') ',1)[1].split();procs[int(d.name)]=(int(parts[1]),stat)
 except (OSError,IndexError):pass
owned=set()
for name in ['wrapper','chain']:
 p=sc/f'logs/launch-cpu1d-attempt1/{name}.pid'
 if p.exists():owned.add(int(p.read_text()))
# Finite traversal of this single process snapshot, no polling.
for _ in range(len(procs)):
 new={pid for pid,(ppid,_) in procs.items() if ppid in owned};before=len(owned);owned|=new
 if len(owned)==before:break
for pid in sorted(owned):
 d=Path(f'/proc/{pid}')
 try:
  stat=(d/'stat').read_text();parts=stat.split(') ',1)[1].split();status=(d/'status').read_text();argv=(d/'cmdline').read_bytes().split(b'\0')
  v={'pid':pid,'ppid':int(parts[1]),'session':int(parts[3]),'kernel_start_ticks':parts[19],'proc_stat':stat,'uid':next(l.split()[1] for l in status.splitlines() if l.startswith('Uid:')),'cpus':next(l.split(':',1)[1].strip() for l in status.splitlines() if l.startswith('Cpus_allowed_list:')),'actual_argv':[a.decode(errors='replace') for a in argv if a]}
  exe=d/'exe';v['exe']=str(exe.resolve());v['CPU1D_overrides']=[x.decode(errors='replace') for x in (d/'environ').read_bytes().split(b'\0') if x.startswith(b'CPU1D_')]
  if Path(v['exe']).name=='motioncorr':v['binary_sha256']=sha(exe)
  r['processes'][str(pid)]=v
 except (OSError,StopIteration,IndexError) as exc:r['processes'][str(pid)]={'unavailable':str(exc)}
r['wrapper_exit']=(sc/'logs/launch-cpu1d-attempt1/wrapper.exit').read_text().strip() if (sc/'logs/launch-cpu1d-attempt1/wrapper.exit').exists() else None
r['chain_exit']=(sc/'logs/launch-cpu1d-attempt1/chain.exit').read_text().strip() if (sc/'logs/launch-cpu1d-attempt1/chain.exit').exists() else None
r['source']='e77a51a220cb0d91f4ac3c7fac211876d0c6833f';r['aggregate']='ONGOING' if r['wrapper_exit'] is None else 'STOPPED: inspect stage exits; never infer aggregate PASS'
(e/'startup-status.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'utc':r['utc'],'aggregate':r['aggregate'],'wrapper_exit':r['wrapper_exit'],'chain_exit':r['chain_exit'],'stages':[s for s in r['stages'] if s['reserved']],'processes':r['processes']},indent=2))
