#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Launch a single frozen factorial under the caller's taskset/flock."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

P=Path('/tmp/motioncorr-w5-20261025-7b76b848')
assert not (P/'results/factorial-launch.json').exists()
receipt=dict(host=os.uname().nodename,affinity=sorted(os.sched_getaffinity(0)),started=time.time(),native_runs=0)
assert receipt['affinity']==list(range(48,56))
def counters():
    return {a[0]:list(map(int,a[1:9])) for l in Path('/proc/stat').read_text().splitlines()
            if (a:=l.split()) and a[0] in ['cpu'+str(i) for i in range(48,56)]}
a=counters();time.sleep(1);b=counters()
receipt['admission_busy_fraction']={k:1-((b[k][3]+b[k][4])-(a[k][3]+a[k][4]))/(sum(b[k])-sum(a[k])) for k in a}
assert max(receipt['admission_busy_fraction'].values())<.5
with tarfile.open('/tmp/motioncorr-w5-20261025-7b76b848-factorial-inputs.tar') as tf:
    for m in tf.getmembers():
        assert not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and (m.isfile() or m.isdir())
    tf.extractall(P,filter='data')
freeze=json.loads((P/'FREEZE.json').read_text())
for rel,pin in freeze['files'].items():
    assert hashlib.sha256((P/rel).read_bytes()).hexdigest()==pin,rel
env=os.environ.copy();env.update({k:'1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
env['PYTHONDONTWRITEBYTECODE']='1'
with (P/'results/factorial.log').open('w') as log:
    run=subprocess.run([str(Path.home()/'.mc-venv/bin/python'),'-I','-B',str(P/'scripts/intervention.py'),
                        '--run-frozen-convention-experiment'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
receipt.update(exit=run.returncode,finished=time.time(),scratch_bytes=sum(p.stat().st_size for p in P.rglob('*') if p.is_file()),
               freeze_sha256=hashlib.sha256((P/'FREEZE.json').read_bytes()).hexdigest())
(P/'results/factorial-launch.json').write_text(json.dumps(receipt,indent=1)+'\n')
print(json.dumps(receipt))
sys.exit(run.returncode)
