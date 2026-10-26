"""Pinned helpers for the evidence-only upstream × B2 factorial."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
ROOT=Path(os.environ.get('B2_FACTORIAL_ROOT','/tmp/motioncorr-b2-factorial-20261026'))
EVID=ROOT/'evidence';SRC=Path('/tmp/motioncorr-b2-native-20261026/source')
SEALED=Path('/home/ubuntu/motioncorr-evidence/native-b2-20261026')
OLD=Path('/tmp/motioncorr-damping-a1c78adc1d0f');FIX=OLD/'v2/v2fixtures'
BIN=Path('/tmp/motioncorr-b2-native-20261026/build/motioncorr');PY=sys.executable
ORDER=('noisy','affine','pedestal','zero','integer','fractional','flat','repeated')
PINS=json.loads((ROOT/'PINS.json').read_text())
sys.path[:0]=[str(ROOT),str(SRC/'tools'),str(SRC/'test-data')]
from motion_field import read_motion_star
import check_motion_diagnostics as C
import check_realistic_motion as R

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def write(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def check(ok,message):
 if not ok:
  path=EVID/'STOP.json'
  if not path.exists():write(path,dict(reason=message,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
  raise RuntimeError(message)
def validate_pins():
 check(sha(BIN)==PINS['binary_sha256'],'binary hash changed')
 check(sha(SEALED/'RAW_INDEX.json')==PINS['sealed_raw_index_sha256'],'sealed reference index changed')
 for name,want in PINS['source_and_tool_files'].items():check(sha(name)==want,'source/tool hash changed: '+name)
 for name,want in PINS['fixture_files'].items():
  p=Path(name);check(p.stat().st_size==want['bytes'] and sha(p)==want['sha256'],'fixture hash changed: '+name)
def sealed_case(case,b2):return SEALED/'evidence/K267'/case/('ON-v3' if b2 else 'OFF')
def verify_reused(case,b2):
 d=sealed_case(case,b2);pins=PINS['sealed_base_outputs'][case]['ON-v3' if b2 else 'OFF']
 for name,want in pins.items():
  p=d/name;check(p.stat().st_size==want['bytes'] and sha(p)==want['sha256'],'reused output changed: '+str(p))
 return d
def admission(d):
 cp=subprocess.run(['ps','-eo','pid,ppid,psr,pcpu,args','--sort=-pcpu'],capture_output=True,text=True,check=True)
 (d/'occupancy-before.txt').write_text(cp.stdout)
 records=[line.split(None,4) for line in cp.stdout.splitlines()[1:]]
 records=[(int(v[0]),int(v[1]),int(v[2]),float(v[3]),v[4]) for v in records if len(v)==5]
 own={os.getpid(),os.getppid()}
 while True:
  prior=len(own);own.update(pid for pid,ppid,*_ in records if ppid in own)
  if len(own)==prior:break
 for pid,ppid,cpu,pct,args in records:
  check(not(pid not in own and cpu in range(32,48) and pct>50),'foreign compute on allocated CPU: '+str((pid,cpu,pct,args)))
 leases=json.loads(os.environ['MOTIONCORR_HELD_LEASES']);affinity=sorted(os.sched_getaffinity(0))
 check('/tmp/motioncorr-cpu64-bench.lock' in leases,'canonical bench lease absent')
 check(affinity==list(range(32,48)),'whole-chain affinity differs')
 task_bytes=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
 prior_bytes=sum(p.stat().st_size for p in Path('/tmp/motioncorr-b2-native-20261026').rglob('*') if p.is_file())
 check(task_bytes+prior_bytes<=25*1024**3,'combined scratch cap exceeded')
 write(d/'admission.json',dict(acquired_locks=leases,affinity=affinity,requested_native_threads=2,task_scratch_bytes=task_bytes,prior_retained_scratch_bytes=prior_bytes,combined_limit_bytes=25*1024**3,assessment='no foreign >50% CPU compute observed on allocated cores at per-job admission',utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
def star_blocks(path):
 blocks={};name=None
 for line in path.read_text().splitlines(keepends=True):
  if line.startswith('data_'):name=line.strip()[5:];blocks[name]=''
  if name is not None:blocks[name]+=line
 return blocks
def observations(path,nf):
 block=star_blocks(path).get('local_shift','');rows=[]
 for line in block.splitlines():
  words=line.split()
  if len(words)==5 and not words[0].startswith(('_','#','data_')):rows.append([float(v) for v in words])
 keys=sorted({(a[1],a[2]) for a in rows});obs=np.full((len(keys),nf,2),np.nan)
 for a in rows:
  p=keys.index((a[1],a[2]));f=int(a[0])-1
  check(0<=f<nf and np.isnan(obs[p,f]).all(),'duplicate/out-of-range observation')
  obs[p,f]=a[3:]
 check(np.isfinite(obs).all(),'nonfinite/incomplete observation capture')
 return np.asarray(keys).reshape(-1,2),obs

def manipulation(path):
 text=path.read_text();pattern=r'MC_EXPERIMENT_CCF_DC arm=(\w+) cpu.global=(\d+)/(\d+) cpu.local=(\d+)/(\d+)'
 matches=re.findall(pattern,text);check(len(matches)==1,'missing/duplicate final DC counters')
 arm,gz,ge,lz,le=matches[0];dc=dict(arm=arm,global_zeroed=int(gz),global_eligible=int(ge),local_zeroed=int(lz),local_eligible=int(le))
 check(arm=='both' and dc['global_zeroed']==dc['global_eligible']>0 and dc['local_zeroed']==dc['local_eligible'],'DC manipulation failed')
 coupled={'global':dict(peaks=0,guard_fired=0,not_negative_definite=0,offset_gt_1px=0),'patch':dict(peaks=0,guard_fired=0,not_negative_definite=0,offset_gt_1px=0)}
 pat=r'\[coupled_peak\] scope=(\w+) peaks=(\d+) guard_fired=(\d+) \(not_negative_definite=(\d+), offset_gt_1px=(\d+)\)'
 entries=re.findall(pat,text);check(bool(entries),'coupled manipulation counters absent')
 for scope,peaks,guard,negative,offset in entries:
  values=list(map(int,(peaks,guard,negative,offset)));check(scope in coupled and values[1]==values[2]+values[3],'inconsistent coupled counters')
  for key,val in zip(coupled[scope],values):coupled[scope][key]+=val
 check(coupled['global']['peaks']==dc['global_eligible'] and coupled['patch']['peaks']==dc['local_eligible'],'coupled/DC eligible count mismatch')
 return dict(dc=dc,coupled=coupled)
def gate(aa):return 'PASS' if all(aa[k]<=v for k,v in [('rms',.20),('p95',.40),('max',.80)]) else 'FAIL'
def model_field(rt,r):
 xx,yy=np.meshgrid(np.arange(r['nx']),np.arange(r['ny']))
 return R.runtime_field(rt,r,xx.ravel(),yy.ravel()).reshape(r['frames'],r['ny'],r['nx'],2)
def metrics(d,case):
 manifest=json.loads((FIX/'MANIFEST.json').read_text());c=manifest['cases'][case];r=c['recipe'];y0,y1,x0,x1=c['roi']
 rt=json.loads((d/'runtime.json').read_text());st=read_motion_star(d/'output'/f'{case}.star')
 truth=np.load(FIX/f'{case}_field.npy');field=model_field(rt,r);q=C.gen.grid(r)
 sf=st.field(st.frames,q[...,0].ravel(),q[...,1].ravel()).reshape(truth.shape)
 check(np.isfinite(field).all() and np.isfinite(sf).all(),'nonfinite published field')
 result={}
 for label,a in [('runtime',field),('STAR',sf)]:
  aa=C.vector_metrics((a-truth)[:,y0:y1,x0:x1]*r['pixel_size']);result[label]=dict(angstrom=aa,gate=gate(aa),px=C.vector_metrics((a-truth)[:,y0:y1,x0:x1]),per_frame_angstrom=[C.vector_metrics(e[y0:y1,x0:x1]*r['pixel_size']) for e in a-truth])
 result['roundtrip_vector_max_px']=float(np.linalg.norm(field-sf,axis=-1).max())
 result['local_enabled']=rt['local_enabled'];result['convergence']=R.convergence(d/'output'/f'{case}.log')
 return result
