#!/usr/bin/env python3
"""Byte payload repeatability against initial main output; all runs retained."""
import hashlib,json,struct,sys
from pathlib import Path
E=Path(sys.argv[1]); C=E/'confirmation-3510561'
def inventory(root):
 rows={}
 for p in sorted((root/'Movies').glob('*.mrc')):
  with p.open('rb') as f:
   h=f.read(1024); nx,ny,nz,mode=struct.unpack_from('<4i',h)
   nsymbt=struct.unpack_from('<i',h,92)[0]
   assert nsymbt>=0
   f.seek(1024+nsymbt); digest=hashlib.sha256(); count=0
   for block in iter(lambda:f.read(1<<20),b''):
    count+=len(block);digest.update(block)
  rows[p.name]={'dimensions':[nx,ny,nz],'mode':mode,'extended_header_bytes':nsymbt,'payload_bytes':count,'payload_sha256':digest.hexdigest()}
 return rows
reference=inventory(E/'ab/out_main_j8')
assert len(reference)==24
roots=[E/'ab/out_candidate_j8']
for base in (E,C):
 for block in range(1,4):
  roots += [base/'timing'/f't_{side}_b{block}' for side in ('main','candidate')]
rows=[]
for root in roots:
 inv=inventory(root)
 rows.append({'root':str(root),'movies':len(inv),'pass':inv==reference,'missing':sorted(set(reference)-set(inv)),'extra':sorted(set(inv)-set(reference)),'changed':[n for n in reference if n in inv and inv[n]!=reference[n]],'inventory':inv})
r={'reference_root':str(E/'ab/out_main_j8'),'reference':reference,'runs':rows,'pass':len(rows)==13 and all(row['pass'] for row in rows),'note':'Hashes cover every stored payload byte after MRC extended header, retaining dimensions/mode/length. Separate v3 gates grade normalized headers and STAR fields.'}
print(json.dumps(r,indent=2));sys.exit(0 if r['pass'] else 1)
