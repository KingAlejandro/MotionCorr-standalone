import json,glob,re,math,subprocess,pathlib,sys
S=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');SW=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1/sweep/runs');OLD=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1ccf/runs')
def primary(d):
 p=[p for p in (d/'Movies').glob('*.mrc') if not p.name.endswith(('_noDW.mrc','_PS.mrc','_ODD.mrc','_EVN.mrc'))];assert len(p)==1,(d,p);return p[0]
def star(d):
 p=list((d/'Movies').glob('*.star'));assert len(p)==1,d;return p[0]
def globalstar(d):
 t=star(d).read_text();b=re.search(r'data_global_shift\s*\n(.*?)(?=\n# version|\ndata_|\Z)',t,re.S).group(1)
 return [tuple(map(float,l.split()[1:3])) for l in b.splitlines() if len(l.split())==3 and not l.strip().startswith('_')]
def metric(a,b):
 return json.loads(subprocess.check_output([str(S/'tools/mc-metrics'),str(primary(a)),str(primary(b))],text=True))
def identity(a,b):
 p=subprocess.run([sys.executable,str(S/'tools/identity.py'),str(a),str(b)],text=True,capture_output=True)
 assert p.returncode in (0,1),p.stderr
 return json.loads(p.stdout.splitlines()[-1])
rows=[]
for fam,n in [('e10216',7),('e12963',10),('e10474f3',4)]:
 for i in range(n):
  mv='%s-%02d'%(fam,i)
  for g in [5,3]:
   ref=SW/('%s-p%d-F-cpu'%(mv,g));r={'movie':mv,'grid':g,'venue':'4GPUs','arms':{}}
   a=globalstar(ref)
   for arm in ['A0','A1','A2','N1','N2']:
    d=S/'runs'/('%s-p%d-%s'%(mv,g,arm))
    if not (d/'run.json').exists(): continue
    run=json.load(open(d/'run.json')); assert run['rc']==0,run
    out=d/'metrics.json'
    if not out.exists():json.dump(metric(ref,d),open(out,'w'),indent=1)
    b=globalstar(d);assert len(a)==len(b)
    delta=[math.hypot(x[0]-y[0],x[1]-y[1]) for x,y in zip(a,b)]
    r['arms'][arm]={**json.load(open(out)),'global_max_px':max(delta),'global_rms_px':math.sqrt(sum(x*x for x in delta)/len(delta)),'rc':run['rc'],'witness':run['gpu_witness_uuids']}
    if arm=='A0':
     out=d/'identity-parent.json'
     if not out.exists():json.dump(identity(OLD/('n-%s-p%d-pr254'%(mv,g)),d),open(out,'w'),indent=1)
     r['A0_identity_parent']=json.load(open(out))['identical']
   if r['arms']:rows.append(r)
json.dump(rows,open(S/'rows-4gpus.json','w'),indent=1)
for r in rows:
 print(r['movie'],r['grid'],' '.join('%s %.6g Gmax=%.6g'%(a,v['relative_rmse'],v['global_max_px']) for a,v in r['arms'].items()),r.get('A0_identity_parent'))
