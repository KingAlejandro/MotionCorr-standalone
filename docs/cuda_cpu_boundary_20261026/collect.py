#!/usr/bin/env python3
"""File-only collection; preserves arrays/receipts and verifies recorded product hashes."""
import pathlib,json,hashlib,tarfile,subprocess
R=pathlib.Path('/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8388608),b''):h.update(b)
 return h.hexdigest()
phases=['baseline','off','off-v2','capture','replays','inverse-repair-v2'];raw=[];producers=[];replays=[]
for phase in phases:
 for p in sorted((R/phase).glob('*/RUN.json')):
  d=json.loads(p.read_text());row={'receipt':str(p.relative_to(R)),'receipt_sha256':sha(p),'rc':d['rc'],'args':d.get('args',d.get('argv')),'env':d['env'],'binary_sha256':d['binary_sha256'],'phase':phase,'start':d['start'],'end':d['end']}
  row['resource_coverage']='fresh-per-producer' if (p.parent/'ADMISSION.json').exists() else 'phase-level-only'
  row['witnessed_uuids_for_run'] = sorted({line.split(',')[1].strip() for sample in d['device_samples'] for line in (sample if isinstance(sample,str) else sample['smi']).splitlines() if ',' in line})
  if 'hashes' in d:
   row['production_source']='e77a51a220cb0d91f4ac3c7fac211876d0c6833f';row['hook_source']=None if phase=='baseline' else ('0e055c154ac12af73ae87a98132a8400f1b11dbe' if phase=='off' else '7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd');producers.append(row)
   entries=[(p.parent/k,v['sha256']) for k,v in d['hashes'].items()]
  else:
   row['old_inverse_status']='INVALID complete-batch provenance' if phase=='replays' and ('-inverse-' in p.parent.name) else 'not affected by inverse-v1 zero-fill defect';replays.append(row)
   entries=[(p.parent/'data'/k,v) for k,v in d['output_hashes'].items()]
  for f,expected in entries:
   observed=sha(f);assert expected==observed,str(f)
   raw.append({'path':str(f.relative_to(R)),'bytes':f.stat().st_size,'sha256':observed})
for name,data in [('verified-file-index.json',raw),('producer-ledger.json',producers),('replay-ledger.json',replays)]:
 p=R/name;assert not p.exists();p.write_text(json.dumps(data,indent=2)+'\n')
(R/'final-gpu.txt').write_text(subprocess.check_output(['nvidia-smi','-q'],text=True))
(R/'final-locks.txt').write_text(subprocess.check_output(['lslocks'],text=True))
(R/'final-space.txt').write_text(subprocess.check_output(['du','-sb',str(R)],text=True))
files=[p for phase in phases for p in (R/phase).rglob('*') if p.is_file() and not p.is_symlink() and p.suffix in ['.json','.txt','.star','.log','.exit']]
files += [p for p in R.iterdir() if p.is_file() and p.suffix in ['.json','.txt','.log','.exit','.py','.cu']]
a=R/'receipts-20261026.tar.gz';assert not a.exists()
with tarfile.open(a,'w:gz') as t:
 for p in sorted(set(files)):t.add(p,arcname=str(p.relative_to(R)),recursive=False)
binding={'remote_archive':str(a),'sha256':sha(a),'bytes':a.stat().st_size,'files':len(set(files)),'verified_product_files':len(raw),'source':'7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd','helper_repair_source':'031f333a2863218c74951117989c84423ad9c92e','native_movie_producers':len(producers),'original_replay_processes':sum(v['phase']=='replays' for v in replays),'inverse_v2_processes':sum(v['phase']=='inverse-repair-v2' for v in replays)}
(R/'archive-binding.json').write_text(json.dumps(binding,indent=2)+'\n');print(json.dumps(binding,indent=2))
