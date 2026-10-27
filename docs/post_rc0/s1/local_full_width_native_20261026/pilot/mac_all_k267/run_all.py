#!/usr/bin/env python3
"""ALL-only K267 Mac producer and comparison against retained UPFW."""
import ast,hashlib,json,os,re,shutil,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent; PILOT=HERE.parent; REPO=PILOT.parents[4]
BASE=Path('/tmp/mc-mac-pilot-20261027').resolve();ROOT=BASE/'all-k267-r1';FX=BASE/'fixtures-numpy253';BIN=(BASE/'build-numpy253/motioncorr').resolve();GS=Path('/opt/homebrew/bin/gs')
BSHA='d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546'; GSHA='d57bb373324bf7e72c5b3fb1a6cc8a9f876eb6f8d2eec23a5a3809a8a108bf9e'; SPEC='e7acf6aee81ffe4865a488391f8b23b95d09267ad1bab69d9202c662c4ac75d2'
CONSUMER=Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6');sys.path.insert(0,str(PILOT));import score_fields_v3 as V3
ADM=json.loads((PILOT/'ADMISSION_DRAFT_v3.json').read_text());CMP=REPO/'docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py';COMMON=REPO/'docs/post_rc0/s1/native_b2_upstream_factorial_20261026/scripts/factorial_common.py'
CASES=ADM['case_order'];ARMS=['OFF','B2','FW','B2FW'];sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(x,msg):
 if not x:raise RuntimeError(msg)
def info(p):return {'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,obj):p.write_text(json.dumps(obj,indent=1,allow_nan=False)+'\n')
def helper():
 src=COMMON.read_text();nodes=[n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name in ('star_blocks','manipulation')];check(len(nodes)==2,'helpers');ns={'re':re,'Path':Path,'check':check};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(COMMON),'exec'),ns);return ns['star_blocks'],ns['manipulation']
def verify_old(case,arm):
 if arm in ARMS: path=BASE/'b2fw-k267-r1'/case/arm; ref=PILOT/'mac_b2fw_k267/evidence_r1'/case/arm
 else:
  path=BASE/('mac-native-r1' if case in ['noisy','affine','pedestal','zero'] else 'mac-native-r2')/case/('OFF' if arm=='UP' else 'ON');ref=PILOT/('mac_native_r1' if case in ['noisy','affine','pedestal','zero'] else 'mac_native_r2')/case/('OFF' if arm=='UP' else 'ON')
 for f in ['RUN.json','score.json','runtime.json',f'{case}.star',f'{case}.log']:
  actual=path/('output/'+f if f in [f'{case}.star',f'{case}.log'] else f);check(actual.is_file() and sha(actual)==sha(ref/f),'retained evidence mismatch '+case+'/'+arm+'/'+f)
 rec=json.loads((path/'RUN.json').read_text());check(rec['exit']==0 and rec['binary_sha256']==BSHA,'retained run identity');
 for n,pin in rec['publication'].items():
  p=path/'output'/n;check(p.is_file() and p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],'retained publication mismatch '+case+'/'+arm+'/'+n)
 return path
def run(case,blocks,manip):
 d=ROOT/case/'ALL';d.mkdir(parents=True,exist_ok=False);free=shutil.disk_usage('/tmp').free;check(free>3*1024**3,'scratch free');(d/'occupancy.txt').write_text(subprocess.check_output(['/usr/bin/uptime'],text=True)+f'free_bytes={free}\n'+subprocess.check_output(['/bin/ps','-Ao','pid,pcpu,comm'],text=True));check(sha(BIN)==BSHA and sha(GS)==GSHA,'binary or gs pin')
 inp=d/'input';inp.mkdir();row=next(r for r in ADM['rows'] if r['case']==case)
 for n in [case+'.star',case+'.mrcs']:
  shutil.copyfile(FX/n,inp/n);p=ADM['fixture_files'][n];check(sha(inp/n)==p['sha256'] and (inp/n).stat().st_size==p['bytes'],'staged input')
 grid=row['patch_grid'];argv=[str(BIN),'--i',case+'.star','--o',str(d/'output'),'--use_own','--j','2','--patch_x',str(grid[0]),'--patch_y',str(grid[1]),'--group_frames','1','--bin_factor','1','--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','5','--skip_logfile','--max_iter','5','--experimental_coupled_peak','all','--experimental_local_b2','--experimental_local_full_width_weight']
 env={k:v for k,v in os.environ.items() if not k.startswith(V3.CONTROLLED_PREFIXES)};env.update({'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','MC_EXPERIMENT_CCF_DC_ARM':'both','MC_DIAG_MODEL_OUT':str(d/'runtime.json'),'PYTHONDONTWRITEBYTECODE':'1'})
 start=time.time();p=subprocess.run(argv,cwd=inp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(d/'stdout.log').write_bytes(p.stdout);out=d/'output';pub={str(x.relative_to(out)):info(x) for x in sorted(out.rglob('*')) if x.is_file()} if out.exists() else {}
 rec={'schema':'mac-all-k267-run/1','case':case,'arm':'ALL','exit':p.returncode,'run_dir':str(d),'argv':argv,'cwd':str(inp),'binary_sha256':BSHA,'environment':{k:v for k,v in env.items() if k.startswith(V3.CONTROLLED_PREFIXES) or k in ('PATH','PYTHONDONTWRITEBYTECODE')},'publication':pub,'runtime':info(d/'runtime.json') if (d/'runtime.json').is_file() else None,'stdout':info(d/'stdout.log'),'wall_seconds':time.time()-start};save(d/'RUN.json',rec);check(p.returncode==0,'producer exit '+case)
 names=sorted(k[len('output/'):] for k in row['baseline_files'] if k.startswith('output/'));check(sorted(pub)==names,'publication inventory');check((out/'logfile.pdf').stat().st_size>0,'empty PDF');log=(out/(case+'.log')).read_text();check(log.splitlines()[0]==f'Working on {case}.mrcs with 2 thread(s).','case log');w=[x for x in log.splitlines() if 'EXPERIMENTAL local full-width weight' in x];expected=9 if grid==[3,3] else 0;check(len(w)==expected and all(x==V3.WITNESS_LINE for x in w),'weight witness')
 man=manip(d/'stdout.log');check(man['dc']['global_eligible']>0,'global manipulation');check(man['dc']['local_eligible']>0 if grid==[3,3] else man['dc']['local_eligible']==0 and man['coupled']['patch']['peaks']==0,'local manipulation')
 score=V3.field_metrics_bound(case,d/'runtime.json',out/(case+'.star'),FX/(case+'_field.npy'),FX);con=V3.V2.R.convergence(out/(case+'.log'));save(d/'score.json',score);save(d/'facts.json',{'convergence':con,'manipulation':man,'witness_lines':len(w)})
 model=json.loads((d/'runtime.json').read_text());g=np.asarray(model['global'],dtype=np.float64);check(g.shape==(5,2) and np.isfinite(g).all(),'global shape');return {'score':score,'convergence':con,'manipulation':man,'global_bits':g.view(np.uint64).tolist(),'global_star':blocks(out/(case+'.star'))['global_shift']}
def main():
 check(not ROOT.exists(),'namespace exists; no retry');ROOT.mkdir(parents=True);check(sha(HERE/'ALL-PREDICTION.md')==SPEC and sha(BIN)==BSHA and sha(GS)==GSHA,'pin mismatch');V3.verify_tool_pins(ADM,{'consumer_source':CONSUMER,'repo':REPO,'pilot':PILOT})
 for n,p in ADM['fixture_files'].items():check((FX/n).is_file() and (FX/n).stat().st_size==p['bytes'] and sha(FX/n)==p['sha256'],'fixture '+n)
 old={c:{a:verify_old(c,a) for a in ARMS+['UP','UPFW']} for c in CASES};blocks,manip=helper();results={}
 for c in CASES:
  result=run(c,blocks,manip);up=old[c]['UPFW'];model=json.loads((up/'runtime.json').read_text());bits=np.asarray(model['global'],dtype=np.float64).view(np.uint64).tolist();check(result['global_bits']==bits and result['global_star']==blocks(up/'output'/(c+'.star'))['global_shift'],'ALL global differs from UPFW '+c)
  if c in ['integer','fractional']:
   for rel in ['runtime.json',f'output/{c}.star']:check((up/rel).read_bytes()==(ROOT/c/'ALL'/rel).read_bytes(),'global only bytes differ '+c)
   cf=ROOT/c/'UPFW-compare.json';p=subprocess.run([sys.executable,str(CMP),str(up/'output'),str(ROOT/c/'ALL/output'),str(cf)],capture_output=True,text=True);(ROOT/c/'UPFW-compare.log').write_text(p.stdout+p.stderr);check(p.returncode==0 and json.loads(cf.read_text())['verdict']=='IDENTICAL','UPFW comparator '+c)
  results[c]=result;save(ROOT/'partial_results.json',results)
 save(ROOT/'results.json',results)
if __name__=='__main__':
 try:main()
 except Exception:
  ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'STOP.txt').write_text(traceback.format_exc());raise
