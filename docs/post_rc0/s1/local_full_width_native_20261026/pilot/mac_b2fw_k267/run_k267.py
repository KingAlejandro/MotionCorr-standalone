#!/usr/bin/env python3
"""Frozen K267 B2FW four-arm producer; field scoring calls the unchanged v3 operator."""
import ast, hashlib, json, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
PILOT=HERE.parent
REPO=PILOT.parents[4]
ROOT=Path('/tmp/mc-mac-pilot-20261027').resolve()/'b2fw-k267-r1'
FX=Path('/tmp/mc-mac-pilot-20261027/fixtures-numpy253').resolve()
BIN=Path('/tmp/mc-mac-pilot-20261027/build-numpy253/motioncorr').resolve()
BSHA='d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546'
GS=Path('/opt/homebrew/bin/gs'); GSHA='d57bb373324bf7e72c5b3fb1a6cc8a9f876eb6f8d2eec23a5a3809a8a108bf9e'
SPEC='5304253b5bcea349eb306f8972acb069b624ce050095a2b7977f11d6a3756597'
CONSUMER=Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
sys.path.insert(0,str(PILOT)); import score_fields_v3 as V3
ADM=json.loads((PILOT/'ADMISSION_DRAFT_v3.json').read_text())
CMP=REPO/'docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py'
COMMON=REPO/'docs/post_rc0/s1/native_b2_upstream_factorial_20261026/scripts/factorial_common.py'
CASES=ADM['case_order']; ARMS={'OFF':[], 'B2':['--experimental_local_b2'], 'FW':['--experimental_local_full_width_weight'], 'B2FW':['--experimental_local_b2','--experimental_local_full_width_weight']}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def info(p):return {'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,x):p.write_text(json.dumps(x,indent=1,allow_nan=False)+'\n')
def check(x,msg):
 if not x:raise RuntimeError(msg)
def star_blocks():
 src=COMMON.read_text(); nodes=[n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='star_blocks'];check(len(nodes)==1,'STAR parser');ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(COMMON),'exec'),ns);return ns['star_blocks']
def run(case,arm):
 d=ROOT/case/arm;d.mkdir(parents=True,exist_ok=False)
 free=shutil.disk_usage('/tmp').free;check(free>3*1024**3,'scratch free <3 GiB')
 (d/'occupancy.txt').write_text(subprocess.check_output(['/usr/bin/uptime'],text=True)+f'free_bytes={free}\n'+subprocess.check_output(['/bin/ps','-Ao','pid,pcpu,comm'],text=True))
 check(sha(BIN)==BSHA and sha(GS)==GSHA,'binary or Ghostscript changed')
 inp=d/'input';inp.mkdir(); row=next(r for r in ADM['rows'] if r['case']==case)
 for name in [case+'.star',case+'.mrcs']:
  shutil.copyfile(FX/name,inp/name);pin=ADM['fixture_files'][name];check(sha(inp/name)==pin['sha256'] and (inp/name).stat().st_size==pin['bytes'],'staged input mismatch')
 grid=row['patch_grid'];argv=[str(BIN),'--i',case+'.star','--o',str(d/'output'),'--use_own','--j','2','--patch_x',str(grid[0]),'--patch_y',str(grid[1]),'--group_frames','1','--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','5','--skip_logfile','--max_iter','5']+ARMS[arm]
 env={k:v for k,v in os.environ.items() if not k.startswith(V3.CONTROLLED_PREFIXES)};env.update({'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','MC_EXPERIMENT_CCF_DC_ARM':'none','MC_DIAG_MODEL_OUT':str(d/'runtime.json'),'PYTHONDONTWRITEBYTECODE':'1'})
 start=time.time();p=subprocess.run(argv,cwd=inp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(d/'stdout.log').write_bytes(p.stdout);out=d/'output';pub={str(x.relative_to(out)):info(x) for x in sorted(out.rglob('*')) if x.is_file()} if out.exists() else {}
 rec={'schema':'mac-b2fw-k267-run/1','case':case,'arm':arm,'exit':p.returncode,'run_dir':str(d),'argv':argv,'cwd':str(inp),'binary_sha256':BSHA,'environment':{k:v for k,v in env.items() if k.startswith(V3.CONTROLLED_PREFIXES) or k in ('PATH','PYTHONDONTWRITEBYTECODE')},'publication':pub,'runtime':info(d/'runtime.json') if (d/'runtime.json').is_file() else None,'stdout':info(d/'stdout.log'),'wall_seconds':time.time()-start};save(d/'RUN.json',rec)
 check(p.returncode==0,'producer exit '+case+'/'+arm);names=sorted(k[len('output/'):] for k in row['baseline_files'] if k.startswith('output/'));check(sorted(pub)==names,'publication inventory '+case+'/'+arm);check((out/'logfile.pdf').stat().st_size>0,'empty PDF');check(all(sha(out/n)==v['sha256'] for n,v in pub.items()),'publication hash')
 log=(out/(case+'.log')).read_text();check(log.splitlines()[0]==f'Working on {case}.mrcs with 2 thread(s).','case log');lines=[x for x in log.splitlines() if 'EXPERIMENTAL local full-width weight' in x];expect=9 if grid==[3,3] and arm in ('FW','B2FW') else 0;check(len(lines)==expect and all(x==V3.WITNESS_LINE for x in lines),'weight witness '+case+'/'+arm)
 text=(d/'stdout.log').read_text();check('MC_EXPERIMENT_CCF_DC arm=none' in text and '[coupled_peak]' not in text,'DC or coupled setting '+case+'/'+arm)
 s=V3.field_metrics_bound(case,d/'runtime.json',out/(case+'.star'),FX/(case+'_field.npy'),FX);save(d/'score.json',s)
 model=json.loads((d/'runtime.json').read_text());g=np.asarray(model['global'],dtype=np.float64);check(g.shape==(5,2) and np.isfinite(g).all(),'global model');con=V3.V2.R.convergence(out/(case+'.log'));save(d/'facts.json',{'convergence':con,'witness_lines':len(lines),'local_enabled':model['local_enabled']})
 return {'global_bits':g.view(np.uint64).tolist(),'global_star':star_blocks()(out/(case+'.star'))['global_shift'],'score':s,'convergence':con}
def main():
 check(not ROOT.exists(),'namespace exists: no retries');ROOT.mkdir(parents=True);check(sha(HERE/'B2FW-PREDICTION.md')==SPEC,'prediction hash');check(sha(BIN)==BSHA and sha(GS)==GSHA,'binary or gs pin');V3.verify_tool_pins(ADM,{'consumer_source':CONSUMER,'repo':REPO,'pilot':PILOT})
 for n,p in ADM['fixture_files'].items():check((FX/n).is_file() and (FX/n).stat().st_size==p['bytes'] and sha(FX/n)==p['sha256'],'fixture '+n)
 results={}
 for case in CASES:
  results[case]={}
  for arm in ARMS:
   results[case][arm]=run(case,arm);base=results[case]['OFF'];cur=results[case][arm];check(base['global_bits']==cur['global_bits'] and base['global_star']==cur['global_star'],'global mismatch '+case+'/'+arm)
   if case in ('zero','integer','fractional','flat','repeated') and arm!='OFF':
    for rel in ('runtime.json',f'output/{case}.star'):check((ROOT/case/'OFF'/rel).read_bytes()==(ROOT/case/arm/rel).read_bytes(),'global-only model difference '+case+'/'+arm)
    cmpfile=ROOT/case/(arm+'-compare.json');p=subprocess.run([sys.executable,str(CMP),str(ROOT/case/'OFF/output'),str(ROOT/case/arm/'output'),str(cmpfile)],capture_output=True,text=True);(ROOT/case/(arm+'-compare.log')).write_text(p.stdout+p.stderr);check(p.returncode==0 and json.loads(cmpfile.read_text())['verdict']=='IDENTICAL','global-only product difference '+case+'/'+arm)
   save(ROOT/'partial_results.json',results)
 save(ROOT/'results.json',results)
if __name__=='__main__':
 try:main()
 except Exception:
  ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'STOP.txt').write_text(traceback.format_exc());raise
