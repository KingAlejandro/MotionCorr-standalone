import os,sys,time,subprocess
pid=int(sys.argv[1]); out=sys.argv[2]; uuids=set()
def descendants(root):
 fam={root}; todo=[root]
 while todo:
  p=todo.pop()
  try: kids=list(map(int,open('/proc/%d/task/%d/children'%(p,p)).read().split()))
  except OSError: continue
  for k in kids:
   if k not in fam: fam.add(k);todo.append(k)
 return fam
while os.path.exists('/proc/%d'%pid):
 fam=descendants(pid)
 try:
  q=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
  for line in q.splitlines():
   u,p=line.split(',')
   if int(p.strip()) in fam: uuids.add(u.strip())
 except Exception: pass
 time.sleep(.2)
open(out,'w').write('\n'.join(sorted(uuids))+'\n')
