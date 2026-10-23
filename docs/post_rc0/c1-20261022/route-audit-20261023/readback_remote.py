from pathlib import Path
import hashlib,json,time,os
S=Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb')
sha=lambda b:hashlib.sha256(b).hexdigest()
r={'utc':time.strftime('%FT%TZ',time.gmtime()),'host':os.uname().nodename,'cpus':sorted(os.sched_getaffinity(0)),'arms':{}}
for arm in ['c1-G','c1-L']:
 d=S/'t24-i3'/arm;jb=(d/'RUN.json').read_bytes();j=json.loads(jb)
 files={}
 for name,p in [('witness',d/'ingest-witness.txt'),('input_star',d/'cwd/movies.star')]:
  b=p.read_bytes();files[name]={'path':str(p),'sha256':sha(b),'size':len(b),'text':b.decode()}
 b=Path(j['binary']).read_bytes();r['arms'][arm]={'RUN_sha256':sha(jb),'RUN':j,'files':files,'live_binary_sha256':sha(b)}
print(json.dumps(r))
