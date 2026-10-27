"""Direct truth-accessible physical RMS projection; never a candidate fitter."""
from pathlib import Path
import hashlib,json,sys,time
sys.dont_write_bytecode=True
import numpy as np
import score_fields as S

HERE=Path(__file__).parent
RAW=Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
FIX=Path('/tmp/motioncorr-b2-retained-challenge-20261026/v2fixtures')
PLAN=HERE/'ORACLE_FLOOR_PLAN.md'
assert S.sha(FIX/'MANIFEST.json')=='9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
manifest=json.loads((FIX/'MANIFEST.json').read_text())
inputs=[PLAN,FIX/'MANIFEST.json']+[p for case in ['affine','noisy'] for p in [FIX/f'{case}_field.npy',RAW/case/'UP_only/runtime.json',RAW/case/'UP_only/output'/f'{case}.star']]
before={str(p):S.sha(p) for p in inputs}
start=time.perf_counter();rows=[]
for case in ['affine','noisy']:
 meta=manifest['cases'][case];r=meta['recipe'];y0,y1,x0,x1=meta['roi']
 assert (r['frames'],r['ny'],r['nx'],meta['roi'])==(5,96,128,[12,84,12,116])
 truth=np.load(FIX/f'{case}_field.npy',allow_pickle=False)[:,y0:y1,x0:x1].reshape(-1,2)
 assert S.sha(FIX/f'{case}_field.npy')=='839c484f08ced435120a3f7c60267b95959bc5c06993f7c3015d61ffa3b95799'
 yy,xx=np.mgrid[y0:y1,x0:x1];u=xx.ravel()/r['nx']-.5;v=yy.ravel()/r['ny']-.5
 spatial=np.array([np.ones_like(u),u,u*u,v,v*v,u*v]).T
 f=np.arange(r['frames'],dtype=float);temporal=np.array([f,f*f,f*f*f]).T
 A=np.einsum('fs,pk->fpks',temporal,spatial).reshape(-1,18)
 scale=np.linalg.norm(A,axis=0);As=A/scale
 rawsv=np.linalg.svd(A,compute_uv=False)
 model=json.loads((RAW/case/'UP_only/runtime.json').read_text())
 st=S.read_motion_star(RAW/case/'UP_only/output'/f'{case}.star')
 for label,G,native in [('runtime',np.array(model['global']),S.R.runtime_field(model,r,xx.ravel(),yy.ravel()).reshape(-1,2)),('STAR',np.column_stack([st.global_shift_x,st.global_shift_y]),st.field(st.frames,xx.ravel(),yy.ravel()).reshape(-1,2))]:
  gb=np.broadcast_to(G[:,None,:],(r['frames'],u.size,2)).reshape(-1,2)
  target=truth-gb
  scaled,_,rank,sv=np.linalg.lstsq(As,target,rcond=None)
  assert rank==18
  coeff=scaled/scale[:,None]
  residual=A@coeff-target
  orth=float(np.linalg.norm(As.T@residual)/max(np.linalg.norm(As)*np.linalg.norm(target),np.finfo(float).tiny))
  assert orth<=1e-10,orth
  direct=np.zeros_like(gb).reshape(r['frames'],u.size,2)
  for k in range(6):
   for s in range(3):direct+=temporal[:,s,None,None]*spatial[None,:,k,None]*coeff[3*k+s]
  direct=direct.reshape(-1,2)+gb-truth
  closure=float(np.max(np.abs(direct-residual)))
  assert closure<=1e-10,closure
  metrics=S.C.vector_metrics(residual*r['pixel_size'])
  current=S.C.vector_metrics((native-truth)*r['pixel_size'])
  assert current['rms']+1e-12>=metrics['rms']
  # Independent N5 temporal null-vector projection. Spatial content of actual
  # truth must first be verified representable; the temporal shortcut is not assumed.
  tv=np.array([0.,-4.,6.,-4.,1.]);tv/=np.linalg.norm(tv)
  expected=np.einsum('f,fpa->pa',tv,target.reshape(5,u.size,2))[None,:,:]*tv[:,None,None]
  expected[0]= -target.reshape(5,u.size,2)[0]
  null_closure=float(np.max(np.abs(residual.reshape(5,u.size,2)+expected)))
  assert null_closure<=1e-10,null_closure
  rows.append({'case':case,'fixed_global':label,'raw_singular_values':rawsv.tolist(),'scaled_singular_values':sv.tolist(),'rank':int(rank),'raw_condition':float(rawsv[0]/rawsv[-1]),'scaled_condition':float(sv[0]/sv[-1]),'relative_orthogonality':orth,'reconstruction_closure_px':closure,'independent_temporal_null_closure_px':null_closure,'rms_floor_A':metrics['rms'],'p95_at_RMS_optimum_A_NOT_FLOOR':metrics['p95'],'max_at_RMS_optimum_A_NOT_FLOOR':metrics['max'],'existing_native_metrics_A':current,'joint_gate_impossible_for_fixed_global_family':bool(metrics['rms']>.20),'oracle_coefficients_px':coeff.tolist()})
after={str(p):S.sha(p) for p in inputs};assert before==after
result={'scope':'Oracle only: truth-accessible physical-field RMS projection on fixed G + native18 local coefficients. No floor subtraction, candidate fit, percentile floors or native/movie run.','rows':rows,'input_hashes_before':before,'input_hashes_after':after,'elapsed_s':time.perf_counter()-start,'python':sys.version,'numpy':np.__version__}
(HERE/'ORACLE_FLOOR_RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps([{k:r[k] for k in ['case','fixed_global','rms_floor_A','rank','joint_gate_impossible_for_fixed_global_family']} for r in rows]))
