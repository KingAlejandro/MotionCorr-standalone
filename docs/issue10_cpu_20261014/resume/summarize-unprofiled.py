import json, statistics, sys
from pathlib import Path
root=Path('/workspace/scratch/28038873ca11');sys.path.insert(0,str(root/'MotionCorr-standalone/tools/profiling'))
from lib import stats
result={}
for path in sorted(root.glob('unprofiled-*/results.json')):
 d=json.loads(path.read_text());runs=[r for r in d['runs'] if not r['warmup']]
 pairs=[]
 for rep in sorted(set(r['rep'] for r in runs)):
  row=[r for r in runs if r['rep']==rep]
  if len(row)!=2:continue
  arms={r['arm']:r for r in row}
  pairs.append({'rep':rep,'delta_s':arms['candidate']['wall_s']-arms['base']['wall_s'],'rss_ratio':arms['candidate']['peak_rss_kib']/arms['base']['peak_rss_kib']})
 summary={'per_pid_proc_certified':False,'paired_n':len(pairs),'arms':{},'pairs':pairs,'all_product_comparisons_identical':all(c['identical'] for c in d['comparisons']),'compared_files':sum(c['compared'] for c in d['comparisons']),'compared_mrc':sum(c['mrc_compared'] for c in d['comparisons'])}
 for arm in ('base','candidate'):
  rr=[r for r in runs if r['arm']==arm]
  if not rr:continue
  wall=[r['wall_s'] for r in rr];rss=[r['peak_rss_kib'] for r in rr];cpu=[r['user_s']+r['sys_s'] for r in rr]
  summary['arms'][arm]={'n':len(rr),'median_wall_s':statistics.median(wall),'min_wall_s':min(wall),'max_wall_s':max(wall),'median_cpu_s':statistics.median(cpu),'median_rss_kib':statistics.median(rss),'max_rss_kib':max(rss)}
 if pairs:
  delta=[p['delta_s'] for p in pairs]
  summary.update(median_paired_delta_s=statistics.median(delta),min_paired_delta_s=min(delta),max_paired_delta_s=max(delta),median_delta_ci=stats.median_ci(delta),paired_robust_sd_s=stats.robust_sd(delta),sign_test=stats.sign_test(delta),max_paired_rss_ratio=max(p['rss_ratio'] for p in pairs))
 result[path.parent.name]=summary
(root/'unprofiled-summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
