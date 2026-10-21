#!/usr/bin/env python3
"""All-config analysis, defined against R, with the retained #261 conventions.
Run on 4GPUs after verified cpu64 products have been offloaded.
"""
import collections,hashlib,json,math,pathlib,re,subprocess,sys
import numpy as np
S=None; OUT=None
METRIC=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit/tools/mc-metrics')
ARMS=['Rprime','C_none','C_global','C_local','C_both','G_none','G_global','G_local','G_both']
def primary(d):
 a=[p for p in (d/'Movies').glob('*.mrc') if not p.name.endswith(('_noDW.mrc','_PS.mrc','_ODD.mrc','_EVN.mrc'))];assert len(a)==1,(d,a);return a[0]
def star(d):return next((d/'Movies').glob('*.star'))
def loop(t,name):
 m=re.search(r'data_'+name+r'\s*\n(.*?)(?=\n# version|\ndata_|\Z)',t,re.S)
 if not m:return []
 return [[float(x) for x in l.split()] for l in m[1].splitlines() if l.strip() and not l.strip().startswith(('_','loop_','#'))]
def runpath(m,g,a):return (S/'runs' if a.startswith('G') else S/'cpu64/runs')/f'{m}-p{g}-{a}'
def info(d):
 rec=json.load(open(d/'run.json'));assert rec['rc']==0
 t=star(d).read_text();loc=loop(t,'local_shift');sets=sorted(set((int(v[1]),int(v[2])) for v in loc))
 model=(d/'model.txt').read_text().splitlines();geom=model[0].split();nx,ny,n=map(int,geom[1:4]);scale=float(geom[4]);first=int(geom[5]);active=int(model[1].split()[1])
 cf=np.zeros((18,2))
 if active:cf=np.array([[float(v) for v in l.split()[1:]] for l in model[2:]])
 assert cf.shape==(18,2)
 gl=np.array([[float(v) for v in l.split()[1:]] for l in (d/'global.txt').read_text().splitlines()])*scale
 cs=loop(t,'local_motion_model');cstar=np.array([v[1] for v in cs]).reshape(2,18).T if cs else np.zeros((18,2))
 return {'record':rec,'set':sets,'coeff':cf*scale,'starcoeff':cstar*scale,'global':gl,'geometry':(nx,ny,n,scale,first),'active':bool(active)}
def field(c,n):
 g=np.linspace(-.5,.5,33);x,y=np.meshgrid(g,g);spatial=np.stack([np.ones_like(x),x,x*x,y,y*y,x*y],axis=-1)
 z=np.arange(n,dtype=float);powers=np.stack([z,z*z,z*z*z],axis=1)
 return np.einsum('ijk,ft,ktv->fijv',spatial,powers,c.reshape(6,3,2),optimize=True)
def norms(v):
 a=np.sqrt(np.sum(v*v,axis=-1));return {'max':float(a.max()),'rms':float(np.sqrt(np.mean(a*a)))}
def ccf(d):
 out={}
 for line in (d/'ccf.txt').read_text().splitlines():
  t=line.split();tag=t[0];p=(int(t[1]),int(t[2]));k=int(t[4]);f=int(t[6]);q={'sel':list(map(int,t[8:10])),'cpu':list(map(int,t[13:15])),'lane':list(map(int,t[16:18])),'ties':int(t[19]),'sub':list(map(float,t[27:32])),'cur':list(map(float,t[33:35]))}
  out.setdefault(p,{}).setdefault(tag,{}).setdefault(k,{})[f]=q
 return out
def chosen(v):
 # Retry is the last attempt entering admission. No CPU full-spectrum retry.
 for tag in ['cuda-full','cuda-batched','cuda-single','cuda-global','cpu','cpu-global']:
  if tag in v:return tag,v[tag]
 raise ValueError(v.keys())
def traj(iters,cuda):
 n=len(iters[1]);tot=np.zeros((n,2));rms=[]
 for k in sorted(iters):
  cur=np.array([iters[k][f]['cur'] for f in sorted(iters[k])]);cur=cur.astype(np.float32) if cuda else cur;inc=(cur-cur[0]).astype(float);tot+=inc;rms.append(float(np.sqrt(np.sum(inc*inc)/n)))
 return tot,rms

def divergence(ca,cb,kept_a,kept_b,failed):
 # Per-call first >0.5-px candidate event and first integer-selection change.
 witnesses=[];first_integer=[];retries=0;global_rms={}
 for p in sorted(set(ca)&set(cb)):
  ta,ia=chosen(ca[p]);tb,ib=chosen(cb[p]);retries+=int('cuda-full' in cb[p] and len(cb[p])>1)
  T_a,ra=traj(ia,ta.startswith('cuda'));T_b,rb=traj(ib,tb.startswith('cuda'))
  if p==(0,0):global_rms={'reference':ra,'arm':rb}
  relevant=(ra[-1]<.5)!=(rb[-1]<.5) or norms(T_a-T_b)['max']>1
  first=None;integer=None
  for k in sorted(set(ia)&set(ib)):
   for f in sorted(set(ia[k])&set(ib[k])):
    a,b=ia[k][f],ib[k][f];dist=math.dist(a['cur'],b['cur'])
    if integer is None and a['sel']!=b['sel']:integer={'patch':p,'iteration':k,'frame':f,'distance_px':dist}
    if first is None and dist>.5:
     same=a['sel']==b['sel'];tie=b['ties']>1 and b['cpu']!=b['lane']
     kind='same integer, different samples/fit' if same else ('different integer; CUDA same-map tie order also differs' if tie and tb.startswith('cuda') else 'different integer ordering')
     first={'patch':p,'iteration':k,'frame':f,'candidate_gap_px':dist,'kind':kind,'s1_relevant':relevant,'reference':a,'arm':b,'arm_tag':tb}
  if first:witnesses.append(first)
  if integer:first_integer.append(integer)
 # Global precedes all local calls. Among local witnesses use iteration, patch,
 # frame order; no claim this recovers batch wall-clock or earliest tiny error.
 key=lambda q:(q['patch']!=(0,0),q['iteration'],q['patch'],q['frame'])
 relevant=[w for w in witnesses if w['s1_relevant'] or w['patch']==(0,0)]
 picked=min(relevant or witnesses,key=key) if witnesses else None
 return {'classification':'known e10216-01 global nonconvergence' if failed else picked['kind'] if picked else 'no >0.5-px candidate event','first_event':picked,'first_integer_change':min(first_integer,key=key) if first_integer else None,'global_increment_rmsd':global_rms,'retry_patch_count':retries,'event_scope':'first >0.5px candidate separation in selected S1-relevant call; smaller arithmetic/input differences may precede it'}

def accepted(recs):
 out=[]
 for p,groups in recs.items():
  if p==(0,0):continue
  tag,it=chosen(groups);_,rms=traj(it,tag.startswith('cuda'))
  if rms[-1]<.5:out.append(p)
 return sorted(out)

def metric(a,b):return json.loads(subprocess.check_output([str(METRIC),str(primary(a)),str(primary(b))],text=True))
def analyze(root):
 global S,OUT
 S=pathlib.Path(root);OUT=S/'analysis';OUT.mkdir(exist_ok=True)
 rows=[];ledger=[]
 for fam in ['e10216','e12963','e10474f3']:
  for i in range(10):
   m=f'{fam}-{i:02d}'
   if not (S/'cpu64'/(m+'-verified.json')).exists():continue
   for g in [5,3]:
    rd=runpath(m,g,'R');R=info(rd);rc=ccf(rd);row={'movie':m,'grid':g,'reference':str(rd),'reference_active_local':R['active'],'arms':{}}
    ledger.append(R['record'])
    for arm in ARMS:
     d=runpath(m,g,arm)
     if not (d/'run.json').exists():continue
     a=info(d);o=OUT/f'{m}-p{g}-{arm}.json'
     if not o.exists():
      assert a['geometry']==R['geometry'],(a['geometry'],R['geometry'])
      glob=norms(a['global']-R['global']);n=R['geometry'][2];fld=norms(field(a['coeff']-R['coeff'],n));starfld=norms(field(a['starcoeff']-R['starcoeff'],n));recs=ccf(d)
      q={'product':metric(rd,d),'global_px':glob,'local_field_native_px':fld,'local_field_star_px':starfld,'accepted_set_equal':accepted(rc)==accepted(recs),'accepted_reference':accepted(rc),'accepted_arm':accepted(recs),'star_observation_set_equal':a['set']==R['set'],'kept_reference':R['set'],'kept_arm':a['set'],'active_local':a['active'],'reference_serialization_field_error_px':norms(field(R['starcoeff']-R['coeff'],n)),'arm_serialization_field_error_px':norms(field(a['starcoeff']-a['coeff'],n)), 'divergence':divergence(rc,recs,R['set'],a['set'],m=='e10216-01'),'run':str(d)}
      json.dump(q,open(o,'w'),indent=1)
     row['arms'][arm]=json.load(open(o));ledger.append(a['record'])
    if len(row['arms'])==len(ARMS):rows.append(row)
 json.dump(rows,open(OUT/'rows.json','w'),indent=1);json.dump(ledger,open(OUT/'run-ledger.json','w'),indent=1)
 # Exact paired binomial test, including the zero-discordance convention p=1.
 def mcn(a,b):
  cells=[sum(x and y for x,y in zip(a,b)),sum(x and not y for x,y in zip(a,b)),sum(not x and y for x,y in zip(a,b)),sum(not x and not y for x,y in zip(a,b))];n=cells[1]+cells[2];k=min(cells[1:3]);p=min(1.,2*sum(math.comb(n,j) for j in range(k+1))/2**n) if n else 1.
  return {'cells_both_Aonly_Bonly_neither':cells,'exact_p_two_sided':p}
 def counts(arm,subset):
  rr=[r['arms'][arm] for r in subset];positive=[r for r in subset if r['arms'][arm]['product']['relative_rmse']>=.1]
  return {'configs':len(rr),'positive_configs':len(positive),'positive_movies':len(set(r['movie'] for r in positive)),'accepted_set_equal':sum(q['accepted_set_equal'] for q in rr),'active_local':sum(q['active_local'] for q in rr),**{kind:{'median_max':float(np.median([q[kind]['max'] for q in rr])),'worst_max':max(q[kind]['max'] for q in rr),'median_rms':float(np.median([q[kind]['rms'] for q in rr])),'worst_rms':max(q[kind]['rms'] for q in rr)} for kind in ['global_px','local_field_native_px']},'product_relRMSE':{'median':float(np.median([q['product']['relative_rmse'] for q in rr])),'worst':max(q['product']['relative_rmse'] for q in rr)}}
 if rows:
  summary={'complete_configs':len(rows),'arms':{},'transitions':{},'backend_continuity':[]}
  for arm in ARMS:summary['arms'][arm]={'all':counts(arm,rows),'other58':counts(arm,[r for r in rows if r['movie']!='e10216-01']),'e10216-01':counts(arm,[r for r in rows if r['movie']=='e10216-01'])} if any(r['movie']=='e10216-01' for r in rows) else {'all':counts(arm,rows)}
  for backend in ['C','G']:
   for dc in ['global','local','both']:
    a,b=backend+'_none',backend+'_'+dc;fa=[r['arms'][a]['product']['relative_rmse']>=.1 for r in rows];fb=[r['arms'][b]['product']['relative_rmse']>=.1 for r in rows];movies=sorted(set(r['movie'] for r in rows));ma=[any(f for r,f in zip(rows,fa) if r['movie']==m) for m in movies];mb=[any(f for r,f in zip(rows,fb) if r['movie']==m) for m in movies]
    summary['transitions'][a+'->'+b]={'configs':mcn(fa,fb),'movies_any_grid':mcn(ma,mb)}
  # Matching-DC CPU-vs-CUDA screen, retaining its own CPU std denominator.
  for r in rows:
   q={'movie':r['movie'],'grid':r['grid'],'arms':{}}
   for dc in ['none','global','local','both']:
    o=OUT/f"{r['movie']}-p{r['grid']}-backend-{dc}.json"
    if not o.exists():json.dump(metric(runpath(r['movie'],r['grid'],'C_'+dc),runpath(r['movie'],r['grid'],'G_'+dc)),open(o,'w'),indent=1)
    q['arms'][dc]=json.load(open(o))
   summary['backend_continuity'].append(q)
  summary['backend_counts']={dc:sum(r['arms'][dc]['relative_rmse']>=.1 for r in summary['backend_continuity']) for dc in ['none','global','local','both']}
  json.dump(summary,open(OUT/'summary.json','w'),indent=1)
  print('COMPLETE',len(rows));print('VS R',{a:summary['arms'][a]['all']['positive_configs'] for a in ARMS});print('BACKEND',summary['backend_counts'])
if __name__=='__main__':analyze(sys.argv[1])
