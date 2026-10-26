"""Frozen same-observation W8 cross-feed, coverage and conditional error decomposition."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from factorial_common import *
import w8_fit as W

METRICS=('rms','p95','max')
def stats(a,roi,pix):
 y0,y1,x0,x1=roi;inside=a[:,y0:y1,x0:x1];mask=np.ones(a.shape[1:3],dtype=bool);mask[y0:y1,x0:x1]=False
 norms=np.linalg.norm(a,axis=-1);idx=np.unravel_index(norms.argmax(),norms.shape)
 return dict(ROI_px=C.vector_metrics(inside),ROI_A=C.vector_metrics(inside*pix),border_excluding_ROI_px=C.vector_metrics(a[:,mask]),full_domain_px=C.vector_metrics(a),full_domain_max_frame_y_x=[int(x) for x in idx],per_frame_ROI_A=[C.vector_metrics(e*pix) for e in inside])
def mean_square(a):return float(np.mean(np.sum(a*a,axis=-1)))
def components(terms,roi,pix):
 y0,y1,x0,x1=roi;sl={k:a[:,y0:y1,x0:x1]*pix for k,a in terms.items()};keys=list(sl)
 ms={k:mean_square(v) for k,v in sl.items()};cross={f'{a}__{b}':float(2*np.mean(np.sum(sl[a]*sl[b],axis=-1))) for i,a in enumerate(keys) for b in keys[i+1:]}
 total=sum(sl.values());return dict(standalone_MS_A2=ms,cross_terms_A2=cross,total_MS_A2=mean_square(total),MS_closure_error_A2=float(mean_square(total)-sum(ms.values())-sum(cross.values())))
def eta_report(keys,obs,g,truth):
 nf=len(g);tp=truth[:,keys[:,1].astype(int),keys[:,0].astype(int)].transpose(1,0,2)
 L=obs[:,1:]-obs[:,0:1];ideal=tp[:,1:]-g[None,1:];eta=L-ideal;norm=np.linalg.norm(eta,axis=-1)
 values=[]
 for p,(x,y) in enumerate(keys):values.append(dict(x=float(x),y=float(y),frames=[1,2,3,4],eta_xy_px=eta[p].tolist(),eta_norm_px=norm[p].tolist(),L_xy_px=L[p].tolist(),ideal_L_xy_px=ideal[p].tolist()))
 return dict(accepted_coordinates=keys.tolist(),all_patch_frame_discrepancies=values,per_frame_px=[C.vector_metrics(eta[:,f]) for f in range(nf-1)],g4_max_vector_discrepancy_px=float(norm[:,-1].max()),all_frames_max_vector_discrepancy_px=float(norm.max()),Tr_constraint_max_abs_px=float(np.abs(obs[:,1]-3*obs[:,0]).max()))
def crossfeed(case,label,d,targets):
 manifest=json.loads((FIX/'MANIFEST.json').read_text());c=manifest['cases'][case];r=c['recipe'];roi=c['roi'];nf,ny,nx=r['frames'],r['ny'],r['nx'];pix=r['pixel_size']
 keys,obs=observations(d/'output'/f'{case}.star',nf);rt=json.loads((d/'runtime.json').read_text());g=np.array(rt['global']);truth=np.load(FIX/f'{case}_field.npy')
 if not len(keys):
  check(not rt['local_enabled'],'local model enabled without observations');return dict(status='GLOBAL_ONLY_NO_LOCAL_OBSERVATIONS',accepted_coordinates=[],operators='NOT_APPLICABLE',global_sha256=sha(d/'runtime.json'))
 u,v=keys[:,0]/nx-.5,keys[:,1]/ny-.5;S=W.spatial(u,v).T
 check(np.linalg.matrix_rank(S)==6,'spatial rank deficiency')
 row=dict(status='LOCAL_CROSSFEED',patches=len(keys),spatial_rank=6,accepted_coordinates=keys.tolist(),tracking=eta_report(keys,obs,g,truth),operators={})
 yy,xx=np.mgrid[:ny,:nx];lu,lv=xx.ravel()/nx-.5,yy.ravel()/ny-.5
 Sd=W.spatial(lu,lv).T;ct=np.linalg.lstsq(Sd,truth.reshape(nf,-1,2).transpose(1,0,2).reshape(len(lu),nf*2),rcond=None)[0].reshape(6,nf,2)
 gt=ct[0];truth_projected=(Sd@ct.reshape(6,nf*2)).reshape(ny,nx,nf,2).transpose(2,0,1,3)
 row['truth_spatial_projection_max_abs_px']=float(np.abs(truth_projected-truth).max())
 tp=truth[:,keys[:,1].astype(int),keys[:,0].astype(int)].transpose(1,0,2)
 Tr=lambda a:a+.5*a[:,1:2]
 residual=tp-g[None,:,:];oracle=Tr(residual);true_residual=tp-gt[None,:,:];dg=g-gt
 Lfull=np.concatenate([np.zeros((len(keys),1,2)),obs[:,1:]-obs[:,0:1]],axis=1)
 eta=Lfull-residual;serial=obs-Tr(Lfull)
 phi=(W.spatial(lu,lv)[:,None,:,None]*W.temporal(nf,'B2')[None,:,None,:]).reshape(18,len(lu)*nf).T
 for name,arm,target in [('OFF','native',targets[0]),('B2','B2',targets[1])]:
  A=W.design(u,v,nf,arm);P=np.linalg.pinv(A)[:18];rank=int(np.linalg.matrix_rank(A))
  check(rank==A.shape[1] and nf>=4,'cross-feed full design rank deficient')
  sol=W.fit(obs,u,v,arm);check(sol['rank']==sol['n_cols'],'W8 fit rank deficient')
  def apply(y):return W.field((P@y.reshape(-1,2)).T,lu,lv,nf).reshape(nf,ny,nx,2)
  local=W.field(sol['coeff'],lu,lv,nf).reshape(nf,ny,nx,2);pred=g[:,None,None,:]+local
  native_rt=json.loads((target/'runtime.json').read_text());native=model_field(native_rt,r);Q=native-pred
  gain_l1=np.abs(phi@P).sum(axis=1).max();bound=float(np.sqrt(2)*5e-6*gain_l1+1e-8)
  delta=float(np.linalg.norm(Q,axis=-1).max())
  U=dg[:,None,None,:]+apply(np.broadcast_to(Tr(-dg[None,:,:]),obs.shape))
  M=gt[:,None,None,:]+apply(Tr(true_residual))-truth
  PL=apply(Tr(eta));PS=apply(serial);PP=PL+PS;error=pred-truth
  closure=float(np.abs(error-U-M-PP).max());check(closure<=1e-8,'linear decomposition closure failed')
  op=dict(rank=rank,n_cols=A.shape[1],condition_raw=float(np.linalg.cond(A)),condition_column_scaled=float(np.linalg.cond(A/np.linalg.norm(A,axis=0))),native_target=str(target),native_vs_prediction_max_vector_px=delta,diagnostic_rounding_vector_bound_px=bound,within_rounding_bound=delta<=bound,native_minus_predicted=stats(Q,roi,pix),predicted_truth_error=stats(error,roi,pix),native_truth_error=stats(native-truth,roi,pix),U_unabsorbed_global=stats(U,roi,pix),M_truth_only_projection_convention=stats(M,roi,pix),P_propagated_discrepancy=stats(PP,roi,pix),P_L_Tr_eta=stats(PL,roi,pix),P_serialized_Tr_residual=stats(PS,roi,pix),decomposition=components(dict(U=U,M=M,P=PP),roi,pix),split_P_decomposition=components(dict(U=U,M=M,P_L=PL,P_serial=PS,Q_native_precision=Q),roi,pix),algebraic_closure_max_abs_px=closure)
  if arm=='B2':
   endpoint=W.field(sol['coeff'],u,v,nf)[-1];spatial_endpoint=S@np.linalg.pinv(S)@(obs[:,-1]-obs[:,0]);op['endpoint_patch_projection_identity_max_abs_px']=float(np.abs(endpoint-spatial_endpoint).max())
  row['operators'][name]=op
  arrays=EVID/'crossfeed-arrays';arrays.mkdir(exist_ok=True)
  np.savez_compressed(arrays/f'{case}-{label}-{name}.npz',predicted_field=pred,native_field=native,U=U,M=M,P=PP,P_L=PL,P_serial=PS,Q=Q,truth=truth,patch_coordinates=keys,observations=obs)
  write(EVID/'crossfeed-partial.json',dict(case=case,upstream=label,operator=name,result=op))
  check(delta<=bound,'native vs frozen W8 cross-feed exceeds diagnostic rounding bound: '+str((case,label,name,delta,bound)))
 return row

def main():
 check((EVID/'NATIVE_COMPLETE.json').exists(),'native matrix incomplete');check(not(EVID/'STOP.json').exists(),'existing STOP; no blind retry');validate_pins()
 summary=[];cross={};regressions=[];P1=[];P2=[]
 for case in ORDER:
  dirs=dict(BASE=verify_reused(case,False),B2=verify_reused(case,True),UP=EVID/'runs'/case/'UP_only',UP_B2=EVID/'runs'/case/'UP_B2')
  scores={}
  for label,d in dirs.items():
   m=metrics(d,case);ck=json.loads((d/'checker.json').read_text());m['checker']={k:ck.get(k) for k in ('accuracy_status','field_distance_status','identifiable','sampling_status','signal_status','application_consistency_status')};m['output_source']=str(d);scores[label]=m
  for a,b in [('BASE','B2'),('BASE','UP'),('B2','UP_B2'),('UP','UP_B2'),('BASE','UP_B2'),('B2','UP')]:
   for rep in ('runtime','STAR'):
    old=scores[a][rep]['angstrom'];new=scores[b][rep]['angstrom'];increased=[k for k in METRICS if new[k]>old[k]]
    if increased:regressions.append(dict(case=case,comparison=b+' vs '+a,representation=rep,increased=increased,old=old,new=new,old_class=scores[a][rep]['gate'],new_class=scores[b][rep]['gate']))
  if case in ('zero','integer','fractional','affine','pedestal'):
   P1.append(dict(case=case,UP={rep:scores['UP'][rep]['gate'] for rep in ('runtime','STAR')},compound={rep:scores['UP_B2'][rep]['gate'] for rep in ('runtime','STAR')},pass_all=all(scores[a][rep]['gate']=='PASS' for a in ('UP','UP_B2') for rep in ('runtime','STAR'))))
  if case=='noisy':
   for rep in ('runtime','STAR'):
    b,u,x=[scores[a][rep]['angstrom'] for a in ('B2','UP','UP_B2')];better={k:x[k]<b[k] for k in METRICS};no_worse={k:x[k]<=u[k] for k in METRICS};P2.append(dict(representation=rep,better_than_B2_alone=better,no_worse_than_UP_only=no_worse,pass_all=all(better.values()) and all(no_worse.values())))
  row=dict(case=case,arms=scores);summary.append(row);write(EVID/'four_arm_summary.json',summary)
  cross[case]={}
  cross[case]['BASE_observations']=crossfeed(case,'BASE',dirs['BASE'],(dirs['BASE'],dirs['B2']))
  cross[case]['UP_observations']=crossfeed(case,'UP',dirs['UP'],(dirs['UP'],dirs['UP_B2']))
  b=cross[case]['BASE_observations'];u=cross[case]['UP_observations']
  if b['status']=='LOCAL_CROSSFEED' and u['status']=='LOCAL_CROSSFEED':
   bc={tuple(v):p for v,p in zip(b['accepted_coordinates'],b['tracking']['all_patch_frame_discrepancies'])};uc={tuple(v):p for v,p in zip(u['accepted_coordinates'],u['tracking']['all_patch_frame_discrepancies'])};common=sorted(set(bc)&set(uc));dropped=sorted(set(bc)-set(uc));added=sorted(set(uc)-set(bc))
   def common_frame_max(mapping):return [max(mapping[k]['eta_norm_px'][f] for k in common) for f in range(4)]
   cross[case]['coverage_comparison']=dict(common_coordinates=common,dropped_coordinates=dropped,added_coordinates=added,BASE_common_per_frame_max_vector_px=common_frame_max(bc),UP_common_per_frame_max_vector_px=common_frame_max(uc),dropped_BASE_discrepancies=[bc[k] for k in dropped],warning='Actual accepted sets differ; full-set max reduction is not pure error repair.')
  write(EVID/'crossfeed.json',cross)
 predictions=dict(P1=dict(rows=P1,confirmed=all(r['pass_all'] for r in P1)),P2=dict(rows=P2,confirmed=all(r['pass_all'] for r in P2)))
 write(EVID/'predictions.json',predictions);write(EVID/'regressions.json',regressions)
 write(EVID/'ANALYSIS_COMPLETE.json',dict(status='COMPLETE',source_production_commit=PINS['production_commit'],binary_sha256=PINS['binary_sha256'],new_producers=16,case_count=8,predictions=predictions,all_crossfeeds_within_diagnostic_rounding_bounds=True,candidate_promotion='NO_GO_RETAINED_NOISY_HARM',full100='UNRUN',GPU='UNRUN',new_N_controls='UNRUN_REUSED_GLOBAL_ONLY_EVIDENCE',timing_claim='NONE'))
 print(json.dumps(dict(P1=predictions['P1']['confirmed'],P2=predictions['P2']['confirmed'],all_crossfeeds_within_bounds=True,regression_rows=len(regressions)),indent=2))
if __name__=='__main__':main()
