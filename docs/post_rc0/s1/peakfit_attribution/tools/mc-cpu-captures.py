import json,pathlib,os,subprocess
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit')
e=dict(os.environ,S13C_ROOT=str(s),LANE_GPU='0',MC_SOURCE_SHA='4837b2100bcbf436cb88896a50a082f788bb3e29',MC_CPU_MASK='80-87',MC_CPU_LOCK='/tmp/motioncorr-owned-cpu-validation.lock')
for r in json.load(open(s/'rows-4gpus.json')):
 if not any(r['arms'].get(a,{}).get('relative_rmse',0)>=.1 for a in ['A1','A2']):continue
 mv,g=r['movie'],r['grid'];label='%s-p%d-cpu'%(mv,g)
 subprocess.run(['/usr/bin/python3',str(s/'tools/run_c.py'),'--sweep-label','%s-p%d-F-cuda'%(mv,g),'--label',label,'--binary',str(s/'build-A0/motioncorr'),'--env','MC_DIAG_CCF={out}/ccf.txt','--env','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt'],env=e,check=True)
 # Reconstructed CPU product is a capture control, primary ref stays the sweep.
 a='/mnt/clathrin/alex-motioncorr-s1/sweep/runs/%s-p%d-F-cpu'%(mv,g)
 p=subprocess.run(['/usr/bin/python3',str(s/'tools/identity.py'),a,str(s/'runs'/label)],capture_output=True,text=True,check=True)
 (s/'runs'/label/'identity-sweep-cpu.json').write_text(p.stdout)
print('DONE')
