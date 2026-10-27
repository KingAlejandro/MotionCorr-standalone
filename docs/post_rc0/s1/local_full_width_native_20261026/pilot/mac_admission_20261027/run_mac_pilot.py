#!/usr/bin/env python3
"""Mac venue driver: unchanged v3 producer/scoring consumer, frozen command rows."""
import ast, hashlib, json, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
PILOT=Path(__file__).resolve().parents[1]
REPO=PILOT.parents[4]
ROOT=Path('/tmp/mc-mac-pilot-20261027/mac-native-r1')
FX=Path('/tmp/mc-mac-pilot-20261027/fixtures-numpy253')
BIN=Path('/tmp/mc-mac-pilot-20261027/build-numpy253/motioncorr')
BSHA='d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546'
GS=Path('/opt/homebrew/bin/gs'); GSHA='d57bb373324bf7e72c5b3fb1a6cc8a9f876eb6f8d2eec23a5a3809a8a108bf9e'
CONSUMER=Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
sys.path.insert(0,str(PILOT)); import score_fields_v3 as V3
ADM=json.loads((PILOT/'ADMISSION_DRAFT_v3.json').read_text()); CMDS=json.loads((PILOT/'COMMANDS_DRAFT_v3.json').read_text())
COMMON=REPO/'docs/post_rc0/s1/native_b2_upstream_factorial_20261026/scripts/factorial_common.py'
CMP=REPO/'docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py'
CASES=ADM['case_order']; PREFIX=V3.CONTROLLED_PREFIXES
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def info(p): return {'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,obj): p.write_text(json.dumps(obj,indent=1,allow_nan=False)+'\n')
def check(ok,msg):
 if not ok: raise RuntimeError(msg)
def pinned_functions():
 source=COMMON.read_text(); tree=ast.parse(source); nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('star_blocks','manipulation')]; check(len(nodes)==2,'helper functions missing'); ns={'re':re,'Path':Path,'check':check}; exec(compile(ast.Module(body=nodes,type_ignores=[]),str(COMMON),'exec'),ns); return ns['star_blocks'],ns['manipulation']
def occupancy(d):
 p=subprocess.run(['/bin/ps','-Ao','pid,pcpu,comm'],capture_output=True,text=True,check=True)
 disk=shutil.disk_usage('/tmp'); check(disk.free>3*1024**3,'less than 3 GiB scratch free'); (d/'occupancy.txt').write_text(subprocess.check_output(['/usr/bin/uptime'],text=True)+f'free_bytes={disk.free}\n'+p.stdout)
def run(case,arm,blocks,manip):
 d=ROOT/case/arm; d.mkdir(parents=True,exist_ok=False); occupancy(d)
 check(sha(BIN)==BSHA and sha(GS)==GSHA,'binary or Ghostscript identity changed')
 e=V3.resolve_expected_row(CMDS,ADM,case,arm,str(ROOT),str(BIN),BSHA); inp=d/'input'; inp.mkdir()
 for n in e['input_files']: shutil.copyfile(FX/n,inp/n)
 env={k:v for k,v in os.environ.items() if not k.startswith(PREFIX)}; env.update(e['environment']); env['PATH']='/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
 started=time.time(); p=subprocess.run(e['argv'],cwd=inp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); (d/'stdout.log').write_bytes(p.stdout)
 out=d/'output'; pub={str(x.relative_to(out)):info(x) for x in sorted(out.rglob('*')) if x.is_file()} if out.exists() else {}
 receipt={'schema':V3.RECEIPT_SCHEMA,'case':case,'arm':arm,'exit':p.returncode,'binary_sha256':BSHA,'run_dir':str(d.resolve()),'argv':e['argv'],'cwd':e['cwd'],'environment':e['environment'],'controlled_environment_observed':{k:v for k,v in env.items() if k.startswith(PREFIX)},'publication':pub,'runtime':info(d/'runtime.json') if (d/'runtime.json').is_file() else None,'stdout':info(d/'stdout.log'),'producer_path':env['PATH'],'wall_seconds':time.time()-started}
 save(d/'RUN.json',receipt); check(p.returncode==0,'producer failed '+case+'/'+arm)
 V3.admit_producer(d,e,ADM,ROOT); check((out/'logfile.pdf').stat().st_size>0,'empty PDF')
 m=manip(d/'stdout.log'); local=e['patch_grid']==[3,3]; check(m['dc']['global_eligible']>0,'missing global DC'); check((m['dc']['local_eligible']>0) if local else (m['dc']['local_eligible']==0 and m['coupled']['patch']['peaks']==0),'local manipulation coverage')
 scores=V3.score_admitted(d,e,ADM,ROOT,FX); save(d/'score.json',scores)
 model=json.loads((d/'runtime.json').read_text()); b=blocks(out/(case+'.star')); check('global_shift' in b,'missing STAR global block')
 conv=V3.V2.R.convergence(out/(case+'.log')); save(d/'facts.json',{'manipulation':m,'convergence':conv,'local_enabled':model['local_enabled']})
 return {'g':np.asarray(model['global'],dtype=np.float64).view(np.uint64).tolist(),'block':b['global_shift'],'man':m,'score':scores,'conv':conv}
def main():
 ROOT.mkdir(parents=True,exist_ok=False); check(sha(BIN)==BSHA and sha(GS)==GSHA,'binary or Ghostscript identity'); check(subprocess.check_output([str(GS),'--version'],text=True).strip()=='10.08.0','Ghostscript version'); V3.verify_tool_pins(ADM,{'consumer_source':CONSUMER,'repo':REPO,'pilot':PILOT})
 for n,pin in ADM['fixture_files'].items(): check((FX/n).is_file() and (FX/n).stat().st_size==pin['bytes'] and sha(FX/n)==pin['sha256'],'fixture pin '+n)
 blocks,manip=pinned_functions(); results={}
 for case in CASES:
  off=run(case,'OFF',blocks,manip); on=run(case,'ON',blocks,manip)
  check(off['g']==on['g'] and off['block']==on['block'],'global mismatch '+case)
  for k in ('global_zeroed','global_eligible'): check(off['man']['dc'][k]==on['man']['dc'][k],'global DC mismatch '+case)
  check(off['man']['coupled']['global']==on['man']['coupled']['global'],'global coupled mismatch '+case)
  if case in ('zero','integer','fractional','flat','repeated'):
   for rel in ('runtime.json',f'output/{case}.star'): check((ROOT/case/'OFF'/rel).read_bytes()==(ROOT/case/'ON'/rel).read_bytes(),'global-only bytes mismatch '+case)
   cmpout=ROOT/case/'compare.json'; c=subprocess.run([sys.executable,str(CMP),str(ROOT/case/'OFF/output'),str(ROOT/case/'ON/output'),str(cmpout)],capture_output=True,text=True); (ROOT/case/'compare.log').write_text(c.stdout+c.stderr); check(c.returncode==0 and json.loads(cmpout.read_text())['verdict']=='IDENTICAL','product comparator '+case)
  results[case]={'OFF':off,'ON':on}; save(ROOT/'partial_results.json',results)
 save(ROOT/'results.json',results)
if __name__=='__main__':
 try: main()
 except Exception as exc:
  ROOT.mkdir(parents=True,exist_ok=True); (ROOT/'STOP.txt').write_text(traceback.format_exc()); print('STOP:',repr(exc),flush=True); raise
