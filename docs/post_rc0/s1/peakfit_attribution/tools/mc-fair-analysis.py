import json,pathlib,subprocess,math,re
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');rows=json.load(open(s/'rows-all.json'));out=[]
def primary(d):return next(p for p in (d/'Movies').glob('*.mrc') if not p.name.endswith(('_noDW.mrc','_PS.mrc','_ODD.mrc','_EVN.mrc')))
def met(a,b):return json.loads(subprocess.check_output([str(s/'tools/mc-metrics'),str(primary(a)),str(primary(b))],text=True))
def gl(p):
 vals=[tuple(map(float,l.split()[1:3])) for l in p.read_text().splitlines() if len(l.split())==3]
 return vals
for r in rows:
 mv,g=r['movie'],r['grid'];dc=s/'runs'/('%s-p%d-cpuDC'%(mv,g))
 if not (dc/'run.json').exists():continue
 assert json.load(open(dc/'run.json'))['rc']==0
 q={'movie':mv,'grid':g,'reference_run':str(dc),'arms':{}}
 for arm in ['A0','A1','A2']:
  d=s/'runs'/('%s-p%d-%s'%(mv,g,arm));o=d/'cpuDC-reference-metrics.json'
  if not o.exists():json.dump(met(dc,d),open(o,'w'),indent=1)
  a,b=gl(dc/'global.txt'),gl(d/'global.txt');assert len(a)==len(b)
  v=[math.hypot(x[0]-y[0],x[1]-y[1]) for x,y in zip(a,b)]
  q['arms'][arm]={**json.load(open(o)),'global_max_px':max(v),'global_rms_px':math.sqrt(sum(x*x for x in v)/len(v))}
 out.append(q)
json.dump(out,open(s/'fair-cpu-dc-all.json','w'),indent=1)
print('FAIR ROWS',len(out))
print('S1',[(a,sum(r['arms'][a]['relative_rmse']>=.1 for r in out)) for a in ['A0','A1','A2']])
