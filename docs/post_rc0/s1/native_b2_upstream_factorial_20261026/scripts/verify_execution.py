"""Mechanical final receipt checks; no producer, fit, image read/scoring or gate change."""
import sys,struct
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from factorial_common import *
validate_pins();check((EVID/'ANALYSIS_COMPLETE.json').exists(),'analysis incomplete')
rows=[];actual=list((EVID/'runs').glob('*/*/RUN.json'));check(len(actual)==16,'producer count differs')
for case in ORDER:
 verify_reused(case,False);verify_reused(case,True)
 for arm in ('UP_only','UP_B2'):
  d=EVID/'runs'/case/arm;rr=json.loads((d/'RUN.json').read_text());ad=json.loads((d/'admission.json').read_text());args=rr['argv']
  check(rr['exit']==0 and rr['binary_sha256']==PINS['binary_sha256'],'producer exit/binary differs')
  for flag,value in [('--j','2'),('--group_frames','1'),('--bin_factor','1'),('--max_iter','5'),('--first_frame_sum','1'),('--last_frame_sum','5'),('--seed','1'),('--experimental_coupled_peak','all')]:check(args[args.index(flag)+1]==value,'command scope differs: '+flag)
  check(('--experimental_local_b2' in args)==(arm=='UP_B2') and '--gpu' not in args,'experimental factor scope differs')
  check(rr['environment']['MC_EXPERIMENT_CCF_DC_ARM']=='both' and rr['environment']['OMP_NUM_THREADS']=='2','environment differs')
  check(ad['affinity']==list(range(32,48)) and '/tmp/motioncorr-cpu64-bench.lock' in ad['acquired_locks'],'resource guard differs')
  check(ad['task_scratch_bytes']+ad['prior_retained_scratch_bytes']<=ad['combined_limit_bytes'],'scratch admission exceeded')
  for name,want in rr['publication'].items():
   p=d/'output'/name;check(p.stat().st_size==want['bytes'] and sha(p)==want['sha256'],'published output changed: '+str(p))
  with (d/'output'/f'{case}.mrc').open('rb') as f:header=f.read(1024)
  check(struct.unpack('<4i',header[:16])==(128,96,1,2),'sum geometry/mode differs')
  text=(d/'stdout.log').read_text();match=re.search(r'\[align\] scope=global iterations=(\d+) max_iter=(\d+) converged=(\d) last_rmsd_px=(\S+) tolerance_px=(\S+)',text)
  check(match is not None and int(match[2])==5 and float(match[5])==.5,'stop budget/tolerance differs')
  rows.append(dict(case=case,arm=arm,exit=0,global_iterations=int(match[1]),global_converged=bool(int(match[3])),max_iter=5,tolerance_px=.5,requested_native_threads=2,all_published_hashes_verified=True,affinity=ad['affinity'],combined_scratch_bytes_at_admission=ad['task_scratch_bytes']+ad['prior_retained_scratch_bytes'],acquired_locks=ad['acquired_locks']))
write(EVID/'EXECUTION_VERIFICATION.json',dict(status='PASS_MECHANICAL_RECEIPTS_ONLY',new_producers=16,reused_base_outputs=16,rows=rows,source_production_commit=PINS['production_commit'],binary_sha256=PINS['binary_sha256'],timing_claim='NONE',full_CPU_qualification='UNRUN',GPU='UNRUN'))
print('PASS16 producer receipts/publication hashes/stop budgets/resources;16 sealed base outputs rechecked')
