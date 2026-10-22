#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Final source-faithful replay, summarization and recorded exit; no native launches."""
import datetime,hashlib,itertools,json,os,pathlib,subprocess,sys
import numpy as np
r=pathlib.Path(sys.argv[1])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
assert (r/'analysis-verification.exit').read_text().strip()=='0'
assert json.loads((r/'analysis-verification.json').read_text())['identical']
argv=['taskset','-c','10-13','/home/alex/.mc-venv/bin/python3',str(r/'replay-final.py'),str(r),str(r/'analysis-final.json')]
with (r/'analysis-final.log').open('w') as f:
 p=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1'))
 (r/'analysis-final.pid').write_text(str(p.pid)+'\n');rc=p.wait()
(r/'analysis-final.exit').write_text(str(rc)+'\n')
write(r/'analysis-final-receipt.json',dict(argv=argv,pid=p.pid,exit=rc,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),affinity=sorted(os.sched_getaffinity(0)),script_sha256=sha(r/'replay-final.py')))
assert rc==0
result=json.loads((r/'analysis-final.json').read_text());rows=result['rows'];trajectories=result['trajectories'];groups=[];witnesses=[]
def key(x):return x['case'],x['backend'],tuple(x['patch_yx']),x['call']
def rms(v):return float(np.sqrt(np.mean(np.sum(np.array(v)**2,axis=-1))))
for k,seq in itertools.groupby(sorted(rows,key=key),key):
 xs=list(seq);ts=[t for t in trajectories if key(t)==k];last=max(ts,key=lambda x:x['iteration']);first=min(ts,key=lambda x:x['iteration'])
 g=dict(case=k[0],backend=k[1],patch_yx=list(k[2]),call=k[3],tag=xs[0]['geometry']['tag'],frames=len(xs),iterations=len(ts),
   native_candidate_same_map_max_abs=max(abs(v) for x in xs for v in x['same_map_candidate_error_xy']),
   stored_ties_max=max(x['peaks']['stored']['ties'] for x in xs),stored_search_boundary_count=sum(x['peaks']['stored']['search_boundary'] for x in xs),
   max_map_abs_error=max(x['map_abs_error'] for x in xs),max_map_error_over_search_contrast=max(x['map_error_over_search_contrast'] or 0 for x in xs),
   native_last_truth_vector_rms=last['truth_vector_rms'],native_first_truth_vector_rms=first['truth_vector_rms'],conditional={})
 for kind in ['rounded_inverse','inverse_double','product_double','reference_double']:
   delta=np.array([x['conditional_shift_disagreement_xy'][kind] for x in xs]);native=np.array(last['truth_residual_xy'])
   g['conditional'][kind]=dict(max_candidate_vector_difference_px=float(np.linalg.norm(delta,axis=1).max()),
      integer_winner_changes=sum(x['peaks'][kind]['integer_xy']!=x['peaks']['stored']['integer_xy'] for x in xs),
      last_conditional_update_truth_vector_rms=rms(np.array(last['conditional_updates'][kind])-native),
      first_conditional_update_truth_vector_rms=rms(np.array(first['conditional_updates'][kind])-np.array(first['truth_residual_xy'])))
 g['max_reference_double_vs_inverse_double_shift_vector_px']=max(float(np.linalg.norm(np.array(x['peaks']['reference_double']['shift_xy'])-x['peaks']['inverse_double']['shift_xy'])) for x in xs)
 groups.append(g)
 # Keep a worst-boundary witness and an earliest changed-integer witness for each invocation.
 chosen=[max(xs,key=lambda x:np.linalg.norm(x['conditional_shift_disagreement_xy']['inverse_double']))]
 changed=[x for x in xs if x['peaks']['stored']['integer_xy']!=x['peaks']['inverse_double']['integer_xy']]
 if changed:chosen.append(min(changed,key=lambda x:(x['iteration'],x['frame'])))
 for x in chosen:
   if x not in witnesses:witnesses.append(x)
retry=[]
for case,patch in [('affine',[2,1]),('noisy',[1,3])]:
 d=r/'runs'/f'cuda-{case}-on'/'capture';m=[(p,json.loads(p.read_text())) for p in sorted(d.glob('c*.json'))];selected=[(p,g) for p,g in m if g['patch_yx']==patch];assert len(selected)==2
 a,b=[p.with_suffix('') for p,g in selected];af={p.name[len(a.name):]:p for p in d.glob(a.name+'-*.bin')};bf={p.name[len(b.name):]:p for p in d.glob(b.name+'-*.bin')}
 checks={k:sha(af[k])==sha(bf[k]) for k in af.keys()&bf.keys()}
 retry.append(dict(case=case,patch_yx=patch,first=selected[0][1],second=selected[1][1],same_inventory=af.keys()==bf.keys(),files_compared=len(checks),identical_all=all(checks.values()),different=[k for k,v in checks.items() if not v]))
checkers=[];historical=[]
old=pathlib.Path('/mnt/clathrin/alex-motioncorr-parallel-20261022-numerics-d751ff28')
for case in ['integer','fractional','affine','noisy']:
 for backend in ['cpu','cuda']:
  for mode in ['off','on']:
   d=r/'runs'/f'{backend}-{case}-{mode}';c=json.loads((d/'checker.json').read_text())
   checkers.append(dict(case=case,backend=backend,capture=mode,accuracy_status=c['accuracy_status'],field_distance_status=c['field_distance_status'],sampling_status=c['sampling_status'],field_px=c['field_px'],estimated_motion_bilinear=c['signal']['estimated_motion_bilinear']))
  fresh=r/'runs'/f'{backend}-{case}-off'/'out';previous=old/('cases-'+backend)/case
  def core(p):b=p.read_bytes();return b[:224]+b[1024:]
  historical.append(dict(case=case,backend=backend,old_numerical_source='d751ff28594902eca75d665ff116e662653481aa',new_control_star_identical=(fresh/(case+'.star')).read_bytes()==(previous/(case+'.star')).read_bytes(),new_control_mrc_core_payload_identical=core(fresh/(case+'.mrc'))==core(previous/(case+'.mrc'))))
summary=dict(analysis_exit=0,source_faithful_update_checks=len(trajectories),controls=result['controls'],captured_frame_records=len(rows),captured_iterations=len(trajectories),captured_alignment_calls=len(groups),same_map_exact_candidate_records=sum(all(v==0 for v in x['same_map_candidate_error_xy']) for x in rows),groups=groups,retry_comparisons=retry,checker_results=checkers,historical_control_comparison=historical,limits=result['limits'],analysis_sha256=sha(r/'analysis-final.json'))
write(r/'analysis-summary.json',summary);write(r/'witnesses.json',witnesses);write(r/'trajectories.json',trajectories)
print('final analysis PASS',len(rows),'frame records',len(groups),'calls',len(trajectories),'iterations')
for g in groups:print(g['case'],g['backend'],g['patch_yx'],g['call'],'inverse delta',g['conditional']['inverse_double']['max_candidate_vector_difference_px'],'winner changes',g['conditional']['inverse_double']['integer_winner_changes'])
