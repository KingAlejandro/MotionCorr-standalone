"""Bounded native B2 pilot. No full-census mode. Run only inside lane.py."""
import hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
import numpy as np
ROOT=Path('/tmp/motioncorr-b2-native-20261026');SRC=ROOT/'source';BIN=ROOT/'build/motioncorr'
OLD=Path('/tmp/motioncorr-damping-a1c78adc1d0f');PY=sys.executable
EVID=ROOT/'evidence';EVID.mkdir(exist_ok=True)
PIN=json.loads((ROOT/'input_pins.json').read_text());W8=json.loads((ROOT/'w8_refit.json').read_text())['movies']
sys.path[:0]=[str(SRC/'tools'),str(SRC/'test-data')]
from motion_field import read_motion_star
import check_realistic_motion as realistic
import check_motion_diagnostics as checker
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def check(ok,message):
 if not ok: (EVID/'STOP-v2').write_text(message+'\n');raise RuntimeError(message)
def admission(d):
 # Assess current occupancy, not merely the earlier lane snapshot.
 cp=subprocess.run(['ps','-eo','pid,ppid,psr,pcpu,args','--sort=-pcpu'],capture_output=True,text=True,check=True)
 (d/'occupancy-before.txt').write_text(cp.stdout)
 own={os.getpid()};records=[]
 for line in cp.stdout.splitlines()[1:]:
  fields=line.split(None,4)
  if len(fields)==5:records.append((int(fields[0]),int(fields[1]),int(fields[2]),float(fields[3]),fields[4]))
 changed=True
 while changed:
  old=len(own);own.update(pid for pid,ppid,_,_,_ in records if ppid in own);changed=len(own)!=old
 # Exclude our supervisors too. Reject observed active compute on our cores;
 # retain all-process snapshot so broad-affinity services remain visible.
 ancestors={os.getpid(),os.getppid()}
 for pid,ppid,cpu,pct,args in records:
  if pid not in own|ancestors and cpu in range(32,48) and pct>50:
   check(False,'foreign compute on allocated CPU: '+str((pid,cpu,pct,args)))
 scratch=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
 write(d/'admission.json',dict(affinity=sorted(os.sched_getaffinity(0)),scratch_bytes=scratch,limit_bytes=25*1024**3,assessment='no foreign >50% CPU process observed on CPUs32-47 in pre-run snapshot',utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
 check(scratch<=25*1024**3,'scratch cap exceeded');check(set(os.sched_getaffinity(0))==set(range(32,48)),'whole-chain affinity mismatch')
def run(name,fixture,movie,frames,patches,on,binary=BIN,extra=(),threads=8):
 d=EVID/name
 if name in ('K267/zero/BASE','K267/zero/OFF') and d.exists():
  row=json.loads((d/'RUN.json').read_text());check(row['exit']==0,'prior producer failed');write(d/'REUSED_BY_CONTROLS_V2.json',dict(reason='comparison-only path normalization amendment; producer NOT rerun',run_sha256=sha(d/'RUN.json')));return d,json.loads((d/'runtime.json').read_text()),row
 d.mkdir(parents=True,exist_ok=False)
 admission(d)
 out=d/'output';cmd=[str(binary),'--i',movie+'.star','--o',str(out),'--use_own','--j',str(threads),'--patch_x',str(patches),'--patch_y',str(patches),'--group_frames','1','--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum',str(frames),'--skip_logfile']
 if on:cmd+=['--experimental_local_b2']
 cmd+=list(extra)
 env={k:v for k,v in os.environ.items() if not k.startswith(('MC_DIAG_','MC_EXPERIMENT_'))}
 env.update(OMP_NUM_THREADS=str(threads),OPENBLAS_NUM_THREADS='1',MC_EXPERIMENT_CCF_DC_ARM='none',MC_DIAG_MODEL_OUT=str(d/'runtime.json'))
 t=time.monotonic()
 with (d/'stdout.log').open('w') as f:rc=subprocess.run(['/usr/bin/time','-v','-o',str(d/'time.txt'),*cmd],cwd=fixture,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 elapsed=time.monotonic()-t
 row=dict(argv=cmd,exit=rc,whole_job_seconds=elapsed,binary_sha256=sha(binary),affinity=sorted(os.sched_getaffinity(0)),threads=threads,environment={k:env[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MC_EXPERIMENT_CCF_DC_ARM')},publication={})
 for p in out.glob('*'):
  if p.is_file():row['publication'][p.name]=dict(bytes=p.stat().st_size,sha256=sha(p))
 write(d/'RUN.json',row);print(name,'exit',rc,'seconds',round(elapsed,3),flush=True)
 check(rc==0,name+': native exit '+str(rc));check((d/'runtime.json').exists(),name+': no capture')
 return d,json.loads((d/'runtime.json').read_text()),row

def products(a,b):
 for p in (a/'output').glob('*'):
  q=b/'output'/p.name
  check(q.exists(),'missing '+str(q))
  if p.suffix=='.star':check(p.read_bytes().replace(str(a/'output').encode(),b'@ROOT@')==q.read_bytes().replace(str(b/'output').encode(),b'@ROOT@'),'flags-off normalized STAR mismatch '+p.name)
  if p.suffix=='.mrc':
   x,y=p.read_bytes(),q.read_bytes();check(x[:224]==y[:224] and x[1024:]==y[1024:],'flags-off pixels/header mismatch '+p.name)

def k267_score(d,case,fixture):
 c=json.loads((fixture/'MANIFEST.json').read_text())['cases'][case];r=c['recipe'];y0,y1,x0,x1=c['roi']
 st=read_motion_star(d/'output'/f'{case}.star');rt=json.loads((d/'runtime.json').read_text());q=checker.gen.grid(r)
 model=st.copy();model.global_shift_x=np.array(rt['global'])[:,0];model.global_shift_y=np.array(rt['global'])[:,1]
 if rt['local_enabled']:model.coeff_x=np.array(rt['coeff_x']);model.coeff_y=np.array(rt['coeff_y'])
 truth=np.load(fixture/f'{case}_field.npy');out={}
 for label,m in [('runtime',model),('STAR',st)]:
  field=m.field(m.frames,q[...,0].ravel(),q[...,1].ravel()).reshape(r['frames'],r['ny'],r['nx'],2)
  metrics=checker.vector_metrics((field-truth)[:,y0:y1,x0:x1]*r['pixel_size']);metrics['verdict']='PASS' if all(metrics[k]<=v for k,v in [('rms',.2),('p95',.4),('max',.8)]) else 'FAIL';out[label]=metrics
 cp=subprocess.run([PY,str(SRC/'tools/check_motion_diagnostics.py'),'--fixtures',str(fixture),'--case',case,'--candidate',str(d/'output'/f'{case}.star'),'--summed-image',str(d/'output'/f'{case}.mrc'),'--json',str(d/'checker.json')],capture_output=True,text=True)
 (d/'checker.stdout').write_text(cp.stdout+cp.stderr);out['checker_exit']=cp.returncode
 write(d/'metrics.json',out);return out

def controls():
 fixture=OLD/'v2/v2fixtures';rows=[]
 for case in ('zero','integer','fractional','affine','pedestal','noisy','flat','repeated'):
  p=3 if case in ('affine','pedestal','noisy') else 1
  base,br,_=run('K267/'+case+'/BASE',fixture,case,5,p,False,OLD/'build-p1on/motioncorr',threads=2)
  off,fr,_=run('K267/'+case+'/OFF',fixture,case,5,p,False,threads=2);products(base,off)
  on,nr,_=run('K267/'+case+'/ON',fixture,case,5,p,True,threads=2)
  check(br==fr,case+': flags-off runtime differs');check(fr['global']==nr['global'],case+': global changed')
  fm,nm=k267_score(off,case,fixture),k267_score(on,case,fixture)
  rows.append(dict(case=case,OFF=fm,ON=nm));write(EVID/'k267_summary.json',rows)
 # N controls are global-only; preserve exact runtime+STAR with B2 flag.
 sys.path.insert(0,'/tmp/motioncorr-w5-20261025-7b76b848/scripts');import common as C
 nrows=[];fixture=OLD/'nc/movies'
 for wt in ('prod','iso'):
  for iv in (0,1):
   for n in (5,9,13,20):
    name=f'vel{iv}_N{n}';extra=['--experimental_isotropic_weight'] if wt=='iso' else []
    off,fr,_=run('N/'+wt+'/'+name+'/OFF',fixture,name,n,1,False,extra=extra,threads=2)
    on,nr,_=run('N/'+wt+'/'+name+'/ON',fixture,name,n,1,True,extra=extra,threads=2);products(off,on);check(fr==nr,name+': global-only runtime differs')
    truth=np.load(fixture/f'{name}_truth.npy');truth=np.broadcast_to(truth[:,None,None],(n,C.NY,C.NX,2))
    st=read_motion_star(on/'output'/f'{name}.star');gS=np.stack([st.global_shift_x,st.global_shift_y],axis=-1);gR=np.array(nr['global'])
    row=dict(movie=name,weight=wt,runtime=C.score(C.field(gR),truth),STAR=C.score(C.field(gS),truth),trajectory_rms_px=C.rms(gR-truth[:,0,0]))
    nrows.append(row);write(EVID/'n_summary.json',nrows)
 write(EVID/'CONTROLS_COMPLETE.json',dict(status='PASS',note='identity/infrastructure controls; scientific failures retained separately',k267_rows=len(rows),n_rows=len(nrows)))

def pilot():
 check((EVID/'CONTROLS_COMPLETE.json').exists(),'controls incomplete')
 for name in ('dose1-s01','dose05-s00','dose4-s00','pedestal32-s00'):
  wanted=PIN[name]['receipt'];fixture=ROOT/'movie';check(not fixture.exists(),'scratch movie already exists')
  KM=Path('/home/ubuntu/mc-km-truth-20261021');cond,seed=name.rsplit('-s',1);key='inmodel'
  code=f'import sys;from pathlib import Path;K=Path({str(KM)!r});sys.path[:0]=[str(K/"v2/test-data"),str(K/"deps")];import generate_realistic_motion as g;g.generate(g.recipe({cond!r},{int(seed)}),K/"expectations"/"{key}.npy",Path({str(fixture)!r}))'
  with (EVID/(name+'-generation.log')).open('w') as log:rc=subprocess.run([PY,'-c',code],stdout=log,stderr=subprocess.STDOUT).returncode
  check(rc==0,name+': generator exit');check(sha(fixture/'movie.mrcs')==wanted['files']['movie.mrcs'],name+': movie SHA mismatch')
  write(EVID/(name+'-input.json'),dict(movie_sha256=sha(fixture/'movie.mrcs'),recipe=wanted['recipe'],receipt_sha256=sha(fixture/'RECEIPT.json')))
  # input.star is the frozen generator name; the native output stem is movie.
  shutil.copyfile(fixture/'input.star',fixture/'movie.star')
  order=[('OFF1',False),('ON1',True),('ON2',True),('OFF2',False),('OFF_AA1',False),('OFF_AA2',False),('OFF_AA3',False),('OFF_AA4',False)] if name=='dose1-s01' else [('OFF1',False),('ON1',True)]
  first=None;first_rt=None;summary=[]
  for label,on in order:
   d,rt,row=run('pilot/'+name+'/'+label,fixture,'movie',40,5,on,extra=['--ingest','float'])
   cp=subprocess.run([PY,str(SRC/'tools/check_realistic_motion.py'),'--receipt',str(fixture/'RECEIPT.json'),'--runtime',str(d/'runtime.json'),'--star',str(d/'output/movie.star'),'--log',str(d/'output/movie.log'),'--json',str(d/'metrics.json')],capture_output=True,text=True)
   (d/'score.stdout').write_text(cp.stdout+cp.stderr);check(cp.returncode==0,name+': scorer failed');m=json.loads((d/'metrics.json').read_text());check(m['sampling_status']=='VALID',name+': sampling failed')
   if first is None:
    first=d;first_rt=rt;check((d/'output/movie.star').read_bytes()==(ROOT/'h7_inputs'/name/'movie.star').read_bytes(),name+': OFF STAR identity defect')
    check(rt==json.loads((ROOT/'h7_inputs'/name/'runtime.json').read_text()),name+': OFF runtime identity defect')
   else:
    check(rt['global']==first_rt['global'],name+': global changed')
    def observations(p):
     text=p.read_text();return text.split('data_local_shift',1)[-1].split('data_')[0] if 'data_local_shift' in text else ''
    check(observations(d/'output/movie.star')==observations(first/'output/movie.star'),name+': observations changed')
   delta=0.
   if on:
    expected={'dose1-s01':'PASS','dose05-s00':'FAIL','dose4-s00':'PASS','pedestal32-s00':'FAIL'}[name]
    check(m['field_distance_status']==expected,name+': unexpected truth gate')
    w=W8[name];wm=dict(global_=rt['global'])
    if w['status']=='NO_LOCAL_RETAINED':check(rt==first_rt,name+': no-local changed')
    else:
     model=dict(rt,coeff_x=w['coeff_x'],coeff_y=w['coeff_y']);r=wanted['recipe'];x,y=np.meshgrid(np.linspace(32,r['nx']-33,129),np.linspace(32,r['ny']-33,129));a=realistic.runtime_field(rt,r,x.ravel(),y.ravel());b=realistic.runtime_field(model,r,x.ravel(),y.ravel());delta=float(np.linalg.norm(a-b,axis=-1).max());check(delta<=.013131428741,name+': W8 comparison threshold exceeded')
   summary.append(dict(label=label,on=on,seconds=row['whole_job_seconds'],runtime=m['field']['angstrom'],STAR=m['serialized_field']['angstrom'],runtime_gate=m['field_distance_status'],local_enabled=m['local_enabled'],convergence=m['convergence'],W8_max_vector_difference_px=delta));write(EVID/(name+'-summary.json'),summary)
   print(name,label,m['field_distance_status'],m['field']['angstrom'],'W8delta',delta,flush=True)
   # Preserve scientific images durably (14*64MiB total); remove only generated input after all pairs.
  shutil.rmtree(fixture)
 write(EVID/'PILOT_COMPLETE.json',dict(status='COMPLETE',full100='UNRUN'))
if __name__=='__main__':
 check(not (EVID/'STOP-v2').exists(),'STOP-v2 exists; no blind retry')
 if (EVID/'STOP').exists():check((EVID/'STOP').read_text()=='flags-off STAR mismatch corrected_micrographs.star\n','unexpected original STOP')
 {'controls':controls,'pilot':pilot}[sys.argv[1]]()
