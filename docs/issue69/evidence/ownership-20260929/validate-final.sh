#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock
flock -n 9
git -C src fetch -q /home/alex/mc-pr115-ownership-v4.bundle HEAD
git -C src checkout -q --detach FETCH_HEAD
FINAL=$(git -C src rev-parse HEAD)
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 > build-v4.log 2>&1
ctest --test-dir build --output-on-failure -j1 > ctest-v4.log 2>&1
build/cuda_fault_matrix > matrix-v4.log 2>&1
MOV=/home/alex/MotionCorr-standalone/relion30_tutorial/Movies
COMMON=(--use_own --gpu 0 --j 4 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
mkdir final24
build/motioncorr --i "$MOV/*.tiff" --gainref "$MOV/gain.mrc" --o "$R/final24/" "${COMMON[@]}" > final24/run.log 2>&1
mkdir final-early
build/motioncorr --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/final-early/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 1 --bin_factor 2 --save_noDW --even_odd_split > final-early/run.log 2>&1
/home/alex/mc-env/bin/python3 compare-native.py "$R/base24" "$R/final24" --images 24 --stars 25 --report parity24-final.json
/home/alex/mc-env/bin/python3 compare-native.py "$R/base-early" "$R/final-early" --images 4 --stars 2 --report parity-early-final.json
mkdir retry-final
MC_RETRY_CALLER=1 build/motioncorr_retry_caller --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/retry-final/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 50 --seed 1 --dose_weighting --dose_per_frame 1 --angpix 1 --voltage 300 > retry-final/run.log 2>&1
grep -q 'second native alignment succeeded' retry-final/run.log
# Function-attributed fallback injection: first try previous ordinal, then search.
COMMON2=(--use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
M="$MOV/20170629_00021_frameImage.tiff"
ORD=''
for N in 35 $(seq 1 60); do
  D="$R/boundary-probe-$N"; mkdir -p "$D"
  set +e
  MC_FAULT_ORDINAL="$N" MC_FAULT_CODE=poison build/motioncorr_faultinject --i "$M" --o "$D/" "${COMMON2[@]}" > "$D/run.log" 2>&1
  RC=$?
  set -e
  if grep -rqs 'recorded at cudaPreparePatch:' "$D"; then
    [ "$RC" -ne 0 ]; ORD=$N; break
  fi
done
[ -n "$ORD" ]
printf '%s\n' "$ORD" > boundary-ordinal.txt
D="$R/boundary-probe-$ORD"
[ "$(find "$D" -name '*.mrc' | wc -l)" -eq 0 ]
[ "$(find "$D" -name corrected_micrographs.star | wc -l)" -eq 0 ]
grep -q 'remaining-owned=0 stale-releases=0' "$D/run.log"
mkdir boundary-recoverable
MC_FAULT_ORDINAL="$ORD" MC_FAULT_CODE=recoverable build/motioncorr_faultinject --i "$M" --o "$R/boundary-recoverable/" "${COMMON2[@]}" > boundary-recoverable/run.log 2>&1
[ "$(find boundary-recoverable -name '*.mrc' | wc -l)" -eq 1 ]
grep -q 'remaining-owned=0 stale-releases=0' boundary-recoverable/run.log
# Failure recording removed: a cleared last-error slot must become a discriminating
# BAD completion, so a mutant crash/configuration failure cannot pass this check.
restore() { git -C src restore src/acc/cuda/cuda_fft_prep.cu src/acc/cuda/cuda_movie_session.cu; }
trap restore EXIT
python3 - <<'PY'
from pathlib import Path
p=Path('src/src/acc/cuda/cuda_fft_prep.cu');s=p.read_text();needle='if (failure) failure->record(e, __func__, __LINE__);';assert s.count(needle)==1;p.write_text(s.replace(needle,''))
PY
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target motioncorr_faultinject > mutant-record-build.log 2>&1
mkdir boundary-mutant
MC_FAULT_ORDINAL="$ORD" MC_FAULT_CODE=poison build/motioncorr_faultinject --i "$M" --o "$R/boundary-mutant/" "${COMMON2[@]}" > boundary-mutant/run.log 2>&1
[ "$(find boundary-mutant -name '*.mrc' | wc -l)" -eq 1 ]
! grep -rqs 'unusable after fallback patch preparation' boundary-mutant
restore
# Remove session entry refusal only: injected sticky fatal status must no longer
# permit the four-sequence control to pass.
python3 - <<'PY'
from pathlib import Path
p=Path('src/src/acc/cuda/cuda_movie_session.cu');s=p.read_text();assert 'failure_state.isPoisoned() || !is_initialized' in s;p.write_text(s.replace('failure_state.isPoisoned() || !is_initialized','!is_initialized'))
PY
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target cuda_fault_matrix > mutant-entry-build.log 2>&1
set +e
build/cuda_fault_matrix > mutant-entry.log 2>&1; RC=$?
set -e
[ "$RC" -ne 0 ] && grep -q 'FAIL ownership re-entry mode=0' mutant-entry.log
restore
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 > restored-v4-build.log 2>&1
build/cuda_fault_matrix > matrix-v4-restored.log 2>&1
sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject,motioncorr_retry_caller} > binary-hashes-v4.txt
git -C src status --porcelain > source-status-v4.txt
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-v4.txt
printf 'PASS final source %s, parity, production retry, fatal fallback and entry controls\n' "$FINAL"
