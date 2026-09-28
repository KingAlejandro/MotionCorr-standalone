#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock -n 9
mkdir resume-inputs resume-reference resume-work
for N in a b c; do cp src/test-data/synthetic/synthetic_movie.tiff resume-inputs/$N.tiff; done
sha256sum resume-inputs/*.tiff > resume-input-hashes.txt
ARGS=(--i "$R/resume-inputs/*.tiff" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --max_iter 50 --dose_weighting --dose_per_frame 1 --angpix 1 --voltage 300)
MC_FAULT_TRACE=1 build/motioncorr_faultinject "${ARGS[@]}" --o "$R/resume-reference/" > resume-reference/run.log 2>&1
TOTAL=$(grep -c '\[faultinject\] cudaMalloc #' resume-reference/run.log)
[ $((TOTAL%3)) -eq 0 ]
ORD=$((TOTAL/3+26)); echo "$ORD" > resume-ordinal.txt
set +e
MC_FAULT_ORDINAL="$ORD" MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${ARGS[@]}" --o "$R/resume-work/" > resume-work/failure.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -q 'remaining-owned=0 stale-releases=0' resume-work/failure.log
[ "$(find resume-work -name '*.mrc' | wc -l)" -eq 2 ]
[ "$(find resume-work -name b.mrc | wc -l)" -eq 0 ]
[ "$(find resume-work -name corrected_micrographs.star | wc -l)" -eq 0 ]
/home/alex/mc-env/bin/python3 - <<'PY'
from pathlib import Path
import json,hashlib
r=Path('resume-work');d={str(p):{'hash':hashlib.sha256(p.read_bytes()).hexdigest(),'mtime':p.stat().st_mtime_ns} for p in r.rglob('*') if p.is_file() and p.suffix in ('.mrc','.star')}
assert len(d)==4;Path('resume-before.json').write_text(json.dumps(d,indent=2))
PY
build/motioncorr "${ARGS[@]}" --o "$R/resume-work/" --only_do_unfinished > resume-work/resume.log 2>&1
/home/alex/mc-env/bin/python3 - <<'PY'
from pathlib import Path
import json,hashlib
for p,v in json.loads(Path('resume-before.json').read_text()).items():
 q=Path(p);assert hashlib.sha256(q.read_bytes()).hexdigest()==v['hash'];assert q.stat().st_mtime_ns==v['mtime']
print('PASS completed a/c image and STAR contents and mtimes survived bounded non-prefix resume')
PY
/home/alex/mc-env/bin/python3 compare-native.py "$R/resume-reference" "$R/resume-work" --images 3 --stars 4 --report parity-resume.json
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-resume.txt
printf 'PASS native middle-movie failure, zero tracked resources, only incomplete b retried\n'
