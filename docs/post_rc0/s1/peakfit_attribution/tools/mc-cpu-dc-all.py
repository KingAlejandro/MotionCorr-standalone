import pathlib,json,subprocess,sys,os,fcntl
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');old=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1/sweep');shard=int(sys.argv[1]);mask=['56-63','64-71','72-79'][shard]
movies=['%s-%02d'%(fam,i) for fam in ['e10216','e12963','e10474f3'] for i in range(10)]
for j,mv in enumerate(movies):
 if j%3!=shard:continue
 for g in [5,3]:
  src=old/'runs'/('%s-p%d-F-cuda'% (mv,g));root=old
  if not (src/'run.json').exists():
   # Clone the exact extra recipe into a separate source-record namespace.
   base=json.load(open(s/'extra/sweep/runs'/(mv+'-p5-F-cuda')/'run.json'));a=base['argv'];a[a.index('--patch_x')+1]=str(g);a[a.index('--patch_y')+1]=str(g)
   root=s/'extra/dc-sweep';src=root/'runs'/('%s-p%d-F-cuda'%(mv,g));src.mkdir(parents=True,exist_ok=True)
   tmp=src/('run.json.tmp-%s'%os.getpid());json.dump(base,open(tmp,'w'));os.replace(tmp,src/'run.json')
  e=dict(os.environ,S13C_ROOT=str(s),S13C_SWEEP=str(root),LANE_GPU='0',MC_SOURCE_SHA='4837b2100bcbf436cb88896a50a082f788bb3e29',MC_CPU_MASK=mask,MC_CPU_LOCK='/tmp/motioncorr-peakfit-cpu%s.lock'%shard)
  cmd=['/usr/bin/python3',str(s/'tools/run_c.py'),'--sweep-label','%s-p%d-F-cuda'%(mv,g),'--label','%s-p%d-cpuDC'%(mv,g),'--binary',str(s/'build-A0/motioncorr'),'--env','MC_DIAG_ZERO_CCF_DC=1','--env','MC_DIAG_CCF={out}/ccf.txt','--env','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt']
  subprocess.run(cmd,env=e,check=True)
  d=s/'runs'/('%s-p%d-cpuDC'%(mv,g));assert json.load(open(d/'run.json'))['rc']==0
print('DONE')
