import json,glob,math,collections,statistics as st,sys
from scipy.stats import binomtest
EV=sys.argv[1]; OUT=sys.argv[2]
R={}
for p in glob.glob(EV+'/B/*.json'):
    m=json.load(open(p)); R[m['id']]=m
ARMS=['none','global','local','both']
conds=sorted({k.split('-')[1] for k in R})
def val(m,met):
    if m['status']!='EVALUATED': return None
    t=m['truth']; i=m['image']['interior']
    return {'rms':t['field']['px']['rms'],'max':t['field']['px']['max'],'transfer':i['transfer_inband'],'transfer_top':i['bands'][-1]['transfer']}[met]
res=[]
for c in conds:
  for b in ['cpu','cuda']:
    for a in ARMS[1:]:
      for met,sgn in [('rms',-1),('max',-1),('transfer',1),('transfer_top',1)]:
        d=[]
        for s in range(10):
          x=R.get(f'B-{c}-s{s:02d}-{b}-none'); y=R.get(f'B-{c}-s{s:02d}-{b}-{a}')
          if x is None or y is None: continue
          vx,vy=val(x,met),val(y,met)
          if vx is None or vy is None: continue
          d.append(vy-vx)
        w=sum(1 for e in d if e*sgn>0); l=sum(1 for e in d if e*sgn<0); t=len(d)-w-l
        p=binomtest(min(w,l),w+l,0.5).pvalue if w+l else 1.0
        res.append(dict(c=c,b=b,a=a,met=met,n=len(d),w=w,l=l,t=t,p=p,med=st.median(d) if d else None,
                        favmed=(st.median(d)*sgn>0) if d else None, mad=max(abs(e) for e in d) if d else None))
json.dump(res,open(OUT,'w'),indent=1)
S=json.load(open(sys.argv[3]))['pairs']
bad=0
SI={(s['condition'],s['backend'],s['arm'],s['metric']):s for s in S}
assert len(SI)==len(res)==240
for r in res:
    s=SI[(r['c'],r['b'],r['a'],r['met'])]
    if (r['n'],r['w'],r['l'],r['t'])!=(s['pairs'],s['wins'],s['losses'],s['ties']) or abs(r['p']-s['sign_p'])>1e-12 or (r['med']!=s['median_delta']): bad+=1; print('MISMATCH',r,s)
print('compared',len(res),'mismatch',bad)
