from pathlib import Path
import os,pwd,json,subprocess,datetime,signal,time,hashlib
ROOT=Path('/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b');PID=3119383;START=815401887
E=ROOT/'parent-resource-stop-20261022-2140';E.mkdir(exist_ok=False)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def info(pid):
 d=Path('/proc')/str(pid)
 try:
  raw=(d/'stat').read_text();v=raw[raw.rfind(')')+2:].split();uid=d.stat().st_uid
  return {'pid':pid,'ppid':int(v[1]),'state':v[0],'start_ticks':int(v[19]),'uid':uid,'argv':(d/'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1],'exe':str((d/'exe').resolve())}
 except (OSError,ValueError):return None
def family():
 allp={}
 for d in Path('/proc').iterdir():
  if d.name.isdigit():
   j=info(int(d.name))
   if j:allp[j['pid']]=j
 ids={PID}
 while True:
  add={n for n,j in allp.items() if j['ppid'] in ids}-ids
  if not add:break
  ids|=add
 return [allp[n] for n in sorted(ids) if n in allp]
def save(name,j):
 f=E/name
 with f.open('x') as h:json.dump(j,h,indent=2);h.write('\n');h.flush();os.fsync(h.fileno())
r=info(PID);assert r and r['start_ticks']==START and r['uid']==os.getuid()==1004
assert r['argv']==['/home/alex/.mc-venv/bin/python3','-B','tools/campaign.py','worker',str(ROOT),'cuda','13']
apps=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory,process_name','--format=csv,noheader'],text=True,capture_output=True,check=True).stdout
foreign=[x for x in apps.splitlines() if 'GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598' in x and 'llama-server' in x]
assert foreign,'Foreign GPU2 occupancy no longer observed; no signal sent'
pre={'utc':now(),'reason':'Notion plan stop on contended venue; foreign GPU2 compute context; prevent further native GPU launches','root':r,'family':family(),'gpu_apps':apps,'foreign_process_not_signalled':True};save('pre.json',pre)
os.kill(PID,signal.SIGSTOP);time.sleep(.2);r2=info(PID);assert r2 and r2['start_ticks']==START and r2['state'] in ('T','t')
owned=family();assert all(j['uid']==1004 for j in owned)
save('coordinator-stopped.json',{'utc':now(),'signal':'SIGSTOP','root':r2,'family':owned,'scope':'Only exact UID/start-identified private worker; no process-group signal'})
# Let its already running child finish, but the stopped coordinator cannot launch another job.
deadline=time.monotonic()+40
while time.monotonic()<deadline:
 living=[j for j in family() if j['pid']!=PID and j['state']!='Z']
 if not living:break
 time.sleep(.25)
remaining=[j for j in family() if j['pid']!=PID and j['state']!='Z'];actions=[]
for j in reversed(remaining):
 cur=info(j['pid'])
 if cur and cur['start_ticks']==j['start_ticks'] and cur['uid']==1004:
  os.kill(j['pid'],signal.SIGTERM);actions.append({'utc':now(),'signal':'SIGTERM','identity':cur})
if remaining:time.sleep(2)
for j in reversed(remaining):
 cur=info(j['pid'])
 if cur and cur['start_ticks']==j['start_ticks'] and cur['uid']==1004 and cur['state']!='Z':
  os.kill(j['pid'],signal.SIGKILL);actions.append({'utc':now(),'signal':'SIGKILL','identity':cur})
cur=info(PID);assert cur and cur['start_ticks']==START and cur['uid']==1004 and cur['state'] in ('T','t')
# Terminate the stopped coordinator only after its owned children finished/reaped or were cancelled.
# SIGKILL avoids ever resuming it into another queue launch; its wrapper records exit137.
os.kill(PID,signal.SIGKILL);actions.append({'utc':now(),'signal':'SIGKILL','identity':cur,'reason':'exact stopped coordinator; no resume/new launch'})
time.sleep(1)
end={'utc':now(),'actions':actions,'root_after':info(PID),'original_family_after':[info(j['pid']) for j in owned if info(j['pid'])],'gpu_apps':subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory,process_name','--format=csv,noheader'],capture_output=True,text=True).stdout,'worker_exit_receipt':(ROOT/'worker-cuda-13.exit').read_text() if (ROOT/'worker-cuda-13.exit').exists() else None,'cpu_workers':[info(n) for n in [3119420,3119494,3119584]],'state':'GPU WORKER STOPPED FOR RESOURCE CONFLICT; any directory without RUN.json remains incomplete, never PASS or rerun in place','foreign_process_not_signalled':True}
save('post.json',end);print(json.dumps({'evidence_dir':str(E),'root_after':end['root_after'],'worker_exit':end['worker_exit_receipt'],'cpu_worker_pids_live':[j['pid'] for j in end['cpu_workers'] if j],'foreign_process_not_signalled':True,'actions':[(j['signal'],j['identity']['pid']) for j in actions]},indent=2))
