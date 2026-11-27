"""Parent R4 F1/F2 post-build/run bindings. Metadata-only; no grader rerun."""
import json,hashlib,subprocess
from pathlib import Path
remote=r'''
from pathlib import Path
import subprocess,json,hashlib,time,re
S=Path('/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def file(p):
 if not p.is_file():return None
 b=p.read_bytes();return {'sha256':hashlib.sha256(b).hexdigest(),'text':b.decode()}
r={'utc':time.strftime('%FT%TZ',time.gmtime()),'chain_exit':file(S/'launch-cpu1/chain.exit'),'chain_log':file(S/'logs/CHAIN.txt'),'stop':file(S/'logs/CHAIN.stopped_at'),'processes':{},'builds':{},'rows':{},'known':file(S/'n3-cpu1/known-observations.json'),'grade':file(S/'n3-cpu1/RESULTS.json'),'subset':file(S/'n3-cpu1/CPU_SUBSET.json'),'stage_exits':{p.name:p.read_text() for p in (S/'logs').glob('cpu1-*.exit')}}
for pid in [3315461,3315463]:
 p=Path(f'/proc/{pid}');r['processes'][str(pid)]=None if not p.exists() else {'stat':(p/'stat').read_text(),'status':(p/'status').read_text(),'argv':(p/'cmdline').read_bytes().replace(bytes([0]),b' ').decode()}
for a in ['base','cand','mut']:
 arm=f'ov-{a}-cpu';b=S/f'build-{arm}';log=S/f'logs/cpu1-b-{arm}.log'
 row={'build_receipt':file(S/f'build-{arm}.binaries.sha256'),'source_lines':[],'cache_selected':[]}
 if log.exists():row['source_lines']=[l for l in log.read_text().splitlines() if l.startswith('source ')]
 if (b/'CMakeCache.txt').exists():row['cache_selected']=[l for l in (b/'CMakeCache.txt').read_text().splitlines() if l.startswith(('CUDA:','CMAKE_HOME_DIRECTORY:','CMAKE_BUILD_TYPE:','MC_REQUIRE_ALL_DECODERS:'))]
 if row['build_receipt'] is not None:
  row['actual_binary_sha256']=sha(b/'motioncorr');row['ldd']=subprocess.check_output(['ldd',str(b/'motioncorr')],text=True)
 r['builds'][arm]=row
for p in sorted((S/'n3-cpu1').glob('ov-*-cpu/*/RUN.json')):r['rows'][str(p.relative_to(S/'n3-cpu1'))]=file(p)
print(json.dumps(r))
'''
p=Path('/tmp/motioncorr-orchestrator-20261022')
r=subprocess.run(['ssh','-J','ccp4-gateway','-oBatchMode=yes','-oConnectTimeout=10','-oConnectionAttempts=1','4GPUs','taskset','-c','13','/home/alex/.mc-venv/bin/python3','-'],input=remote,text=True,capture_output=True,timeout=35)
(p/'guard-cpu1-parent-postcheck-v2.stderr').write_text(r.stderr);assert r.returncode==0,(r.returncode,r.stderr)
(p/'guard-cpu1-parent-postcheck-v2.json').write_text(r.stdout);j=json.loads(r.stdout)
out={'utc':j['utc'],'source':'3751bd05a95412dff468557141f2e7e01ad21831','readback_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'native_CPU_rows_recorded':len(j['rows']),'stage_exits':j['stage_exits'],'stop':None if j['stop'] is None else j['stop']['text'],'status':'ONGOING' if j['chain_exit'] is None else 'TERMINAL_REQUIRES_VERIFICATION','build_bindings':{}}
diffs={'base':('3691374061f782bc84531fd1c79d017ddcb5a7c2','4b01e2607e1ffc86a719ccbf68afbfe5789f2a5b026efe6921eeed62af7d8316',1),'cand':('3751bd05a95412dff468557141f2e7e01ad21831','26274cd38b2ab2026ad5fd3ebab8ecd5fce2a6210aa8fef035e78eb6f4aa2de0',1),'mut':('3751bd05a95412dff468557141f2e7e01ad21831','74b983bccff71b062ca535e057bb1d3e3cad2e9dfb44bb503bfc902304c485b9',2)}
for a,(rev,diff,n) in diffs.items():
 b=j['builds'][f'ov-{a}-cpu'];want=f'source {rev} dirty-diff-sha256 {diff} status-lines {n}'
 if b['source_lines']:assert b['source_lines']==[want],(a,b['source_lines'])
 if b['build_receipt'] is not None:
  h=b['build_receipt']['text'].split()[0];assert h==b['actual_binary_sha256']
  assert 'CUDA:BOOL=OFF' in b['cache_selected'] and 'CMAKE_BUILD_TYPE:STRING=Release' in b['cache_selected']
  assert not any(x in b['ldd'].lower() for x in ['libcuda','libcufft','libnvcomp'])
  out['build_bindings'][a]=h
if j['chain_exit'] is not None:
 out['chain_exit']=int(j['chain_exit']['text'].strip())
 assert len(out['build_bindings'])==3 and len(set(out['build_bindings'].values()))==3
 known=json.loads(j['known']['text']);rows={}
 for path,v in j['rows'].items():
  z=json.loads(v['text']);key=z['arm']+'/'+z['case'];assert key not in rows;rows[key]=z
 assert set(rows)==set(known['rows']) and len(rows)==24
 for key,k in known['rows'].items():
  z=rows[key];assert z['rc']==0 and z['gpu'] is False and not z['gpu_uuids_witnessed']
  spec=z['env'].get('MC264_N3_COEFFS')
  assert spec==k.get('MC264_N3_COEFFS'),key
  if k['overlay']:assert hashlib.sha256(spec.encode()).hexdigest()==k['spec_sha256']
  a=z['arm'].removeprefix('ov-').removesuffix('-cpu');assert z['binary_sha256']==out['build_bindings'][a],key
 subset=json.loads(j['subset']['text']);grade=json.loads(j['grade']['text'])
 out['subset_verdict']=subset['cpu_subset_verdict'];out['subset_problems']=subset['problems']
 assert subset['full_n3_n4_aggregate']=='INCOMPLETE: 16 CUDA rows UNRUN'
 assert grade['summary']['runs']=={'PASS':24,'FAIL':0,'UNRUN':16}
 out['grade_summary']=grade['summary'];out['failed_pairs']=[x for x in grade['base_vs_candidate'] if x['status']!='PASS']
 assert set(grade['n4_mutant']['cases_where_mutant_decision_differs_from_candidate'])=={'A_x_legacy_false_accept','B_x_legacy_false_reject','A_y_legacy_false_accept','B_y_legacy_false_reject','E_xy_nonsquare_near_threshold'}
 out.update(status='BINDINGS_VERIFIED_NATIVE_SUBSET_'+subset['cpu_subset_verdict'],F1_source_and_build_bindings='3/3',F2_exact_injection_bindings='21/21 plus3no-overlay',binary_bindings='24rows/3arms/3distinctverifiedbinaries',full_N3_N4='INCOMPLETE:16CUDArowsUNRUN',limits='Actual CPU runner with TEST-ONLY injected observations; not motion-estimation accuracy, production ordinary-movie, CUDA, performance, parity adoption or scientific qualification.')
(p/'guard-cpu1-parent-postcheck-v2-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
