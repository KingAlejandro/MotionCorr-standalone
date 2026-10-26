"""Retained-data-only diagnosis after the K267 noisy regression; no native producers."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path('/tmp/motioncorr-b2-native-20261026');SRC=ROOT/'source';OLD=Path('/tmp/motioncorr-damping-a1c78adc1d0f')
sys.path[:0]=[str(ROOT),str(SRC/'tools'),str(SRC/'test-data')]
import w8_fit as W
from motion_field import read_motion_star
import check_motion_diagnostics as C
import check_realistic_motion as R
out={}
for case in ('affine','noisy'):
 base=ROOT/'evidence/K267'/case;off=base/'OFF';on=base/'ON-v3';r=json.loads((OLD/'v2/v2fixtures/MANIFEST.json').read_text())['cases'][case]['recipe']
 def observations(path):
  text=path.read_text();block=text.split('data_local_shift',1)[1];rows=[]
  for line in block.splitlines():
   w=line.split()
   if len(w)==5 and not w[0].startswith(('_','#')):rows.append([float(a) for a in w])
  return np.array(rows),block
 a,oa=observations(off/'output'/f'{case}.star');b,ob=observations(on/'output'/f'{case}.star')
 keys=sorted({(v[1],v[2]) for v in a});obs=np.zeros((len(keys),r['frames'],2))
 for row in a:obs[keys.index((row[1],row[2])),int(row[0])-1]=row[3:]
 uv=np.array(keys)/np.array([r['nx'],r['ny']])-.5;fit=W.fit(obs,uv[:,0],uv[:,1],'B2')
 rt=json.loads((on/'runtime.json').read_text());fr=json.loads((off/'runtime.json').read_text());q=C.gen.grid(r);u=q[...,0].ravel()/r['nx']-.5;v=q[...,1].ravel()/r['ny']-.5
 native=W.field(np.array([rt['coeff_x'],rt['coeff_y']]),u,v,r['frames']);offline=W.field(fit['coeff'],u,v,r['frames'])
 truth=np.load(OLD/'v2/v2fixtures'/f'{case}_field.npy');field=native.reshape(r['frames'],r['ny'],r['nx'],2)+np.array(rt['global'])[:,None,None,:];err=np.linalg.norm(field-truth,axis=-1);worst=np.unravel_index(err.argmax(),err.shape)
 out[case]=dict(observation_block_byte_equal=oa==ob,global_exact=rt['global']==fr['global'],local_enabled_OFF=fr['local_enabled'],local_enabled_ON=rt['local_enabled'],OFF_convergence=R.convergence(off/'output'/f'{case}.log'),ON_convergence=R.convergence(on/'output'/f'{case}.log'),rank=fit['rank'],n_cols=fit['n_cols'],native_vs_independent_W8_B2_STARobs_max_vector_px=float(np.linalg.norm(native-offline,axis=-1).max()),native_max_full_border_error_px=float(err.max()),worst_full_border_frame_y_x=[int(x) for x in worst])
npast=OLD/'nc/runs/a-prod-iso/vel1_N20.runtime.json';nnow=ROOT/'evidence/N/iso/vel1_N20/ON-v3/runtime.json';out['harmful_N20_native_runtime_matches_retained_PR286']=json.loads(npast.read_text())==json.loads(nnow.read_text())
out['w8_fit_sha256']=hashlib.sha256((ROOT/'w8_fit.py').read_bytes()).hexdigest()
(ROOT/'evidence/tiny_diagnosis.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
