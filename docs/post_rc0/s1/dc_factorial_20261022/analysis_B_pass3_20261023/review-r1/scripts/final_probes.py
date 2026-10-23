import json,glob,re,collections,statistics as st,math,hashlib,subprocess,sys
SNAP='snap'; WT='/Users/alex.konstantinov/.t3/worktrees/MotionCorr/work-272-evaluator-contract-20261022'
OLD='/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c79c479/docs/post_rc0/s1/dc_factorial_20261022/results/tierB.json'
R={}
for p in glob.glob(SNAP+'/eval/B/*.json'):
    m=json.load(open(p)); R[m['id']]=m
S=json.load(open(SNAP+'/SNAPSHOT.json')); E=json.load(open(SNAP+'/EVALUATIONS.json'))
print('## identity')
print('records',len(R),'status',dict(collections.Counter(m['status'] for m in R.values())),'cpu',sum(m['backend']=='cpu' for m in R.values()),'cuda',sum(m['backend']=='cuda' for m in R.values()))
print('eval sha mismatches',sum(hashlib.sha256(open(f'{SNAP}/eval/B/{k}.json','rb').read()).hexdigest()!=h for k,h in E['sha256'].items()))
print('retained==current',all(E['sha256'][k]==v for k,v in S['retained_evaluations'].items()),len(S['retained_evaluations']),'reused/new',E['reused'],E['new'])
print('plain in snapshot',[k for k in S['records'] if k.endswith('plain')],'plain excluded',[k for k in S['excluded'] if k.endswith('plain')])
print('binaries',dict(collections.Counter((r['backend'],r['arm']=='plain',r['binary_sha256'][:8],r['native_exit']) for r in S['records'].values())))
ok=bad=0
for p,h in S['source_python_sha256'].items():
    r=subprocess.run(['git','-C',WT,'show',f'3eee0a4b4e367f9b57f950c440c89679a5ec9c93:{p}'],capture_output=True)
    if r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==h: ok+=1
    else: bad+=1
print('imported-source hashes vs git 3eee0a4b: ok',ok,'bad',bad)
print('## witness audit (z==e on selected stage, 0 on unselected)')
pat=re.compile(r'(\w+)\.(\w+)=(\d+)/(\d+)'); an=[]
for rid,m in R.items():
    if m['arm']=='plain': continue
    mm=re.match(r'MC_EXPERIMENT_CCF_DC arm=(\w+) (.*)',m['dc_witness'] or '')
    if not mm or mm.group(1)!=m['arm']: an.append(rid); continue
    ents=[(a,b,int(z),int(e)) for a,b,z,e in pat.findall(mm.group(2))]
    for site,stage,z,e in ents:
        sel=m['arm']=='both' or m['arm']==stage
        if e>0 and ((sel and z!=e) or (not sel and z!=0)): an.append((rid,site,stage,z,e))
    if not any(e>0 for *_,e in ents): an.append((rid,'noelig'))
print('anomalies',len(an),an[:5])
print('## validity/failure fields (734 evaluated)')
c=collections.Counter()
for m in R.values():
    if m['status']!='EVALUATED': continue
    t=m['truth']; c[('sampling',t['sampling_status'])]+=1; c[('fieldgate',t['field_distance_status'])]+=1
    c[('local_enabled',t['local_enabled'])]+=1; c[('global_converged',t['convergence']['global_converged'])]+=1
print(sorted(c.items(),key=str))
tr=[m['image']['interior']['transfer_inband'] for m in R.values() if m['status']=='EVALUATED']
tt=[m['image']['interior']['bands'][-1]['transfer'] for m in R.values() if m['status']=='EVALUATED']
print('transfer_inband max',max(tr),'top-band >1 count',sum(x>1 for x in tt),'max',max(tt))
print('## pseudoreplication evidence: none-arm CPU field RMS px seeds 0-3')
for c_ in ['pedestal0','pedestal32','dose1','contrast025','contrast4']:
    print(c_,[round(R[f'B-{c_}-s{s:02d}-cpu-none']['truth']['field']['px']['rms'],5) for s in range(4)],'both',[round(R[f'B-{c_}-s{s:02d}-cpu-both']['truth']['field']['px']['rms'],5) for s in range(4)])
print('## multiplicity (216 complete comparisons)')
res=json.load(open('out/indep.json')); ev=[r for r in res if r['n']==10]; sig=[r for r in ev if r['p']<.05]
ps=sorted(r['p'] for r in ev); m_=len(ps); bh=[p*m_/(i+1) for i,p in enumerate(ps)]; q=[min(bh[i:]) for i in range(m_)]
print('m',m_,'sig',len(sig),'min p',ps[0],'bonf survivors',sum(p<.05/m_ for p in ps),'BH q<.05',sum(x<.05 for x in q),'p==0.001953 count',sum(abs(p-0.001953125)<1e-12 for p in ps))
print('null P(p<.05) at n=10',2*(1+10+0)/1024 if False else 2*(1+10)/1024,'-> expected nominal false positives if 216 independent nulls:',216*2*(1+10)/1024)
print('sig by condition',dict(collections.Counter(r['c'] for r in sig)))
print('sig with |median|<1e-2:',sum(abs(r['med'])<1e-2 for r in sig),' <2e-4:',sum(abs(r['med'])<2e-4 for r in sig))
print('ties in complete comparisons',sum(r['t'] for r in ev))
print('## regression magnitudes (878)')
reg=json.load(open('out/regen/tierB.json'))['regressions']
print({k:sum(abs(r['delta'])<v for r in reg) for k,v in [('<1e-6',1e-6),('<1e-4',1e-4),('<1e-3',1e-3)]},'>=1e-2',sum(abs(r['delta'])>=1e-2 for r in reg),'in partial CPU outmodel',sum(1 for r in reg if r['condition']=='outmodel' and r['backend']=='cpu'))
print('## partial-cell cohort mismatch: CPU outmodel')
have={a:[s for s in range(10) if f'B-outmodel-s{s:02d}-cpu-{a}' in R] for a in ['none','global','local','both']}; print(have)
com=sorted(set.intersection(*map(set,have.values())))
for a in have: print(a,'own-seeds',round(st.median([R[f'B-outmodel-s{s:02d}-cpu-{a}']['truth']['field']['px']['rms'] for s in have[a]]),5),'common',com,round(st.median([R[f'B-outmodel-s{s:02d}-cpu-{a}']['truth']['field']['px']['rms'] for s in com]),5))
print('## stability vs earlier 345-record results/tierB.json')
old=json.load(open(OLD))['pairs']; new=json.load(open('out/regen/tierB.json'))['pairs']
K=lambda p:(p['condition'],p['backend'],p['arm'],p['metric']); N={K(p):p for p in new}
both=[(o,N[K(o)]) for o in old if o['pairs']==10 and N[K(o)]['pairs']==10]
print('complete in both',len(both),'changed',sum((o['wins'],o['losses'],o['category'])!=(n['wins'],n['losses'],n['category']) for o,n in both))
