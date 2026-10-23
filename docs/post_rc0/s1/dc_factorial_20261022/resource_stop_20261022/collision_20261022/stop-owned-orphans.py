# SPDX-License-Identifier: GPL-2.0-or-later
# Exact local parent-owned duplicate Claude sessions only; never name/group signalling.
from pathlib import Path
import subprocess,json,os,signal,time,datetime
P=Path(__file__).parent
baseline=json.loads((P/'process-snapshot.json').read_text())
expected={x['pid']:x for x in baseline['selected'] if x['pid'] in [75362,82476]}
assert len(expected)==2 and all(x['ppid']==1 and x['uid']==os.getuid() and '--resume=8864b6f5-c104-4b3b-8024-85b7fde2b670' in x['argv'] and '--add-dir /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c79c479' in x['argv'] for x in expected.values())
def snapshot():
 rows={}
 for l in subprocess.check_output(['ps','-axo','pid=,ppid=,uid=,lstart=,command='],text=True).splitlines():
  a=l.split(None,8)
  if len(a)==9:rows[int(a[0])]={'pid':int(a[0]),'ppid':int(a[1]),'uid':int(a[2]),'birth':' '.join(a[3:8]),'argv':a[8]}
 return rows
def same(x,y):return bool(x and y and all(x[k]==y[k] for k in ['pid','uid','birth','argv']))
actions=[]
def sig(x,s):
 now=snapshot().get(x['pid'])
 if now is None:actions.append({'pid':x['pid'],'result':'already gone'});return
 assert same(x,now),('identity changed',x['pid'])
 assert x['uid']==os.getuid()
 os.kill(x['pid'],s);actions.append({'pid':x['pid'],'birth':x['birth'],'signal':signal.Signals(s).name})
# Quiesce only orphan control owners before discovering their exact descendants.
for x in expected.values():sig(x,signal.SIGSTOP)
rows=snapshot();owned=dict(expected);depth={n:0 for n in owned}
while True:
 new={n:x for n,x in rows.items() if x['ppid'] in owned and n not in owned}
 if not new:break
 for n,x in new.items():assert x['uid']==os.getuid();depth[n]=depth[x['ppid']]+1
 owned.update(new)
(P/'pre-signal-tree.json').write_text(json.dumps(owned,indent=2)+'\n')
for n in sorted(owned,key=lambda n:depth[n],reverse=True):
 if n not in expected:sig(owned[n],signal.SIGTERM)
for x in expected.values():sig(x,signal.SIGTERM);sig(x,signal.SIGCONT)
time.sleep(2)
remaining={n:x for n,x in owned.items() if same(x,snapshot().get(n))}
for x in remaining.values():sig(x,signal.SIGKILL)
time.sleep(.5)
post=snapshot();left={n:post[n] for n,x in owned.items() if same(x,post.get(n))}
current=post.get(23920);assert current and current['ppid']==16516 and current['birth']=='Fri Oct 23 00:39:05 2026' and '--resume=8864b6f5-c104-4b3b-8024-85b7fde2b670' in current['argv']
r={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actions':actions,'owned_remaining':left,'tracked_author_23920_preserved':current,'scope':'Only local orphan copies75362/82476 of the same delegated DC author and their identity-bound descendants. No process group/name signals, no remote signals.'}
(P/'stop-receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'signals':len(actions),'owned_remaining':list(left),'current_author_preserved':23920}));assert not left
