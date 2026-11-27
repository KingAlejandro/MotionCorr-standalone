# Package this task's records, excluding bulk images and plot intermediates.
import pathlib,tarfile,hashlib,json
S=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');out=S/'retained';out.mkdir(exist_ok=True)
for section in ['runs','attempts']:
 with tarfile.open(out/(section+'.tar.gz'),'w:gz',compresslevel=6) as t:
  for p in sorted((S/section).rglob('*')):
   if p.is_file() and p.suffix not in ['.mrc','.mrcs','.eps','.pdf']:
    t.add(p,arcname=str(p.relative_to(S)))
with tarfile.open(out/'logs.tar.gz','w:gz') as t:
 for p in sorted((S/'logs').glob('*')):
  if p.is_file():t.add(p,arcname='logs/'+p.name)
idx=[]
for p in sorted(out.iterdir()):
 if p.is_file():idx.append({'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
json.dump(idx,open(out/'index.json','w'),indent=1)
print(idx)
