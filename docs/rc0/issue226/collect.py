import hashlib,json,re
from pathlib import Path
W=Path('/mnt/clathrin/alex-motioncorr-226')
result={}
for arm in ['runs-base','runs-d2-124a8708','runs-d2-728f7ada','runs-d2-bb348554','runs-d3']:
 rows=[]
 for p in sorted((W/arm).glob('*/result.json')):
  r=json.loads(p.read_text())
  text=(p.parent/'stdout.txt').read_text(errors='replace')
  logs='\n'.join(q.read_text(errors='replace') for q in (p.parent/'out').rglob('*.log'))
  rows.append({k:r.get(k) for k in ['spec','exit','timed_out','wall_s','free_vram_after_balloon_mib','max_rss_mib','all_products','joint_star','balloon_gone','gpu_used_after_mib','gpu_apps_after','compare','witness','cmd','identity','sampled']} | {
   'local_admission':re.findall(r'Local alignment admission[^\n]*',logs),
   'retry_admission':re.findall(r'Resident patch retry admission[^\n]*',logs),
   'batch_chunks':[int(v) for v in re.findall(r'Batched patch alignment:.*?chunk size (\d+)',logs)],
   'cpu_preprocessing':'Falling back to CPU preprocessing' in logs,
   'early_oom':re.findall(r'ERROR: Out of GPU memory[^\n]*',text),
   'incompatible':'incompatible' in text.lower(),
   'stray_products':r.get('products'),
  })
 result[arm]=rows
(W/'collected.json').write_text(json.dumps(result,indent=2))
print({k:len(v) for k,v in result.items()})
