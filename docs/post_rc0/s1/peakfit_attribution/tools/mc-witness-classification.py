import json,pathlib,math,importlib.util,numpy as np
p=pathlib.Path('/tmp/mc-classification');root=pathlib.Path('/tmp/mc-peakfit-records');S=json.load(open(p/'summary.json'))
spec=importlib.util.spec_from_file_location('a','/tmp/mc-peakfit-tools/analyze.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[];need={}
def lookup(rec):
 x,y=rec['sel'];v=[float(np.float32(x)) for x in rec['sub']];d={(x,y):v[0],(x+1,y):v[1],(x-1,y):v[2],(x,y+1):v[3],(x,y-1):v[4]}
 if rec['p2']>-1e29:d[tuple(rec['p2pos'])]=float(np.float32(rec['p2']))
 return d
for s in S:
 assert s['status']=='measured',s['case'];a=json.load(open(p/(s['case']+'.json')));mv,pg,arm=s['case'].rsplit('-',2);g=int(pg[1:]);r={'case':s['case'],'both_global_failure':s['both_global_failure'],'s1_relevant_patches':list(s['relevant_patches'])}
 if s['both_global_failure']:r['kind']='both-backend global failure';rows.append(r);continue
 candidates=[]
 for k,v in a['patches'].items():
  if k=='global' or not(v['converged_cpu'] or v['converged_cuda']):continue
  if v.get('first_event'):
   e=v['first_event'];f,q=max(e['frames'].items(),key=lambda kv:math.hypot(*(kv[1]['cpu_cur'][i]-kv[1]['cuda_cur'][i] for i in [0,1])))
   candidates.append((k,v,e['iter'],int(f),q))
 # Prefer the existing #255 S1-relevant patch screen; otherwise report the first
 # accepted-patch witness without silently dropping sub-1px final differences.
 critical=[c for c in candidates if c[0] in s['relevant_patches']]
 if critical:candidates=critical;r['witness_scope']='S1-relevant patch'
 else:r['witness_scope']='accepted patch; no S1-relevant patch under the 1px screen'
 if not candidates:
  r['kind']='subthreshold fitted-candidate/trajectory differences';r['max_accepted_final_trajectory_difference_px']=max((v['final_traj_diff_max_px'] for k,v in a['patches'].items() if k!='global' and (v['converged_cpu'] or v['converged_cuda'])),default=0);rows.append(r);continue
 first=min(c[2] for c in candidates);k,v,it,f,q=max([c for c in candidates if c[2]==first],key=lambda c:math.hypot(*(c[4]['cpu_cur'][i]-c[4]['cuda_cur'][i] for i in [0,1])))
 r.update(patch=k,iteration=it,frame=f,cpu_position=q['cpu_sel'],cuda_position=q['cuda_sel'],candidate_difference_px=math.hypot(*(q['cpu_cur'][i]-q['cuda_cur'][i] for i in [0,1])),cuda_tag=v['cuda_tag'])
 C=m.parse_ccf(pathlib.Path(a['cpu_run'])/'ccf.txt');G=m.parse_ccf(pathlib.Path(a['cuda_run'])/'ccf.txt');iy,ix=map(int,k.split(','));rc=C['cpu'][(iy,ix)][it][f];rg=G[v['cuda_tag']][(iy,ix)][it][f]
 r['cpu_five_samples']=[float(np.float32(x)) for x in rc['sub']];r['cuda_five_samples']=[float(np.float32(x)) for x in rg['sub']]
 if q['same_peak']:
  r['kind']='same integer peak, different fitted candidate';r['same_five_samples']=r['cpu_five_samples']==r['cuda_five_samples']
 else:
  r['kind']='different integer peak';lc,lg=lookup(rc),lookup(rg)
  if tuple(q['cuda_sel']) in lc and tuple(q['cpu_sel']) in lg:
   mc=lc[tuple(q['cpu_sel'])]-lc[tuple(q['cuda_sel'])];mg=lg[tuple(q['cuda_sel'])]-lg[tuple(q['cpu_sel'])]
   r.update(cpu_margin=mc,cuda_margin=mg,cpu_margin_ulps=mc/abs(float(np.spacing(np.float32(rc['sub'][0])))),cuda_margin_ulps=mg/abs(float(np.spacing(np.float32(rg['sub'][0])))),margin_evidence='captured peak/neighbour/separate-maximum samples')
  key=(mv,g);x=need.setdefault(key,{'movie':mv,'grid':g,'patches':set(),'arms':set()});x['patches'].add(k);x['arms'].add(arm)
 rows.append(r)
for v in need.values():v['patches']=sorted(v['patches']);v['arms']=sorted(v['arms'])
json.dump(rows,open(p/'configuration-witnesses.json','w'),indent=1);json.dump(list(need.values()),open(p/'witness-map-requests.json','w'),indent=1)
from collections import Counter
print(Counter(r['kind'] for r in rows));print('map configs',len(need));print(list(need.values()))
