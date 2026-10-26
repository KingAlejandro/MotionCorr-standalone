#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run one named frozen offline phase inside the caller's taskset/flock."""
import hashlib,json,os
from pathlib import Path
import subprocess,sys,time

root=Path('/tmp/motioncorr-w5-20261025-7b76b848/round2')
phase,script,flag=sys.argv[1:]
receipt=root/'results'/(phase+'-launch.json')
assert not receipt.exists()
assert sorted(os.sched_getaffinity(0))==list(range(48,56))
def stat():
    return {s[0]:list(map(int,s[1:9])) for l in Path('/proc/stat').read_text().splitlines()
            if (s:=l.split()) and s[0] in ['cpu'+str(i) for i in range(48,56)]}
a=stat();time.sleep(1);b=stat()
busy={k:1-((b[k][3]+b[k][4])-(a[k][3]+a[k][4]))/(sum(b[k])-sum(a[k])) for k in a}
assert max(busy.values())<.5,busy
freeze=root/(phase+'-FREEZE.json')
for rel,pin in json.loads(freeze.read_text())['files'].items():
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==pin,rel
env=os.environ.copy();env.update({k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
env['PYTHONDONTWRITEBYTECODE']='1'
started=time.time()
with (root/'results'/(phase+'.log')).open('w') as log:
    r=subprocess.run([str(Path.home()/'.mc-venv/bin/python'),'-I','-B',str(root/'scripts'/script),flag],
        env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
out=dict(host=os.uname().nodename,affinity=sorted(os.sched_getaffinity(0)),busy_fraction=busy,
    started=started,finished=time.time(),exit=r.returncode,native_runs=0,
    freeze_sha256=hashlib.sha256(freeze.read_bytes()).hexdigest(),
    round2_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()))
receipt.write_text(json.dumps(out,indent=1)+'\n');print(json.dumps(out));sys.exit(r.returncode)
