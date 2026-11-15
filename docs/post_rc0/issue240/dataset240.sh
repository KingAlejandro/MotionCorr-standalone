#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-hygiene240
export QF_W=$W QF_CPUS=112-119 QF_GPU_UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 QF_GPU_LOCK=/tmp/motioncorr-gpu0-correctness.lock
export QF_MG_CPU_A=112-115 QF_MG_CPU_B=116-119 QF_MG_W1_GPU=0
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset CUDA_VISIBLE_DEVICES PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
mkdir -p "$W/logs" "$W/tools"
cd "$W/src"
[ "$(git rev-parse HEAD)" = ed24e44b614ec158ffa919a356efaa2806b9c309 ]
# The fix only changes Python tooling. Reuse and identify frozen Release binaries.
for cfg in cpu cuda nvcomp; do
  mkdir -p "$W/build-$cfg"
  cp /mnt/clathrin/alex-motioncorr-rc0/W-QF/build-$cfg/motioncorr "$W/build-$cfg/motioncorr"
done
cp docs/rc0/qf/tools/qual_lib.py "$W/tools/"
python3 - <<'PY'
from pathlib import Path
import os
w=Path(os.environ['QF_W'])
s=(w/'src/docs/rc0/qf/tools/multigpu_publication.py').read_text()
s=s.replace("return f'{lo}-{lo + 3}', f'{lo + 4}-{hi}'", "mid = (lo + hi) // 2\n    return f'{lo}-{mid}', f'{mid + 1}-{hi}'")
s=s.replace("[MG_ALL], 16)", "[MG_ALL], 8)").replace("[MG_A, MG_B], 8)", "[MG_A, MG_B], 4)").replace("*_split(MG_B)], 4)", "*_split(MG_B)], 2)").replace('--cpu-budget 16', '--cpu-budget 8')
(w/'tools/multigpu_publication.py').write_text(s)
PY
exec 9>/tmp/motioncorr-gpu0-correctness.lock; flock -n 9
exec 8>/tmp/motioncorr-gpu1-correctness.lock; flock -n 8
exec 7>/tmp/motioncorr-gpu2-correctness.lock; flock -n 7
exec 6>/tmp/motioncorr-gpu3-correctness.lock; flock -n 6
exec 5>/tmp/motioncorr-bench.lock; flock -n 5
if [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; then echo foreign-GPU-process; exit 91; fi
{ date -u; hostname; nvidia-smi; git rev-parse HEAD; sha256sum "$W/build-nvcomp/motioncorr" "$W/tools/"*.py; } > "$W/logs/endpoint-provenance.txt"
taskset -c 112-119 python3 "$W/tools/multigpu_publication.py" --configs G,L > "$W/logs/endpoint.log" 2>&1
taskset -c 112-119 python3 "$W/tools/multigpu_publication.py" --mixed >> "$W/logs/endpoint.log" 2>&1
python3 - <<'PY'
import json, os
from pathlib import Path
w=Path(os.environ['QF_W']);d=w/'summaries/multigpu'
for cfg in ('G','L'):
    s=json.loads((d/f'multigpu-{cfg}.json').read_text())
    assert set(s['arms'])=={'s0','w1','w2','w4'}
    assert s['arms']['s0']['run']['rc']==0
    for name in ('w1','w2','w4'):
        a=s['arms'][name]
        assert a['rc']==0 and not a['contract']['problems'], (cfg,name,a)
        assert a['contract']['logfile_pdf']['pages'] is not None
    assert len(s['comparisons'])==6
    for name,c in s['comparisons'].items():
        assert c['identity_lib_status']=='PASS' and c['products_only_status']=='PASS', (cfg,name,c)
    assert s['controls']['positive_untouched_copy']['identity_lib']=='PASS'
    assert s['controls']['negative_flipped_payload_byte']['identity_lib']=='FAIL'
    print(cfg,'3/3 endpoints PASS, 6/6 comparisons PASS, controls discriminating')
s=json.loads((d/'multigpu-mixed.json').read_text())
for a in s['arms'].values(): assert a['rc']==0 and not a['contract']['problems']
assert s['w1_vs_w2']['identity_lib_status']=='PASS'
assert s['controls']=={'positive_untouched_copy':'PASS','negative_flipped_payload_byte':'FAIL'}
print('mixed 2/2 endpoints PASS, identity PASS, controls discriminating')
PY
