from pathlib import Path
import os,hashlib,tarfile,json,sys
os.environ['COPYFILE_DISABLE']='1'
root=Path('/tmp/mc-truth-final');out=Path('docs/post_rc0/s1/km_truth')
allfiles=sorted(p for p in root.rglob('*') if p.is_file())
omitted=[p for p in allfiles if p.suffix.lower() in ['.eps','.pdf']]
files=[p for p in allfiles if p not in set(omitted)]
(out/'rendered-products.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n' for p in omitted))
for p in files:
 assert p.suffix.lower() not in ['.mrc','.mrcs','.tif','.tiff','.npy'],p
idx={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
with tarfile.open(out/'raw.tar.gz','w:gz') as t:
 for p in files:t.add(p,arcname='raw/'+str(p.relative_to(root)),recursive=False)
with tarfile.open(out/'raw.tar.gz') as t:
 members={m.name:m for m in t.getmembers() if m.isfile()}
 assert set(members)=={'raw/'+p for p in idx}
 for p,h in idx.items():assert hashlib.sha256(t.extractfile('raw/'+p).read()).hexdigest()==h,p
(out/'raw.sha256').write_text(''.join(f'{h}  {p}\n' for p,h in idx.items()))
(out/'archive-verification.json').write_text(json.dumps(dict(files=len(files),rendered_products_omitted=len(omitted),rendered_products_index_sha256=hashlib.sha256((out/'rendered-products.sha256').read_bytes()).hexdigest(),archive_sha256=hashlib.sha256((out/'raw.tar.gz').read_bytes()).hexdigest(),raw_index_sha256=hashlib.sha256((out/'raw.sha256').read_bytes()).hexdigest(),verification='Every file read back from tar and matched to SHA256; exact file inventory; no MRC/TIFF/NPY movie payloads. Native EPS/PDF renderings omitted with hashes retained; full source archives remain on hosts'),indent=2)+'\n')
print('archived and verified',len(files),'records;', (out/'raw.tar.gz').stat().st_size,'bytes')
