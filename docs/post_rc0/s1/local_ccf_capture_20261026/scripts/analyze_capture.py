"""Saved-state only. Actual real-map oracle v3; no native execution."""
import hashlib,importlib.util,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
ROOT=Path('/tmp/motioncorr-local-ccf-20261026');CAP=ROOT/'evidence/runs/ON/capture';OUT=ROOT/'analysis-v1';ORACLE=ROOT/'oracle/validate_oracle_controls_v3.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def load(p):return json.loads(p.read_text())
def array(d,name):
 m=load(d/(name+'.json'));p=d/(name+'.bin');a=np.fromfile(p,dtype=m['dtype']).reshape(m['shape'])
 assert a.nbytes==m['bytes'] and list(a.strides)==m['serialized_byte_strides']
 return a
def complex_array(d,name):
 a=array(d,name);return a[...,0]+1j*a[...,1]
def maxerr(a,b):return float(np.max(np.abs(np.asarray(a)-b)))
def torusdist(a,b):return float(np.linalg.norm((np.asarray(a)-b+[21,16])%[42,32]-[21,16]))
def scalar(o,point):return float(o.eval_val_grad_hess(*point)[0])
def main():
 OUT.mkdir(exist_ok=False)
 assert sha(ORACLE)=='714f2fa8e9fbf9777e2686a978f6bfa364de1aa8c4129b231c99ad36c9be380f'
 spec=importlib.util.spec_from_file_location('cleared_oracle_v3',ORACLE);oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
 pins=load(ROOT/'RUN_PINS.json');assert load(ROOT/'evidence/NATIVE_COMPLETE.json')['producers']==2
 for p,h in pins['analysis_input_files'].items():assert sha(p)==h
 truth=np.load(pins['truth_field']);global_=np.array(load(ROOT/'evidence/runs/ON/runtime.json')['global']);allrows=[];checks=[];patches=[]
 for cy in (47,79):
  d=CAP/f'patch-62-{cy}';completion=load(d/'alignment-complete.json');n=completion['iterations'];assert n==2 and completion['converged']
  # Coverage checks all files incl metadata and no duplicated state names.
  assert load(CAP/'COMPLETE.json')['selected_patches']==2
  expected_files=load(d/'patch-files.json')['files'];assert len(set(expected_files))==len(expected_files)
  assert set(expected_files)|{'patch-files.json'}=={p.name for p in d.iterdir()}
  local_truth=truth[:,cy,62,:]-global_;weight=array(d,'weights');initial=[]
  for f in range(5):
   samples=array(d,f'initial-frame{f}-samples');ft=complex_array(d,f'initial-frame{f}-fft');initial.append(ft)
   checks.append(dict(patch=[62,cy],frame=f,stage='clipped sample forward FFT comparison',max_complex_error=maxerr(np.fft.rfft2(samples)/1344,ft)))
  deltas=[];iterstates={};refs={};enters={}
  for it in range(1,n+1):
   prefix=f'iter{it}';enter=array(d,prefix+'-enter-shifts');exit_=array(d,prefix+'-exit-shifts');delta=array(d,prefix+'-applied-deltas');deltas.append(delta)
   ref=complex_array(d,prefix+'-reference');refs[it]=ref;frames=[complex_array(d,f'{prefix}-frame{f}-window-fft') for f in range(5)];enters[it]=frames
   # Sum in native frame order and float32 precision, not np.sum's unspecified reduction.
   summed=np.zeros_like(frames[0]);
   for ff in frames:summed=(summed+ff).astype(np.complex64)
   assert np.array_equal(summed,ref),'captured reference differs from frame-order sum'
   raw=np.array([load(d/f'{prefix}-frame{f}-peak.json')['raw_scaled_xy_movie'] for f in range(5)])
   assert np.array_equal(raw-raw[0],delta) and np.array_equal(enter+delta,exit_)
   if it==1:assert np.array_equal(enter,np.zeros_like(enter))
   else:assert np.array_equal(enter,array(d,f'iter{it-1}-exit-shifts'))
   stop=load(d/(prefix+'-stop.json'));assert abs(np.sqrt(np.square(delta).sum()/5)-stop['rms_increment_px'])<1e-14
   states=[]
   for f in range(5):
    tag=f'{prefix}-frame{f}';p=load(d/(tag+'-peak.json'));mp=array(d,tag+'-real-map');pre=complex_array(d,tag+'-weighted-pre-dc');post=complex_array(d,tag+'-weighted-api-consumed');actual=complex_array(d,tag+'-c2r-temporary-before');api_after=complex_array(d,tag+'-weighted-api-after');destroyed=complex_array(d,tag+'-c2r-temporary-after');other=complex_array(d,tag+'-sum-of-others')
    assert np.array_equal(post,actual) and np.array_equal(post,api_after),'API/actual C2R input identity mismatch'
    assert post[0,0]==0 and np.array_equal(pre.ravel()[1:],post.ravel()[1:])
    assert np.array_equal((ref-frames[f]).astype(np.complex64),other)
    native_replay=oracle.native_discrete_and_local_fit(mp)
    assert [native_replay['level1_integer']['posx'],native_replay['level1_integer']['posy']]==p['integer_xy']
    assert native_replay['level1_integer']['maxval']==p['max_value'] and native_replay['level2_coupled']['verdict']==p['coupled_verdict']
    selected=[native_replay['level2_coupled']['applied_x'],native_replay['level2_coupled']['applied_y']]
    assert maxerr(selected,p['raw_selected_xy_ccf'])<1e-12
    desired=local_truth[f]-enter[f];truthpoint=desired+raw[0]
    o=oracle.TrigonometricCcfOracleV3(mp);levels=o.run_all_levels(truth_seed=tuple(truthpoint),oversample_factor=32)
    best=levels['level4_multistart_local_candidates']['best_torus_candidate'];bestxy=[best['x'],best['y']];nativexy=p['raw_selected_xy_ccf']
    selected_local=o.newton_refine_unconstrained(*nativexy)
    numpy_map=oracle.numpy_reference_irfft2_unnormalized_not_native_fftw(post)
    row=dict(patch=[62,cy],iteration=it,frame=f,native=p,native_map_replay=native_replay,desired_anchored_increment_px=desired.tolist(),truth_scoring_raw_point=truthpoint.tolist(),raw_frame0_gauge_px=raw[0].tolist(),native_objective_value=scalar(o,nativexy),integer_objective_value=scalar(o,p['integer_xy']),truth_point_objective_value=scalar(o,truthpoint),native_to_truth_periodic_distance_px=torusdist(nativexy,truthpoint),native_to_best_local_candidate_periodic_distance_px=torusdist(nativexy,bestxy),native_seeded_local_candidate=selected_local,native_to_same_basin_local_candidate_periodic_distance_px=torusdist(nativexy,[selected_local['x'],selected_local['y']]),levels=levels,precision_diagnostics=dict(actual_C2R_API_before_and_after_exact=True,postC2R_scratch_changed_components=int(np.count_nonzero(array(d,tag+'-c2r-temporary-before')!=array(d,tag+'-c2r-temporary-after'))),postC2R_scratch_all_finite=bool(np.isfinite(destroyed).all()),numpy_irfft2_unnormalized_vs_actual_float_map_max_error=maxerr(numpy_map,mp),weighted_expression_complex64_max_error=maxerr(((ref-frames[f])*frames[f].conj()*weight).astype(np.complex64),pre),map_absmax=float(np.max(np.abs(mp)))))
    allrows.append(row);states.append(row)
    write(OUT/f'patch62-{cy}-iter{it}-frame{f}.json',row)
   iterstates[it]=states
  final=array(d,'final-local-shifts');reported=array(d,'reported-observations');interp=array(d,'interpolated-shifts')
  assert np.array_equal(final,np.sum(np.array(deltas),axis=0)) and np.array_equal(reported,final-interp[0])
  assert maxerr(interp[0],-.5*final[1])<1e-14
  # Native interpolation/recentering contributes the same +.5*s1 to every group observation.
  patches.append(dict(patch=[62,cy],iterations=n,local_truth_px=local_truth.tolist(),final_local_px=final.tolist(),reported_observations_px=reported.tolist(),reported_minus_local_common_offset_px=(-interp[0]).tolist(),final_local_error_px=(final-local_truth).tolist(),reported_error_px=(reported-local_truth).tolist(),reported_endpoint_error_norm_px=float(np.linalg.norm(reported[4]-local_truth[4])),per_iteration_applied_deltas_px=np.array(deltas).tolist(),per_iteration_endpoint_contributions_px=[v[4].tolist() for v in deltas]))
  # Endpoint/frame0 same-state isolated reference probes; not a producer or trajectory replay.
  probes=[]
  for f in (0,4):
   for refit,frameit in ((1,1),(1,2),(2,1),(2,2)):
    other=refs[refit]-enters[refit][f];F=other*enters[frameit][f].conj()*weight;F[0,0]=0
    mp=oracle.numpy_reference_irfft2_unnormalized_not_native_fftw(F);o=oracle.TrigonometricCcfOracleV3(mp)
    replay=oracle.native_discrete_and_local_fit(mp);levels=o.run_all_levels(oversample_factor=32)
    probes.append(dict(frame=f,sum_of_others_iteration=refit,current_frame_iteration=frameit,numpy_float64_counterfactual_not_native=True,discrete_and_fit=replay,level3=levels['level3_oversampled'],level4=levels['level4_multistart_local_candidates'],global_status='UNPROVEN_GLOBAL'))
  write(OUT/f'patch62-{cy}-reference-probes.json',probes)
 result=dict(scope='two selected patches, same noisy UP-only fixture; saved data only; no estimator or science claim',oracle_sha256=sha(ORACLE),global_status='UNPROVEN_GLOBAL',coverage=dict(patches=2,frames=5,actual_iterations_each=2,map_states=len(allrows)),sampled_analytic_checks=checks,patches=patches,rows=allrows,source_commit=pins['source_commit'],binary_sha256=pins['binary_sha256'],coverage_caveat='UP accepts8 versus BASE9; dropped(104,47) base endpoint discrepancy23.00612px remains explicit; not excluded by estimator')
 write(OUT/'RESULT.json',result)
if __name__=='__main__':main()
