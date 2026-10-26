"""Preregistered retained-only linear-operator challenge; no native producers."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
BUNDLE=Path(sys.argv[1]);REPO=Path(sys.argv[2]);W8=Path(sys.argv[3]);OUT=Path(sys.argv[4])
sys.path[:0]=[str(W8),str(REPO/'tools')]
import w8_fit as W
from check_motion_diagnostics import vector_metrics
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def summary(field,roi,pix):
 y0,y1,x0,x1=roi
 def m(a):return dict(px=vector_metrics(a),angstrom=vector_metrics(a*pix))
 norms=np.linalg.norm(field,axis=-1);idx=np.unravel_index(norms.argmax(),norms.shape)
 return dict(ROI=m(field[:,y0:y1,x0:x1]),full_border_domain=m(field),max_frame_y_x=[int(x) for x in idx])
rows={};manifest=json.loads((BUNDLE/'v2fixtures/MANIFEST.json').read_text())
for case in ('affine','noisy'):
 root=BUNDLE/'evidence/K267'/case;r=manifest['cases'][case]['recipe'];roi=manifest['cases'][case]['roi'];ny,nx,nf=r['ny'],r['nx'],r['frames'];pix=r['pixel_size']
 text=(root/'OFF/output'/f'{case}.star').read_text();local=text.split('data_local_shift')[1];a=[]
 for line in local.splitlines():
  w=line.split()
  if len(w)==5 and not w[0].startswith(('_','#')):a.append([float(v) for v in w])
 a=np.array(a);keys=sorted({(x[1],x[2]) for x in a});obs=np.zeros((len(keys),nf,2))
 for row in a:obs[keys.index((row[1],row[2])),int(row[0])-1]=row[3:]
 keys=np.array(keys);u,v=keys[:,0]/nx-.5,keys[:,1]/ny-.5
 xx,yy=np.meshgrid(np.arange(nx),np.arange(ny));lu,lv=xx.ravel()/nx-.5,yy.ravel()/ny-.5
 physical=(W.spatial(lu,lv)[:,None,:,None]*W.temporal(nf,'B2')[None,:,None,:]).reshape(18,len(lu)*nf).T
 # design rows are point,frame; convert consistently to frame,y,x below.
 def publish(coeff):return W.field(np.array(coeff).T,lu,lv,nf).reshape(nf,ny,nx,2)
 truth=np.load(BUNDLE/'v2fixtures'/f'{case}_field.npy');rt={label:json.loads((root/arm/'runtime.json').read_text()) for label,arm in [('OFF','OFF'),('ON','ON-v3')]}
 g=np.array(rt['OFF']['global']);gt=truth[:,ny//2,nx//2]
 tp=truth[:,keys[:,1].astype(int),keys[:,0].astype(int)].transpose(1,0,2)
 oracle=tp-g[None,:,:];oracle=oracle+.5*oracle[:,1:2]
 oracle_trueg=tp-gt[None,:,:];oracle_trueg=oracle_trueg+.5*oracle_trueg[:,1:2]
 row=dict(recipe=r,ROI=roi,patches=len(keys),global_exact=rt['OFF']['global']==rt['ON']['global'],arms={})
 fields={};operators={}
 for label,arm in [('OFF','native'),('ON','B2')]:
  A=W.design(u,v,nf,arm);inv=np.linalg.pinv(A);P=inv[:18];nativecoeff=np.array([rt[label]['coeff_x'],rt[label]['coeff_y']]).T
  fit=lambda z: np.linalg.lstsq(A,z.reshape(-1,2),rcond=None)[0][:18]
  obs_field=publish(fit(obs));oracle_field=publish(fit(oracle));truthg_field=publish(fit(oracle_trueg))
  native_field=publish(nativecoeff)+g[:,None,None,:];fields[label]=native_field
  projection_error=oracle_field+g[:,None,None,:]-truth
  discrepancy=publish(fit(obs-oracle));observed_error=obs_field+g[:,None,None,:]-truth
  global_error=oracle_field+g[:,None,None,:]-(truthg_field+gt[:,None,None,:])
  H=physical@P;operators[label]=H;l1=np.abs(H).sum(axis=1);l2=np.linalg.norm(H,axis=1)
  raw=np.linalg.svd(A,compute_uv=False);sc=np.linalg.svd(A/np.linalg.norm(A,axis=0),compute_uv=False)
  native_vs_independent=native_field-(obs_field+g[:,None,None,:]);bound=float(2**.5*5e-6*l1.max())
  checker=json.loads((root/('OFF' if label=='OFF' else 'ON-v3')/'checker.json').read_text())
  row['arms'][label]=dict(rank=int(np.linalg.matrix_rank(A)),n_cols=A.shape[1],condition_raw=float(raw[0]/raw[-1]),condition_scaled=float(sc[0]/sc[-1]),local_enabled=rt[label]['local_enabled'],checker_classes={k:checker.get(k) for k in ('accuracy_status','sampling_status','identifiability_status','application_consistency','signal')},native_field_error=summary(native_field-truth,roi,pix),independent_field_error=summary(observed_error,roi,pix),native_vs_independent=summary(native_vs_independent,roi,pix),rounding_vector_bound_px=bound,native_within_diagnostic_rounding_bound=bool(np.linalg.norm(native_vs_independent,axis=-1).max()<=bound+1e-8),operator_max_row_L1=float(l1.max()),operator_max_row_L2=float(l2.max()),perfect_observation_projection_error=summary(projection_error,roi,pix),propagated_observation_discrepancy=summary(discrepancy,roi,pix),unabsorbed_global_error=summary(global_error,roi,pix),true_global_perfect_observation_error=summary(truthg_field+gt[:,None,None,:]-truth,roi,pix),decomposition_max_abs_error=float(np.abs(observed_error-projection_error-discrepancy).max()))
 delta=operators['ON']-operators['OFF'];row['difference_operator_max_row_L1']=float(np.abs(delta).sum(axis=1).max());row['difference_operator_max_row_L2']=float(np.linalg.norm(delta,axis=1).max());row['ON_minus_OFF_field']=summary(fields['ON']-fields['OFF'],roi,pix)
 rows[case]=row
result=dict(plan_sha256=sha(REPO/'docs/post_rc0/s1/native_b2_20261026/TINY_DIAGNOSTIC_PLAN.md'),w8_fit_sha256=sha(W8/'w8_fit.py'),numpy=np.__version__,cases=rows,interpretation='Retained-data characterization only. Observation discrepancy is not isolated stochastic noise. No native producer, acceptance change or promotion.')
OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({case:{label:dict(ROIerror=r['arms'][label]['native_field_error']['ROI']['angstrom'],projection=r['arms'][label]['perfect_observation_projection_error']['ROI']['angstrom'],discrepancy=r['arms'][label]['propagated_observation_discrepancy']['ROI']['angstrom'],global_error=r['arms'][label]['unabsorbed_global_error']['ROI']['angstrom'],gain=r['arms'][label]['operator_max_row_L2'],native_rounding_bound_ok=r['arms'][label]['native_within_diagnostic_rounding_bound']) for label in ('OFF','ON')} for case,r in rows.items()},indent=2))
