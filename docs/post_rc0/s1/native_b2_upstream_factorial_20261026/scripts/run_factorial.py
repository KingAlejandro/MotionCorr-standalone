"""Exactly16 new tiny native producers. Scientific failures do not tune/skip rows."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from factorial_common import *

def run(case,b2):
 label='UP_B2' if b2 else 'UP_only';d=EVID/'runs'/case/label;d.mkdir(parents=True,exist_ok=False)
 admission(d);validate_pins();verify_reused(case,False);verify_reused(case,True)
 patch=3 if case in ('noisy','affine','pedestal') else 1
 cmd=[str(BIN),'--i',case+'.star','--o',str(d/'output'),'--use_own','--j','2','--patch_x',str(patch),'--patch_y',str(patch),'--group_frames','1','--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','5','--skip_logfile','--max_iter','5','--experimental_coupled_peak','all']
 if b2:cmd+=['--experimental_local_b2']
 env={k:v for k,v in os.environ.items() if not k.startswith(('MC_DIAG_','MC_EXPERIMENT_'))}
 env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',MC_EXPERIMENT_CCF_DC_ARM='both',MC_DIAG_MODEL_OUT=str(d/'runtime.json'),PYTHONDONTWRITEBYTECODE='1')
 start=time.monotonic()
 with (d/'stdout.log').open('w') as f:rc=subprocess.run(['/usr/bin/time','-v','-o',str(d/'time.txt'),*cmd],cwd=FIX,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 receipt=dict(case=case,arm=label,argv=cmd,exit=rc,wall_seconds_receipt_only=time.monotonic()-start,requested_native_threads=2,binary_sha256=sha(BIN),environment={k:env[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MC_EXPERIMENT_CCF_DC_ARM')},publication={str(p.relative_to(d/'output')):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (d/'output').rglob('*') if p.is_file()})
 write(d/'RUN.json',receipt);check(rc==0,'native producer exit '+str((case,label,rc)))
 check({'runtime.json','stdout.log','time.txt'}<={p.name for p in d.iterdir()},'missing capture/receipt')
 check({case+'.star',case+'.mrc',case+'.log','corrected_micrographs.star'}<=set(receipt['publication']),'publication incomplete')
 rt=json.loads((d/'runtime.json').read_text());check(np.isfinite(np.array(rt['global'])).all() and np.isfinite(rt['coeff_x']).all() and np.isfinite(rt['coeff_y']).all(),'nonfinite runtime capture')
 result=metrics(d,case);result['manipulation']=manipulation(d/'stdout.log')
 keys,obs=observations(d/'output'/f'{case}.star',5)
 accepted=sum(p['converged'] is True for p in result['convergence']['patches'])
 check(len(keys)==accepted if rt['local_enabled'] else len(keys)==0,'accepted observations not captured')
 if accepted and not rt['local_enabled']:check(False,'accepted patch observations lost at local-model rejection; diagnose without retry')
 cp=subprocess.run([PY,'-B',str(SRC/'tools/check_motion_diagnostics.py'),'--fixtures',str(FIX),'--case',case,'--candidate',str(d/'output'/f'{case}.star'),'--summed-image',str(d/'output'/f'{case}.mrc'),'--json',str(d/'checker.json')],capture_output=True,text=True)
 (d/'checker.stdout').write_text(cp.stdout+cp.stderr);check(cp.returncode in (0,1) and (d/'checker.json').exists(),'checker failed without result')
 ck=json.loads((d/'checker.json').read_text());result.update(checker_exit=cp.returncode,checker={k:ck.get(k) for k in ('accuracy_status','field_distance_status','identifiable','sampling_status','signal_status','application_consistency_status')},patch_coordinates=keys.tolist(),fit_RMS_logged=re.findall(r'Polynomial fit RMSD:.*',(d/'output'/f'{case}.log').read_text()),fit_RMS_estimand='nuisance-adjusted observation residual' if b2 else 'inherited observation residual')
 write(d/'metrics.json',result)
 print(case,label,receipt['exit'],result['runtime']['gate'],result['runtime']['angstrom'],'local',rt['local_enabled'],'patches',len(keys),flush=True)
 return d,rt,result

def main():
 EVID.mkdir(exist_ok=False);validate_pins();rows=[]
 for case in ORDER:
  a,ra,ma=run(case,False);b,rb,mb=run(case,True)
  sa=star_blocks(a/'output'/f'{case}.star');sb=star_blocks(b/'output'/f'{case}.star')
  identity=dict(global_runtime_exact=ra['global']==rb['global'],global_STAR_block_exact=sa['global_shift']==sb['global_shift'],observation_STAR_block_exact=sa.get('local_shift','')==sb.get('local_shift',''),patch_acceptance_exact=ma['convergence']==mb['convergence'],stage_counters_exact=ma['manipulation']==mb['manipulation'])
  write(b/'UP-pair-identity.json',identity);check(all(identity.values()),'UP pair upstream/observation/acceptance/counter identity differs: '+case)
  if not ra['local_enabled'] and not rb['local_enabled']:
   cp=subprocess.run([PY,'-B',str(OLD/'scripts/compare_products.py'),str(a/'output'),str(b/'output'),str(b/'global-only-product-identity.json')],capture_output=True,text=True)
   (b/'global-only-product-identity.stdout').write_text(cp.stdout+cp.stderr);check(cp.returncode==0,'global-only B2 neutrality broken')
  rows.append(dict(case=case,UP_only=ma,UP_B2=mb,pair_identity=identity));write(EVID/'native_matrix.json',rows)
 write(EVID/'NATIVE_COMPLETE.json',dict(status='COMPLETE_16_NATIVE_PRODUCERS',case_order=list(ORDER),source_production_commit=PINS['production_commit'],binary_sha256=PINS['binary_sha256'],source_changed=False,promotion='NO_CLAIM',full100='UNRUN',GPU='UNRUN',timing_claim='NONE'))
if __name__=='__main__':main()
