import json,pathlib,os,subprocess,sys,fcntl
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');shard=int(sys.argv[1]);mask=['56-63','64-71','72-79'][shard]
rows=[r for r in json.load(open(s/'rows-all.json')) if any(r['arms'].get(a,{}).get('relative_rmse',0)>=.1 for a in ['A1','A2'])]
old=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1ccf/runs')
for j,r in enumerate(rows):
 if j%3!=shard:continue
 mv,g=r['movie'],r['grid'];label='%s-p%d-cpu'%(mv,g);out=s/'runs'/label
 if mv in ['e10216-00','e12963-00','e10474f3-00']:
  p=old/('%s-p%d-diag-cpu-on'%(mv.rsplit('-',1)[0],g))
  if (p/'ccf.txt').exists():
   subprocess.run(['/usr/bin/python3',str(s/'tools/identity.py'),r['reference_run'],str(p)],check=True,stdout=open(s/('%s-p%d-reused-cpu-identity.json'%(mv,g)),'w'))
   continue
 with open('/tmp/motioncorr-peakfit-capture-%s-p%d.lock'%(mv,g),'w') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX)
  e=dict(os.environ,S13C_ROOT=str(s),LANE_GPU='0',MC_SOURCE_SHA='4837b2100bcbf436cb88896a50a082f788bb3e29',MC_CPU_MASK=mask,MC_CPU_LOCK='/tmp/motioncorr-peakfit-cpu%s.lock'%shard)
  if r['reference_regenerated']:e['S13C_SWEEP']=str(s/'extra/sweep')
  subprocess.run(['/usr/bin/python3',str(s/'tools/run_c.py'),'--sweep-label','%s-p%d-F-cuda'%(mv,g),'--label',label,'--binary',str(s/'build-A0/motioncorr'),'--env','MC_DIAG_CCF={out}/ccf.txt','--env','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt'],env=e,check=True)
  assert json.load(open(out/'run.json'))['rc']==0,out
  p=subprocess.run(['/usr/bin/python3',str(s/'tools/identity.py'),r['reference_run'],str(out)],capture_output=True,text=True,check=True)
  (out/'identity-primary-cpu.json').write_text(p.stdout)
print('DONE')
