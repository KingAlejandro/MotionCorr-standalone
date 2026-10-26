"""Metadata-only v2: preserve v1 fits; make the coverage warning case-specific."""
import json,hashlib,sys
from pathlib import Path
r=Path(sys.argv[1]);source=r/'crossfeed.json';data=json.loads(source.read_text())
changes=[]
for case,row in data.items():
 c=row.get('coverage_comparison')
 if c is None:continue
 old=c['warning'];different=bool(c['dropped_coordinates'] or c['added_coordinates'])
 c['warning']='Actual accepted sets differ; full-set max reduction is not pure error repair.' if different else 'Accepted-coordinate sets are identical; no accepted-set change in this case.'
 if c['warning']!=old:changes.append(dict(case=case,old=old,new=c['warning']))
out=r/'crossfeed-v2.json';assert not out.exists();out.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
(r/'coverage-note-correction.json').write_text(json.dumps(dict(scope='Metadata-only wording; original crossfeed.json retained, no fit/metric/source/gate rerun or change',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),changes=changes),indent=2)+'\n')
