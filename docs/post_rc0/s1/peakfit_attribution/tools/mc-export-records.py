import pathlib,tarfile,json,shutil
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');extra=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1ccf/runs')
with tarfile.open(s/'records-progress.tar.gz','w:gz',compresslevel=4) as t:
 for d in sorted((s/'runs').iterdir()):
  if not (d/'run.json').exists():continue
  r=json.load(open(d/'run.json'))
  if r['rc']!=0:continue
  for p in sorted(d.rglob('*')):
   if p.is_file() and (p.name in ['run.json','ccf.txt','global.txt','null-dose.txt','stdout.log','time-v.log','witness.txt'] or p.suffix in ['.star','.log']):t.add(p,arcname=str(p.relative_to(s)))
 for fam,g in [('e10216',5),('e10216',3),('e12963',5),('e10474f3',5)]:
  d=extra/('%s-p%d-diag-cpu-on'%(fam,g))
  for p in sorted(d.rglob('*')):
   if p.is_file() and (p.name in ['run.json','ccf.txt','stdout.log'] or p.suffix in ['.star','.log']):t.add(p,arcname='reused-cpu/'+str(p.relative_to(extra)))
print((s/'records-progress.tar.gz').stat().st_size)
