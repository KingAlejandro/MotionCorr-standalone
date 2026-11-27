import pathlib,json,math,importlib.util,contextlib,sys
root=pathlib.Path('/tmp/mc-peakfit-records');out=pathlib.Path('/tmp/mc-classification');out.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('s13','/tmp/mc-peakfit-tools/analyze.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=json.load(open('/tmp/mc-rows-all.json'));summary=[];requests={}
def cpu(mv,g):
 p=root/'runs'/('%s-p%d-cpu'%(mv,g))
 if (p/'ccf.txt').exists():return p
 if not mv.endswith('-00'):return None
 p=root/'reused-cpu'/('%s-p%d-diag-cpu-on'%(mv.rsplit('-',1)[0],g))
 return p if (p/'ccf.txt').exists() else None
for r in rows:
 for arm in ['A1','A2']:
  if r['arms'].get(arm,{}).get('relative_rmse',0)<.1:continue
  mv,g=r['movie'],r['grid'];name='%s-p%d-%s'%(mv,g,arm);c=cpu(mv,g);d=root/'runs'/name
  if c is None or not (d/'ccf.txt').exists():summary.append({'case':name,'status':'missing capture'});continue
  assert next((c/'Movies').glob('*.star')).name == next((d/'Movies').glob('*.star')).name, (c,d,'input-movie mismatch')
  p=out/(name+'.json')
  with open(out/(name+'.log'),'w') as f,contextlib.redirect_stdout(f):m.cmd_traj(c,d,p)
  a=json.load(open(p));glob=a['patches'].get('global',{})
  global_failure=not glob.get('converged_cpu',True) and not glob.get('converged_cuda',True)
  relevant={k:v for k,v in a['patches'].items() if k!='global' and (v['converged_cpu'] or v['converged_cuda']) and v['divergent']}
  entry={'case':name,'status':'measured','both_global_failure':global_failure,'global':glob,'relevant_patches':{},'emulation_mismatches':a['cuda_emulation_mismatches']}
  for k,v in relevant.items():
   q={x:v[x] for x in ['first_separation_kind','first_sel_diff','final_traj_diff_max_px','acceptance_flip','converged_cpu','converged_cuda','iters_cpu','iters_cuda']}
   q['first_event']=v.get('first_event');q['cuda_retry']=v.get('cuda_retry');entry['relevant_patches'][k]=q
   if q['first_event'] and any(not f['same_peak'] for f in q['first_event']['frames'].values()) and not global_failure:
    requests.setdefault((mv,g),{'movie':mv,'grid':g,'patches':set(),'arms':set()});requests[(mv,g)]['patches'].add(k);requests[(mv,g)]['arms'].add(arm)
  summary.append(entry)
json.dump(summary,open(out/'summary.json','w'),indent=1)
for v in requests.values():v['patches']=sorted(v['patches']);v['arms']=sorted(v['arms'])
json.dump(list(requests.values()),open(out/'map-requests.json','w'),indent=1)
for x in summary:print(x['case'],x['status'],'bothGlobalFail',x.get('both_global_failure'),{k:v['first_separation_kind'] for k,v in x.get('relevant_patches',{}).items()})
print('map probe configs',len(requests))
