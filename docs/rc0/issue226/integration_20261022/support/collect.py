"""Retain compact combined-source receipts, never source/binary/movie payloads."""
import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
W=Path('/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z')
sys.path.insert(0,str(W/'support'))
from health import snapshot

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def command(name,argv,cwd=W):
    r=subprocess.run(argv,cwd=cwd,capture_output=True,text=True)
    (W/'logs'/f'{name}.log').write_text(r.stdout+r.stderr)
    (W/'logs'/f'{name}.exit').write_text(str(r.returncode)+'\n')
    assert r.returncode==0,(name,r.returncode)
    return dict(argv=argv,exit=r.returncode,stdout=r.stdout,stderr=r.stderr)

for phase in ('complete-build','native','products'):
    assert (W/'logs'/f'{phase}.exit').read_text().strip()=='0',phase
release=[command('released-'+n,['flock','-n','/tmp/motioncorr-'+n+'.lock','true']) for n in ('gpu3-correctness','build','bench')]
post=snapshot('collected-post',idle=True)
checks=command('production-source-final',['sha256sum','-c',str(W/'support/production-source.sha256')],W/'src')
command('binaries-final',['sha256sum',*[str(W/'build'/n) for n in ('motioncorr','cuda_local_admission','motioncorr_faultinject','motioncorr_streaming_plan_fault','patch_retry_admission','patch_retry_state')]])
command('binary-libraries',['ldd',str(W/'build/motioncorr')])
command('source-and-support-identities',['sha256sum',str(W/'source.tar.gz'),*[str(p) for p in sorted((W/'support').glob('*')) if p.is_file()]])
prov=json.loads((W/'logs/product-provenance.json').read_text())
assert sha(Path(prov['input']))==prov['input_sha256']
assert sha(W/'build/motioncorr')==prov['files'][str(W/'build/motioncorr')]
products=json.loads((W/'logs/product-results.json').read_text())
grades=json.loads((W/'matrix/grades.json').read_text())
receipts=[json.loads(p.read_text()) for d in ('matrix','early') for p in sorted((W/d).glob('*.json')) if p.stem!='inputs' and p.stem!='grades']
receipts=[r for r in receipts if 'binary_sha256' in r]
assert len(receipts)==19,len(receipts)
assert len(grades)==16 and all(not r['problems'] for r in grades)
health=[json.loads(l) for l in (W/'logs/health.jsonl').read_text().splitlines()]
local=(W/'logs/local-admission.log').read_text()
assert local.count('BOUNDARY free=')==28
assert 'spectrum=158299360 complete_required=191819184' in local
assert 'REVIEW free=175000000 admitted=0' in local
launches=[json.loads(l) for l in (W/'logs/native-launches.jsonl').read_text().splitlines()]
runner_launches=[r for r in launches if r['argv'][0]=='/usr/bin/time']
balloons=[r for r in launches if r['argv'][0]==str(W/'balloon')]
assert len(runner_launches)==4 and len(balloons)==3
status=dict(native_build_source='fe104f217703871c897887a9b7ca3a6bff4b7b69',scratch=str(W),gpu_uuid=post['uuid'],cpus=[10,11,12,13],compile_parallelism=2,runtime_threads=1,numeric_threads=1,
    statuses={'CUDA_nvcomp_Release_compile':'PASS','PatchRetryAdmission_State':'PASS 2/2','required_collection_and_failclosed':'PASS','missing_three_controls':'PASS','CudaLocalAdmission':'PASS 28 boundaries plus review interval','CudaEarlyStreamingOom':'PASS','CudaStreamingPlanClassificationCleanup':'PASS 16/16','e10216_completion_publication':'PASS 4/4','e10216_strict_MRC_STAR_products':'PASS 3/3','e10216_whole_tree':'FAIL 3/3 expected log differences','post_health_release':'PASS','full_suites':'UNRUN','science':'UNRUN','performance':'UNRUN','genuinely_poisoned_device':'UNRUN'},
    process_counts={'MotionCorr_D3_controls_including_references':len(receipts),'MotionCorr_QM_runner':len(runner_launches),'MotionCorr_total':len(receipts)+len(runner_launches),'native_admission_executable':1,'host_retry_executables':2,'balloons':len(balloons)},
    native={'e10216_retry_required_bytes':191819184,'review_headroom_bytes':175000000,'review_admitted':False,'boundary_rows':28,'matrix':grades},provenance=prov,products=products,post_health=post,health_sample_count=len(health),release_probes=release,production_source_file_count=len(checks['stdout'].splitlines()),
    preparation={'selected_compile_exit':int((W/'logs/compile.exit').read_text()),'initial_collection_exit':int((W/'logs/collection-validation.exit').read_text()),'initial_collection_reason':json.loads((W/'logs/collection-validation.json').read_text())['reason'],'resolution':'Compile remaining registered executables under same source/flags/lock; no native rerun. Final collection passes.'},
    limitations=['D3 fatal statuses are simulated classifier returns around real healthy GPU work.','Only one frozen e10216 movie, no physical small-card or host-OOM qualification.','No performance comparison; time/RSS are provenance during parallel work.','Kernel Xid logs unavailable to account in prior venue; no kernel-log qualification claimed.','Standalone collection-only merge 6a2e6c1d retains these tested production/CMake/native-test bytes; host checks separately recorded locally.'])
(W/'integration.json').write_text(json.dumps(status,indent=2)+'\n')
paths=[]
for directory in ('logs','matrix','early','runs','inputs','support'):
    for p in sorted((W/directory).rglob('*')):
        if not p.is_file() or p.is_symlink() or p.suffix in ('.mrc','.mrcs','.pdf','.pyc') or '__pycache__' in p.parts:continue
        paths.append(p)
paths += [W/'source.sha256',W/'integration.json']
index=dict(schema=1,excluded=['executables','source archive','bulk and synthetic MRC/MRCS/PDF','input symlinks'],files=[dict(path=str(p.relative_to(W)),bytes=p.stat().st_size,sha256=sha(p)) for p in paths])
(W/'raw-index.json').write_text(json.dumps(index,indent=2)+'\n')
with tarfile.open(W/'raw-logs.tgz','x:gz') as tf:
    for p in paths:tf.add(p,arcname=p.relative_to(W),recursive=False)
(W/'archive.sha256').write_text(sha(W/'raw-logs.tgz')+'  raw-logs.tgz\n')
print(json.dumps(dict(statuses=status['statuses'],process_counts=status['process_counts'],raw_files=len(paths),archive_bytes=(W/'raw-logs.tgz').stat().st_size,health_samples=len(health)),indent=2))
