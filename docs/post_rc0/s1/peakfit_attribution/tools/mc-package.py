import pathlib,tarfile,json,hashlib,collections
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');out=s/'retained';out.mkdir(exist_ok=True);rows=json.load(open(s/'rows-all.json'));include=set()
for r in rows:
 mv,g=r['movie'],r['grid']
 for a in ['A0','A1','A2','Nnative1','Nnative2','cpu','cpuDC','parent']:
  d=s/'runs'/f'{mv}-p{g}-{a}'
  if (d/'run.json').exists():include.add(d)
for d in (s/'runs').iterdir():
 if '-G-' in d.name or '-map-' in d.name or d.name.endswith(('A1plain','Noff')):
  if (d/'run.json').exists():include.add(d)
manifest=[];validation=[];groups=collections.defaultdict(list)
for d in sorted(include):
 r=json.load(open(d/'run.json'));assert r['rc']==0,(d,r)
 if r.get('cuda_visible_devices'):assert r['gpu_witness_uuids']==[r['cuda_visible_devices']],(d,r)
 validation.append({'label':d.name,**r})
 group=d.name.split('-p')[0].rsplit('-',1)[0] if '-p' in d.name else d.name.split('-G-')[0].rsplit('-',1)[0]
 grid=('p'+d.name.split('-p')[1].split('-')[0]) if '-p' in d.name else 'global'
 for p in sorted(d.rglob('*')):
  if not p.is_file() or 'maps' in p.relative_to(d).parts:continue
  # Keep every scalar/capture/metadata record; MRC and rendered reports stay in scratch.
  if p.suffix not in ['.json','.log','.star','.txt'] and p.name not in ['witness']:continue
  b=p.read_bytes();item={'path':str(p.relative_to(s)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};manifest.append(item);groups[group+'-'+grid].append(p)
for group,files in sorted(groups.items()):
 p=out/(group+'.tar.gz')
 with tarfile.open(p,'w:gz',compresslevel=6) as t:
  for f in files:t.add(f,arcname=str(f.relative_to(s)))
 print(group,len(files),p.stat().st_size,flush=True)
 assert p.stat().st_size<95_000_000
json.dump(manifest,open(out/'capture-manifest.json','w'),indent=1)
json.dump(validation,open(out/'run-ledger.json','w'),indent=1)
# Reference STARs and original #255 metadata, without changing retained references.
with tarfile.open(out/'original-references.tar.gz','w:gz') as t:
 for r in rows:
  d=pathlib.Path(r['reference_run'])
  for p in sorted(d.rglob('*')):
   if p.is_file() and (p.suffix in ['.json','.star','.log'] or p.name=='run.txt'):t.add(p,arcname='references/'+r['movie']+'-p'+str(r['grid'])+'/'+str(p.relative_to(d)))
print('runs',len(validation),'files',len(manifest),flush=True)
