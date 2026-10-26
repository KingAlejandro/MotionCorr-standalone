#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""cpu64 launch receipt. Invoke inside the assigned taskset/flock."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

P = Path('/tmp/motioncorr-w5-20261025-7b76b848')
P.mkdir(exist_ok=False)
(P/'results').mkdir()
receipt = dict(host=os.uname().nodename, affinity=sorted(os.sched_getaffinity(0)),
               disk_free=shutil.disk_usage('/tmp').free, started=time.time(), native_runs=0)
assert receipt['affinity'] == list(range(48,56)) and receipt['disk_free'] > 10*1024**3
def counters():
    return {a[0]: list(map(int,a[1:9])) for l in Path('/proc/stat').read_text().splitlines()
            if (a:=l.split()) and a[0] in ['cpu'+str(i) for i in range(48,56)]}
a=counters(); time.sleep(1); b=counters()
busy={k: 1-((b[k][3]+b[k][4])-(a[k][3]+a[k][4]))/(sum(b[k])-sum(a[k])) for k in a}
receipt['admission_busy_fraction']=busy
assert max(busy.values()) < .5
archive = Path('/tmp/motioncorr-w5-20261025-7b76b848-inputs.tar')
receipt['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
assert receipt['archive_sha256']=='07e1fd693dd536291d306dc430cf50fccf8f09b65d858f4c1812ea399226fe4f'
with tarfile.open(archive) as tf:
    for m in tf.getmembers():
        assert not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and (m.isfile() or m.isdir())
    tf.extractall(P,filter='data')
env=os.environ.copy()
env.update({k:'1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
env['PYTHONDONTWRITEBYTECODE']='1'
with (P/'results/challenge.log').open('w') as log:
    run=subprocess.run([str(Path.home()/'.mc-venv/bin/python'),'-I','-B',str(P/'scripts/challenge.py')],
                       env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
receipt.update(exit=run.returncode,finished=time.time(),scratch_bytes=sum(p.stat().st_size for p in P.rglob('*') if p.is_file()))
(P/'results/challenge-launch.json').write_text(json.dumps(receipt,indent=1)+'\n')
print(json.dumps(receipt))
sys.exit(run.returncode)
