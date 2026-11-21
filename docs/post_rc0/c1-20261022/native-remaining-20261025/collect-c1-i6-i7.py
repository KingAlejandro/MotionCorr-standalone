import pathlib,subprocess,hashlib,json,datetime,tarfile,io
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
code=r'''
import pathlib,hashlib,json,tarfile,io,sys
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb')
names=['remaining-i6-20261025','remaining-i7-20261025','dataset-G-archive-regrade-v1-20261025','dataset-G-archive-regrade-v1.1-20261025','matrix-cuda','matrix-nvcomp','a249-i6-20261025','t24-i6-20261025/c1-ds-G','t24-i6-20261025/c1-ds-L','t24-i6-20261025/compare','v2/cuda-unset']
single=['matrix-cuda.json','matrix-nvcomp.json','v2/cuda-unset.eval.json','c1-i6-20261025.sh','c1-i7-datasetL-k267.sh']
allow={'.json','.log','.txt','.star','.xml','.exit','.cmd','.stdout','.stderr','.time','.sha256','.py','.sh'}
files=set()
for name in names:
 root=s/name
 for p in root.rglob('*'):
  if p.is_file() and not p.is_symlink() and (p.suffix in allow or p.name in {'STOP','DONE','finished','started','stdout','stderr','exit'}): files.add(p)
for name in single:
 p=s/name;assert p.is_file(),p;files.add(p)
for p in (s/'logs').iterdir():
 if p.is_file() and not p.is_symlink() and ('i6-' in p.name or 'i7-' in p.name or p.name.startswith('occupancy-v2-')):files.add(p)
buf=io.BytesIO();idx={}
with tarfile.open(fileobj=buf,mode='w:gz') as t:
 for p in sorted(files):
  raw=p.read_bytes();assert len(raw)<16<<20,p
  rel=str(p.relative_to(s));idx[rel]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'remote':str(p)}
  ti=tarfile.TarInfo(rel);ti.size=len(raw);t.addfile(ti,io.BytesIO(raw))
 raw=(json.dumps({'scope':'selected immutable receipts/logs/STAR only; MRC payloads remain in original VM scratch','files':idx},indent=2)+'\n').encode();ti=tarfile.TarInfo('COLLECTED-INDEX.json');ti.size=len(raw);t.addfile(ti,io.BytesIO(raw))
sys.stdout.buffer.write(buf.getvalue())
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','4GPUs','python3 -'],input=code.encode(),capture_output=True,timeout=120);assert r.returncode==0,r.stderr
dest=P/'c1-i6-i7-receipts.tgz';assert not dest.exists();dest.write_bytes(r.stdout)
out=P/'c1-i6-i7-collected';out.mkdir()
with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:t.extractall(out,filter='data')
idx=json.loads((out/'COLLECTED-INDEX.json').read_text())['files']
for rel,m in idx.items():
 raw=(out/rel).read_bytes();assert len(raw)==m['bytes'] and hashlib.sha256(raw).hexdigest()==m['sha256'],rel
rec={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive_sha256':hashlib.sha256(r.stdout).hexdigest(),'archive_bytes':len(r.stdout),'files':len(idx),'content_bytes':sum(m['bytes'] for m in idx.values()),'scope':'receipts/logs/STAR; raw MRC retained on VM; no native rerun'}
(P/'c1-i6-i7-collection.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec,indent=2))
