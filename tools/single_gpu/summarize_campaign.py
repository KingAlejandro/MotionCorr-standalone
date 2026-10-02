#!/usr/bin/env python3
"""Retain observations and scope: paired process walls, resource samples, exact gates."""
import argparse,csv,json,math,re,statistics,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--phases',nargs='+',required=True);a=p.parse_args()
def percentile(xs,q):
 x=sorted(xs);pos=(len(x)-1)*q;lo=math.floor(pos);hi=math.ceil(pos);return x[lo]+(x[hi]-x[lo])*(pos-lo)
def stats(xs):return {'observations':xs,'median':statistics.median(xs),'range':[min(xs),max(xs)],'iqr':percentile(xs,.75)-percentile(xs,.25)}
out={'wall_scope':'wrapper-inclusive complete process with matching resource samplers, including output/PDF; nominal poll intervals20ms/tutorial and1ms/one-movie, scheduling delay not bounded; raw GNU time elapsed retained','quartiles':'linear interpolation (n-1)*q','phases':{}}
for phase in a.phases:
 root=a.root/phase
 provenance=json.loads((root/'provenance.json').read_text());complete=json.loads((root/'COMPLETE.json').read_text());expected=provenance['expected_pair_count']

 if not(type(expected) is int and expected>0 and complete['expected_pair_count']==expected):raise RuntimeError('invalid expected pair count')
 digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if not(complete['runs_sha256']==digest(root/'runs.json') and complete['provenance_sha256']==digest(root/'provenance.json')):raise RuntimeError('changed campaign records')
 if set(complete['exact_sha256'])!={str(n) for n in range(1,expected+1)}:raise RuntimeError('incomplete exact inventory')
 if not all(complete['exact_sha256'][str(n)]==digest(root/f'exact-{n}.json') for n in range(1,expected+1)):raise RuntimeError('changed exact verdicts')
 records=json.loads((root/'runs.json').read_text());arms={k:[x['whole_process_wall_seconds'] for x in records if x['arm']==k] for k in ['baseline','candidate']};
 if not len(arms['baseline'])==len(arms['candidate'])>0:raise RuntimeError('unbalanced arm counts')
 if not(len(records)==2*expected and {(x['pair'],x['arm']) for x in records}=={(n,arm) for n in range(1,expected+1) for arm in ('baseline','candidate')}):raise RuntimeError('incomplete/duplicate campaign')
 inventory=complete.get('device_sha256')
 if not isinstance(inventory,dict) or set(inventory)!={f"{x['arm']}-{x['pair']}" for x in records}:raise RuntimeError('incomplete device sample inventory')
 if any(inventory[f"{x['arm']}-{x['pair']}"]!=digest(Path(x['directory'])/'device.csv') for x in records):raise RuntimeError('changed device samples')
 details=[]
 for record in records:
  d=Path(record['directory']);dev=list(csv.reader((d/'device.csv').open()));values=[]
  for row in dev:
   try:values.append([float(row[2]),float(row[3])])
   except (ValueError,IndexError):continue
  if not values:raise RuntimeError('no valid device samples')
  resource=record['resource'];peak=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',resource)[1]);cpu=int(re.search(r'Percent of CPU this job got: (\d+)%',resource)[1]);elapsed=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)',resource)[1]
  details.append({'pair':record['pair'],'arm':record['arm'],'wall_seconds':record['whole_process_wall_seconds'],'gnu_time_elapsed':elapsed,'payload_rss_peak_KiB':peak,'payload_rss_peak_GiB':peak/1024**2,'cpu_percent':cpu,'sampled_GPU_util_mean_percent':statistics.mean(x[0] for x in values),'sampled_device_memory_peak_MiB':max(x[1] for x in values),'actual_payload_cpu_mask':record['actual_cpu_mask']})
 pairs=[]
 for n in sorted({x['pair'] for x in records}):
  b=next(x['whole_process_wall_seconds'] for x in records if x['pair']==n and x['arm']=='baseline');c=next(x['whole_process_wall_seconds'] for x in records if x['pair']==n and x['arm']=='candidate');pairs.append(b-c)
 exact=[json.loads((root/f'exact-{n}.json').read_text()) for n in sorted({x['pair'] for x in records})];
 if not all(x['status']=='PASS' for x in exact):raise RuntimeError('exact verdict not PASS')
 out['phases'][phase]={'baseline':stats(arms['baseline']),'candidate':stats(arms['candidate']),'paired_savings_seconds':stats(pairs),'median_wall_improvement_percent':100*(statistics.median(arms['baseline'])-statistics.median(arms['candidate']))/statistics.median(arms['baseline']),'faster_pairs':sum(x>0 for x in pairs),'pair_count':len(pairs),'exact_non_PDF_tree_pairs':'PASS','resource_observations':details}
print(json.dumps(out,indent=2))
