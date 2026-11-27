"""Index bounded receipts, excluding executables and bulk MRC/PDF products."""
import hashlib, json, os, subprocess, sys, tarfile, time
from pathlib import Path
W=Path('/mnt/clathrin/alex-pr252-native-retry-20261022T150600Z')
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
    if r.returncode: raise RuntimeError(name+' failed')
    return {'argv':argv,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}

for label in ('build','native','products','production-source-check'):
    if (W/'logs'/f'{label}.exit').read_text().strip()!='0': raise RuntimeError(label+' did not pass')
releases=[]
for name in ('gpu3-correctness','build','bench'):
    releases.append(command('released-'+name,['flock','-n','/tmp/motioncorr-'+name+'.lock','true']))
post=snapshot('collected-post',idle=True)
checks=command('production-source-final',['sha256sum','-c',str(W/'support/production-source.sha256')],cwd=W/'src')
command('binaries-final',['sha256sum',*[str(W/'build'/f) for f in ('motioncorr','cuda_local_admission','patch_retry_admission','patch_retry_state')]])
command('binary-libraries',['ldd',str(W/'build/motioncorr')])
command('source-test-identities',['sha256sum',str(W/'source.tar.gz'),str(W/'src/tests/cuda_local_admission.cpp'),str(W/'src/tests/test_patch_retry_admission.cpp'),str(W/'src/tests/test_patch_retry_state.cpp')])
# Post-run movie identity must still equal the frozen corpus value.
prov=json.loads((W/'logs/product-provenance.json').read_text())
assert sha(Path(prov['input']))==prov['input_sha256']
assert sha(W/'build/motioncorr')==prov['files'][str(W/'build/motioncorr')]
products=json.loads((W/'logs/product-results.json').read_text())
health=[json.loads(l) for l in (W/'logs/health.jsonl').read_text().splitlines()]
status={'source':'868d1fbb2394119a88dc5b02fdff77618109320b','scratch':str(W),
 'gpu_uuid':post['uuid'],'cpus':'10-13','numeric_threads':1,'compile_parallelism':2,
 'statuses':{'cuda_nvcomp_release_build':'PASS','PatchRetryAdmission':'PASS','PatchRetryState':'PASS',
             'CudaLocalAdmission_with_receipt_overlay':'PASS','native_spectrum_only_mutant_discrimination':'PASS',
             'e10216_runner_completion_and_publication':'PASS','e10216_MRC_STAR_identity_3_of_3':'PASS',
             'post_health_and_resource_release':'PASS','full_suites':'UNRUN','scientific_validation':'UNRUN',
             'performance_qualification':'UNRUN','physical_smaller_card':'UNRUN'},
 'native':{'boundary_required_bytes':191819184,'review_free_bytes':175000000,'review_admitted':False,
           'mutant_expected_exit':1,'mutant_actual_exit':int((W/'logs/native-omission-mutant.exit').read_text()),
           'mutant_expected_diagnostic':'FAIL: incorrect complete retry admission boundary'},
 'provenance':prov,'mutant':json.loads((W/'logs/mutant-identities.json').read_text()),
 'products':products,'post_health':post,'health_sample_count':len(health),
 'release_probes':releases,'production_source_files_checked':len(checks['stdout'].splitlines()),
 'limitations':['Native admission uses a wrapped free-memory query and real cuFFT; product fallback uses a real VRAM balloon.',
                'Whole non-PDF tree comparisons exit 1 solely for expected per-movie log route/memory differences; strict MRC/STAR product comparisons exit 0.',
                'No kernel Xid log access: dmesg is denied on this account; CUDA error checks and nvidia-smi ECC/remap checks are retained.',
                'One frozen e10216 movie only. Historical bb348554 results do not qualify this source. D3/#251 absent.']}
(W/'native.json').write_text(json.dumps(status,indent=2)+'\n')
paths=[]
for root in ('logs','runs','support','inputs'):
 for p in sorted((W/root).rglob('*')):
    if not p.is_file() or p.is_symlink() or p.suffix in ('.mrc','.pdf','.pyc') or '__pycache__' in p.parts:continue
    paths.append(p)
paths.extend([W/'source.sha256',W/'native.json'])
index={'schema':1,'excluded':['executables','bulk MRC/PDF files','source archive','input movie symlinks'],
       'files':[{'path':str(p.relative_to(W)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]}
(W/'raw-index.json').write_text(json.dumps(index,indent=2)+'\n')
with tarfile.open(W/'raw-logs.tgz','x:gz') as tf:
 for p in paths: tf.add(p,arcname=p.relative_to(W),recursive=False)
(W/'archive.sha256').write_text(sha(W/'raw-logs.tgz')+'  raw-logs.tgz\n')
print(json.dumps({'statuses':status['statuses'],'raw_files':len(paths),'archive_bytes':(W/'raw-logs.tgz').stat().st_size,'health_samples':len(health)},indent=2))
