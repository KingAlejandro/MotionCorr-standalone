import os,pathlib,subprocess
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-dc-oracle');sha=(s/'source-sha.txt').read_text().strip()
for mv,g in [('e10216-00',3),('e12963-00',5)]:
 for a,dc in [('R','none'),('Rprime','both')]:
  label=f'{mv}-p{g}-capture-{a}';(s/'runs'/label/'maps').mkdir(parents=True,exist_ok=True)
  cmd=['python3',str(s/'tools/run.py'),'--sweep-label',f'{mv}-p{g}-F-cuda','--label',label,'--binary',str(s/'build/motioncorr')]
  for v in ['MC_DIAG_CCF_DC='+dc,'MC_DIAG_CCF_DOUBLE=1','MC_DIAG_CCF={out}/ccf.txt','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt','MC_DIAG_MODEL_OUT={out}/model.txt','MC_DIAG_MAPS={out}/maps','MC_DIAG_MAP_PATCHES=1,1']:cmd+=['--env',v]
  subprocess.run(cmd,env=dict(os.environ,S13C_ROOT=str(s),S13C_SWEEP=str(s/'recipes'),MC_SOURCE_SHA=sha,MC_CPU_MASK='40-47',MC_CPU_LOCK='/tmp/motioncorr-dc-oracle-cpu-40-47.lock'),check=True)
