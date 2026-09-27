#!/usr/bin/env python3
"""Explain intentional log-label changes without altering strict comparison evidence."""
import json,sys
from pathlib import Path
from compare_outputs import normalize_text
work=Path(sys.argv[1]); ref=work/'out_main_j8'; test=work/'out_candidate_j8'
rows=[]
for p in sorted((ref/'Movies').glob('*.log')):
    q=test/'Movies'/p.name
    a=normalize_text(p.read_bytes(),str(ref)).splitlines()
    b=normalize_text(q.read_bytes(),str(test)).splitlines()
    ds=[]
    for n in range(max(len(a),len(b))):
        x=a[n] if n<len(a) else None; y=b[n] if n<len(b) else None
        if x!=y:
            accepted=x is not None and y is not None and x.replace('Peak GPU memory allocated:    ', 'Tracked alignment memory:     ')==y
            ds.append({'line':n+1,'main':x,'candidate':y,'intentional_memory_label_only':accepted})
    rows.append({'path':str(p.relative_to(ref)),'differences':ds,'only_intentional_memory_label':all(d['intentional_memory_label_only'] for d in ds)})
print(json.dumps({'note':'Explanatory audit only; original auxiliary and overall FAIL are preserved. PDF differences remain separate.','logs':rows,'all24_logs_only_intentional_label':len(rows)==24 and all(r['only_intentional_memory_label'] for r in rows)},indent=2))
