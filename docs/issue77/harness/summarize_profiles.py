#!/usr/bin/env python3
"""Summarize reported CUDA profile fields without conflating them with wall time."""
import json,re,sys
from collections import defaultdict
from pathlib import Path
root=Path(sys.argv[1])
if (root/'ab').is_dir(): root=root/'ab'
rows=[]
for label in ('main','candidate'):
    profiles=defaultdict(lambda:defaultdict(float))
    count=defaultdict(int)
    for log in sorted((root/f'out_{label}_j8'/'Movies').glob('*.log')):
        stage=None
        for line in log.read_text(errors='replace').splitlines():
            m=re.search(r'\[CUDA (.+? Profile[^\]]*)\]',line)
            if m: stage=m.group(1);count[stage]+=1;continue
            if '[CUDA ' in line and 'completed' in line:stage=None
            if stage:
                m=re.search(r'^\s*(.+?):\s*([0-9.]+)\s+ms',line)
                if m:profiles[stage][m.group(1).strip()]+=float(m.group(2))
    rows.append({'label':label,'profile_instances':dict(count),'reported_ms_totals':dict(profiles)})
print(json.dumps({'note':'Fields come from application profiles. Totals include overlapping categories; do not sum them into end-to-end time. Device process memory samples are separate.','runs':rows},indent=2))
