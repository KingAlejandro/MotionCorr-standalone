import json,sys,pathlib,subprocess,math,struct
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');old=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1ccf/runs')
def primary(d):return next(p for p in (d/'Movies').glob('*.mrc') if not p.name.endswith(('_noDW.mrc','_PS.mrc','_ODD.mrc','_EVN.mrc')))
def metric(a,b):return json.loads(subprocess.check_output([str(s/'tools/mc-metrics'),str(a),str(b)],text=True))
out=[]
for fam in ['e10216','e12963','e10474f3']:
 for i in range(10):
  mv='%s-%02d'%(fam,i);ref=old/('e-%s-G-cpu'%mv) if mv in ['e10216-00','e12963-00'] else s/'runs'/(mv+'-G-cpu')
  if not (ref/'run.json').exists():continue
  row={'movie':mv,'reference_run':str(ref),'arms':{}}
  for arm in ['A0','A1']:
   d=s/'runs'/(mv+'-G-'+arm)
   if not (d/'run.json').exists():continue
   o=d/'global-products.json'
   if not o.exists():
    refp=primary(ref);p=primary(d)
    r={'DW':metric(refp,p),'nonDW':metric(refp.with_name(refp.stem+'_noDW.mrc'),p.with_name(p.stem+'_noDW.mrc'))}
    json.dump(r,open(o,'w'),indent=1)
   row['arms'][arm]=json.load(open(o))
  if row['arms']:out.append(row)
json.dump(out,open(s/'global-products-all.json','w'),indent=1)
print('GLOBAL_PRODUCTS',len(out),flush=True)
# Paired CPU conditioning controls on the three retained primary movies, both grids.
rows=[]
for mv in ['e10216-00','e12963-00','e10474f3-00']:
 for g in [5,3]:
  a=s/'runs'/('%s-p%d-cpu'%(mv,g));b=s/'runs'/('%s-p%d-cpuDC'%(mv,g));cuda=s/'runs'/('%s-p%d-A2'%(mv,g))
  if not (b/'run.json').exists():continue
  from importlib.machinery import SourceFileLoader
  # Use the established STAR trajectory convention without importing NumPy.
  import re
  def gl(d):
   p=next((d/'Movies').glob('*.star'));t=p.read_text();z=re.search(r'data_global_shift\s*\n(.*?)(?=\n# version|\ndata_|\Z)',t,re.S).group(1)
   return [tuple(map(float,l.split()[1:3])) for l in z.splitlines() if len(l.split())==3 and not l.strip().startswith('_')]
  delta=[math.hypot(x[0]-y[0],x[1]-y[1]) for x,y in zip(gl(a),gl(b))]
  rows.append({'movie':mv,'grid':g,'CPU_DC_vs_CPU':metric(primary(a),primary(b)),'A2_vs_CPU_DC':metric(primary(b),primary(cuda)),'global_delta_max_px':max(delta),'global_delta_rms_px':math.sqrt(sum(x*x for x in delta)/len(delta))})
json.dump(rows,open(s/'cpu-dc-controls.json','w'),indent=1);print('CPU_DC_CONTROLS',len(rows))
