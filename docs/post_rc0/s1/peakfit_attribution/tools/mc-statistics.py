import json,math,statistics,pathlib
from math import comb
R=json.load(open('/tmp/mc-rows-all.json'));F=json.load(open('/tmp/mc-fair-all.json'));assert len(R)==len(F)==60
O=pathlib.Path('/tmp/mc-final-tables');O.mkdir(exist_ok=True)
def pval(b,c):return 1 if b+c==0 else min(1,2*sum(comb(b+c,i) for i in range(min(b,c)+1))/2**(b+c))
def table(rows,a,b):
 z={'+/+':0,'+/−':0,'−/+':0,'−/−':0}
 for r in rows:
  x,y=(r['arms'][k]['relative_rmse']>=.1 for k in [a,b]);z['+/+' if x and y else '+/−' if x else '−/+' if y else '−/−']+=1
 return {'from':a,'to':b,'n':len(rows),'from_positive':sum(r['arms'][a]['relative_rmse']>=.1 for r in rows),'to_positive':sum(r['arms'][b]['relative_rmse']>=.1 for r in rows),'cells':z,'mcnemar_exact_two_sided_p':pval(z['+/−'],z['−/+'])}
def groups(rows):
 g={}
 for r in rows:
  fam=r['movie'].rsplit('-',1)[0]
  for key in [fam+'-p'+str(r['grid']),fam+'-both','pooled-p'+str(r['grid']),'pooled-both']:g.setdefault(key,[]).append(r)
 return g
pairs=[('A0','A1'),('N1','A1'),('N2','A1'),('A1','A2'),('A0','N1'),('A0','N2')]
S={k:[table(v,a,b) for a,b in pairs] for k,v in groups(R).items()}
T={k:[table(v,a,b) for a,b in [('A0','A1'),('A1','A2'),('A0','A2')]] for k,v in groups(F).items()}
json.dump(S,open(O/'primary-transitions.json','w'),indent=1);json.dump(T,open(O/'conditioned-transitions.json','w'),indent=1)
D={}
for name,rows in [('original_CPU',R),('conditioned_CPU',F)]:
 D[name]={}
 for arm in ['A0','A1','A2']:
  for bad in [False,True]:
   q=[r['arms'][arm] for r in rows if (r['movie']=='e10216-01')==bad]
   D[name][arm+('-known-global-failure' if bad else '-other-58-configs')]={m:{'median':statistics.median(r[m] for r in q),'max':max(r[m] for r in q),'min':min(r[m] for r in q)} for m in ['global_max_px','global_rms_px','relative_rmse']}
json.dump(D,open(O/'global-summaries.json','w'),indent=1)
for name,t in [('PRIMARY',S),('CONDITIONED',T)]:
 print(name)
 for row in t['pooled-both']:print(row)
 print('12963',t['e12963-both'])
print('GLOBAL',D)
