"""Parent readback of completed T24 CPU L; source/report identity, no native rerun."""
import hashlib,json,subprocess
from pathlib import Path
remote=r'''
from pathlib import Path
import json,hashlib,time,subprocess
S=Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb')
paths=['t24-cpu1d/c1-cpu-L/RUN.json','t24/F-cpu-L/RUN.json','cpu1d-v2-check.json','cpu1d-prereq.json','t24-cpu1d/compare/F-cpu_vs_c1-cpu-L.json','t24-cpu1d/compare/F-cpu_vs_c1-cpu-L.run.json','t24-cpu1d/compare/F-cpu_vs_c1-cpu-L.class.json']
paths += [f'logs/cpu1d-{n}.{x}' for n in ['run-c1-cpu-L','cmp-cpu-L'] for x in ['cmd','pid','started','finished','exit','log']]
r={'utc':time.strftime('%FT%TZ',time.gmtime()),'source':subprocess.check_output(['git','-C',str(S/'src'),'rev-parse','HEAD'],text=True).strip(),'source_status':subprocess.check_output(['git','-C',str(S/'src'),'status','--porcelain'],text=True),'files':{},'processes':{}}
for p in paths:
 b=(S/p).read_bytes();r['files'][p]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'text':b.decode()}
for pid in [3311648,3311661]:
 d=Path(f'/proc/{pid}')
 r['processes'][str(pid)]=None if not d.exists() else {'stat':(d/'stat').read_text(),'status':(d/'status').read_text(),'argv':(d/'cmdline').read_bytes().replace(bytes([0]),b' ').decode()}
r['local_stage_reserved']=(S/'logs/cpu1d-run-c1-cpu-L.reserved').exists()
r['local_stage_exit']=(S/'logs/cpu1d-run-c1-cpu-L.exit').read_text() if (S/'logs/cpu1d-run-c1-cpu-L.exit').exists() else None
r['chain_stop']=(S/'logs/chain-cpu1d.stop').read_text() if (S/'logs/chain-cpu1d.stop').exists() else None
print(json.dumps(r))
'''
p=Path('/tmp/motioncorr-orchestrator-20261022')
r=subprocess.run(['ssh','-J','ccp4-gateway','-oBatchMode=yes','-oConnectTimeout=10','-oConnectionAttempts=1','4GPUs','taskset','-c','13','/home/alex/.mc-venv/bin/python3','-'],input=remote,text=True,capture_output=True,timeout=35)
(p/'c1-cpu1d-L-parent-readback.stderr').write_text(r.stderr);assert r.returncode==0,(r.returncode,r.stderr)
(p/'c1-cpu1d-L-parent-readback.json').write_text(r.stdout);j=json.loads(r.stdout)
assert j['source']=='e77a51a220cb0d91f4ac3c7fac211876d0c6833f' and not j['source_status']
f=j['files'];load=lambda n:json.loads(f[n]['text']);prefix='t24-cpu1d/compare/F-cpu_vs_c1-cpu-L'
c=load(prefix+'.class.json');q=load(prefix+'.json');run=load(prefix+'.run.json')
assert c['state']=='IDENTICAL' and not c['products'] and not c['reasons']
assert c['report_sha256']==run['report_sha256']==f[prefix+'.json']['sha256'] and run['rc']==0
assert q['status']=='PASS' and q['comparison_scope']=='products' and not q['different_products'] and not q['different_files']
for side in ['base','candidate']:assert q[side]['movie_count']==q[side]['mrc_count']==24 and q[side]['star_count']==25
assert len(q['mrc_sha256'])==24
for name,v in q['mrc_sha256'].items():
 for part in ['header','extended','payload']:assert v['base_'+part]==v['candidate_'+part],(name,part)
a=load('t24-cpu1d/c1-cpu-L/RUN.json');b=load('t24/F-cpu-L/RUN.json')
assert a['rc']==b['rc']==0 and a['gpu_run'] is b['gpu_run'] is False
assert a['binary_sha256']=='5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c'
assert b['binary_sha256']=='43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42'
assert f['t24/F-cpu-L/RUN.json']['sha256']=='4b2ffd1fcfee0ccd9d04abedfc3d30560ad5a0ea189a34ed4a7adb626b0d97cb'
for rec in [a,b]:assert rec['cpu_mask']=='8-9' and rec['env']['OMP_NUM_THREADS']=='2'
assert a['input_star_sha256']==b['input_star_sha256']=='fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041'
for n in ['run-c1-cpu-L','cmp-cpu-L']:assert f[f'logs/cpu1d-{n}.exit']['text'].strip()=='0'
assert a['cleanup']['remaining']==[] and not a['cleanup']['sigterm'] and not a['cleanup']['sigkill']
v=load('cpu1d-v2-check.json');assert not v['invalid'] and not v['problems'] and len(v['rows'])==8
assert all(x['c1_equals_same_host_F'] for x in v['rows'].values())
counts={s:sum(x['checker_status']==s for x in v['rows'].values()) for s in ['PASS','FAIL','UNIDENTIFIABLE']}
out={'utc':j['utc'],'status':'PASS_BOUNDED_ENGINEERING_CPU_L_ONLY','tested_source':j['source'],'readback_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'native_exit':0,'comparison_exit':0,'inventory':{'movies':24,'MRC':24,'STAR':25},'MRC_equal_header_extended_payload':24,'product_comparison':'IDENTICAL under unchanged products comparator; STAR uses documented output-root normalization','source_binary_input_pins':'MATCH','cpu_mask':'8-9','OMP_NUM_THREADS':2,'cleanup_receipt_no_remaining':True,'v2_field_status_counts':counts,'v2_scope':'Eight field/status rows equal same-hostF; no image/signal qualification. Old ABORT records retained separately.','CPU_local_reserved':j['local_stage_reserved'],'CPU_local_exit':j['local_stage_exit'],'chain_stop':j['chain_stop'],'aggregate':'T24 CPU local complete; remaining chain status recorded separately. No C1 qualification/science/performance PASS. GPU rows and individual-fix CUDA MRC attribution pending.'}
(p/'c1-cpu1d-L-parent-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
