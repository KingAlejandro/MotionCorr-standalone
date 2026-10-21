#!/usr/bin/env python3
"""One worker lane, one movie process at a time; releases GPU lock every run."""
import argparse,json,os,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--lane',type=int,default=0);p.add_argument('--shards',type=int,default=1);p.add_argument('--shard',type=int,default=0);p.add_argument('--arms',default='R,Rprime');p.add_argument('--movies',default='all');p.add_argument('--mask',default='32-39');a=p.parse_args();s=pathlib.Path(a.root)
movies=[f'{fam}-{i:02d}' for fam in ['e10216','e12963','e10474f3'] for i in range(10)] if a.movies=='all' else a.movies.split(',')
sha=(s/'source-sha.txt').read_text().strip();parent=(s/'parent-sha.txt').read_text().strip()
for j,mv in enumerate(movies):
 if j%a.shards!=a.shard:continue
 for grid in [5,3]:
  label=f'{mv}-p{grid}'
  for arm in a.arms.split(','):
   gpu=arm.startswith('G') or arm in ['parentGPU','offGPU'];par=arm.startswith('parent')
   dc={'R':'none','Rprime':'both'}.get(arm,arm.split('_')[-1] if '_' in arm else 'none')
   env=dict(os.environ,S13C_ROOT=str(s),S13C_SWEEP=str(s/'recipes'),LANE_GPU=str(a.lane),MC_SOURCE_SHA=parent if par else sha,MC_CPU_MASK=a.mask,MC_CPU_LOCK=f'/tmp/motioncorr-dc-oracle-cpu-{a.mask}.lock')
   cmd=[sys.executable,str(s/'tools/run.py'),'--sweep-label',label+'-F-cuda','--label',label+'-'+arm,'--binary',str(s/('build-parent' if par else 'build')/'motioncorr')]
   if not par and not arm.startswith('off'):
    cmd+=['--env','MC_DIAG_CCF_DC='+dc,'--env','MC_DIAG_CCF={out}/ccf.txt','--env','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt','--env','MC_DIAG_MODEL_OUT={out}/model.txt']
    if arm in ['R','Rprime']:cmd+=['--env','MC_DIAG_CCF_DOUBLE=1']
   if gpu:cmd+=['--gpu']
   # Do not race a still arriving input movie on cpu64.
   ready=s/'inputs'/mv/'READY'
   if os.environ.get('MC_WAIT_INPUTS')=='1':
    while not ready.exists():time.sleep(15)
   subprocess.run(cmd,env=env,check=True)
print('LANE DONE',a.shard,a.arms,flush=True)
