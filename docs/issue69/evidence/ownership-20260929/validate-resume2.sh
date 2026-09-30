#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock -n 9
MOV="$R/resume-inputs/*.tiff"
ARGS=(--i "$MOV" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --max_iter 50 --dose_weighting --dose_per_frame 1 --angpix 1 --voltage 300)
mkdir resume-work2
TOTAL=$(grep -c '\[faultinject\] cudaMalloc #' resume-reference/run.log)
[ $((TOTAL%3)) -eq 0 ]
ORD=$((TOTAL/3+27)); echo "$ORD" > resume-ordinal2.txt
set +e
MC_FAULT_ORDINAL="$ORD" MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${ARGS[@]}" --o "$R/resume-work2/" > resume-work2/failure.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -q 'remaining-owned=0 stale-releases=0' resume-work2/failure.log
[ "$(find resume-work2 -name '*.mrc' | wc -l)" -eq 2 ]
[ "$(find resume-work2 -name b.mrc | wc -l)" -eq 0 ]
[ "$(find resume-work2 -name corrected_micrographs.star | wc -l)" -eq 0 ]
/home/alex/mc-env/bin/python3 - <<'PY'
from pathlib import Path
import json,hashlib
r=Path('resume-work2');d={str(p):{'hash':hashlib.sha256(p.read_bytes()).hexdigest(),'mtime':p.stat().st_mtime_ns} for p in r.rglob('*') if p.is_file() and p.suffix in ('.mrc','.star')}
assert len(d)==4;Path('resume-before2.json').write_text(json.dumps(d,indent=2))
PY
build/motioncorr "${ARGS[@]}" --o "$R/resume-work2/" --only_do_unfinished > resume-work2/resume.log 2>&1
/home/alex/mc-env/bin/python3 - <<'PY'
from pathlib import Path
import json,hashlib
for p,v in json.loads(Path('resume-before2.json').read_text()).items():
 q=Path(p);assert hashlib.sha256(q.read_bytes()).hexdigest()==v['hash'];assert q.stat().st_mtime_ns==v['mtime']
print('PASS completed a/c image and STAR contents and mtimes survived bounded non-prefix resume')
PY
/home/alex/mc-env/bin/python3 compare-native.py "$R/resume-reference" "$R/resume-work2" --images 3 --stars 4 --report parity-resume2.json
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-resume.txt
printf 'PASS native middle-movie failure, zero tracked resources, only incomplete b retried\n'
