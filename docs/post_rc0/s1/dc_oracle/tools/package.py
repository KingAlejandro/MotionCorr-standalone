#!/usr/bin/env python3
"""Retain compact native records, full hashes, measurements and build receipts.
Run on 4GPUs; bulk maps, CCF text and MRCs remain in task scratch.
"""
import hashlib,json,pathlib,shutil,struct,subprocess,sys,tarfile
import analyze as a
s=pathlib.Path(sys.argv[1]);out=s/'evidence';out.mkdir(exist_ok=True)
for d in ['results','raw']: (out/d).mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
for name in ['rows.json','summary.json','controls.json','native-stage.json','run-ledger.json']:
 shutil.copy(s/'analysis'/name,out/'results'/name)
shutil.copy(s/'stage-results.json',out/'results/stage.json')
shutil.copy(s/'input-manifest.json',out/'results/input-manifest.json')
shutil.copy(s/'stage-provenance.json',out/'results/stage-provenance.json')
shutil.copy(s/'cpu64-input-verification.json',out/'results/input-transfer-verification.json')
for name in ['parent-source-validation.json','parent-blobs.json','build-receipts.json','toolchain.txt','stage.log','native-stage.log','offload.log','source-validation.json','source-blobs.json','source-sha.txt','parent-sha.txt','native-tests.log','native-tests.exit','cpu-tests.log','configure.log','configure-attempt1.log','build.log','model-build.log','parent-configure.log','parent-build.log','tests-configure.log','tests-build.log']:
 if (s/name).exists():shutil.copy(s/name,out/'raw'/name)
shutil.copy(s/'cpu64-source-validation.json',out/'raw/cpu64-source-validation.json')
# All primary records and the parent/unset/capture controls, each with explicit
# argv/env, source/binary hash, affinity, exit, native global/model and STAR.
ledger=json.load(open(s/'analysis/run-ledger.json'));assert len(ledger)==600
paths={pathlib.Path(r['argv'][r['argv'].index('--o')+1]) for r in ledger}
# CPU paths in original records are host-native; select verified copied dirs.
paths={s/'cpu64/runs'/p.name if str(p).startswith('/tmp/alex-motioncorr-dc-oracle/') else p for p in paths}
paths.update(p for p in (s/'runs').iterdir() if (p/'run.json').exists() and any(t in p.name for t in ['-parent','-offCPU','-offGPU','-capture-']))
# Include six independent 4GPUs CPU R/Rprime/C_none controls too.
for mv in ['e10216-00','e12963-00','e10474f3-00']:
 for g in [5,3]:
  for arm in ['R','Rprime','C_none']:paths.add(s/'runs'/f'{mv}-p{g}-{arm}')
manifest={};products={};large={};patches={};archive=out/'raw/native-records.tar.gz'
with tarfile.open(archive,'w:gz') as tf:
 for d in sorted(paths):
  if (d/'ccf.txt').exists():
   q={}
   for patch,groups in a.ccf(d).items():
    tag,it=a.chosen(groups);_,rms=a.traj(it,tag.startswith('cuda'));q['%d,%d'%patch]={'tag':tag,'increment_rmsd_px':rms,'converged':rms[-1]<.5}
   patches[str(d.relative_to(s))]=q
  for p in sorted(d.rglob('*')):
   if not p.is_file():continue
   name=str(p.relative_to(s));size=p.stat().st_size
   if p.suffix=='.mrc':
    h=hashlib.sha256();payload=hashlib.sha256()
    with p.open('rb') as f:
     header=f.read(1024);h.update(header);ext=struct.unpack_from('<i',header,92)[0];e=f.read(ext);h.update(e)
     for b in iter(lambda:f.read(4<<20),b''):h.update(b);payload.update(b)
    products[name]={'bytes':size,'sha256':h.hexdigest(),'core_header_sha256':hashlib.sha256(header[:224]).hexdigest(),'payload_sha256':payload.hexdigest(),'extended_header_bytes':ext}
   elif p.name=='ccf.txt' or 'maps' in p.parts or p.suffix=='.star' or (p.suffix=='.log' and p.name!='time-v.log'):
    large[name]={'bytes':size,'sha256':sha(p)}
   elif p.name in ['run.json','global.txt','model.txt','time-v.log','witness.txt']:
    digest=sha(p);manifest[name]={'bytes':size,'sha256':digest};tf.add(p,arcname=name)
# Bind the stage inputs and every selected dump to its retained scratch path.
for p in sorted((s/'stage-inputs').rglob('*')):
 if p.is_file():large[str(p.relative_to(s))]={'bytes':p.stat().st_size,'sha256':sha(p)}
for name,data in [('ccf-summary.json',patches),('native-records-manifest.json',manifest),('products-manifest.json',products),('large-captures-manifest.json',large)]:json.dump(data,open(out/'raw'/name,'w'),indent=1)
json.dump({'primary_runs':len(ledger),'selected_run_dirs':len(paths),'small_native_files':len(manifest),'products':len(products),'large_capture_files':len(large),'native_archive_sha256':sha(archive),'bulk_root':str(s),'notes':'The committed archive omits full STARs/movie logs, CCF text, spectra/maps, PDFs and MRCs. Their hashes bind retained scratch artifacts; pixel metrics cannot be recomputed from the compact archive alone. Preliminary 97fd8107 runs and the interrupted local-relay input transfer are administrative history, excluded from the final census.'},open(out/'raw/package.json','w'),indent=1)
print('PACKAGED',len(ledger),'primary',len(paths),'selected','archive MB',archive.stat().st_size/1e6)
