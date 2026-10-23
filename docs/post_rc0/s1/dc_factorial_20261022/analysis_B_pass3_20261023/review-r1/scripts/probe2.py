import json,glob,statistics as st,collections,math
res=json.load(open('out/indep.json'))
ev=[r for r in res if r['n']==10]; print('complete comparisons',len(ev),'partial',len([r for r in res if 0<r['n']<10]),'unrun',len([r for r in res if r['n']==0]))
sig=[r for r in ev if r['p']<.05]; print('p<.05',len(sig))
# multiplicity
ps=sorted(r['p'] for r in ev); m=len(ps)
bh=[ (p*m/(i+1)) for i,p in enumerate(ps)]
q=[min(bh[i:]) for i in range(m)]
print('min p',ps[0],'bonf alpha',0.05/m,'bonferroni survivors',sum(p<0.05/m for p in ps))
print('BH q<0.05 count',sum(x<0.05 for x in q),'BH q<0.10',sum(x<0.10 for x in q))
# restrict to rms family
fam=[r for r in ev if r['met']=='rms']; ps=sorted(r['p'] for r in fam); m=len(ps)
bh=[p*m/(i+1) for i,p in enumerate(ps)]; q=[min(bh[i:]) for i in range(m)]
print('rms family m',m,'p<.05',sum(p<.05 for p in ps),'BH q<.05',sum(x<.05 for x in q),'bonf',sum(p<.05/m for p in ps))
# expected false positives
print('expected false pos at .05 over',len(ev),'=',0.05*len(ev),'(exact test is conservative; P(p<.05|H0,n=10,no ties)=',2*sum(math.comb(10,i) for i in range(2))/2**10,')')
# category vs median sign / ties
for r in sig:
    if not r['favmed'] and r['w']>r['l'] or r['t']>0: print('sign/median/ties oddity',r)
print('ties total in complete', sum(r['t'] for r in ev), 'comparisons with any tie', sum(r['t']>0 for r in ev))
print('regressions (losses) total over all', sum(r['l'] for r in res), 'by metric', collections.Counter({m:sum(r['l'] for r in res if r['met']==m) for m in ['rms','max','transfer','transfer_top']}))
# tiny-effect: improves/harms with median |delta| thresholds
for r in sorted(sig,key=lambda r:abs(r['med'])):
    if abs(r['med'])<1e-2: print('SMALL',r['c'],r['b'],r['a'],r['met'],f"{r['w']}/{r['l']}/{r['t']}",f"med={r['med']:.3g}",f"maxabs={r['mad']:.3g}",'p=%.4g'%r['p'])
print('sig by condition',collections.Counter(r['c'] for r in sig))
# all-neutral exact: pedestal0 magnitudes
for r in ev:
    if r['c']=='pedestal0' and r['met'] in('rms','transfer') : print('ped0',r['b'],r['a'],r['met'],f"{r['w']}/{r['l']}/{r['t']}",f"med={r['med']:.2e}",f"max|d|={r['mad']:.2e}",'p=%.3f'%r['p'])
