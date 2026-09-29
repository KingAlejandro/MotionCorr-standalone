#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock -n 9
ctest --test-dir build --output-on-failure -j1 > ctest-v5.log 2>&1
build/cuda_fault_matrix > matrix-v5.log 2>&1
sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject,motioncorr_retry_caller} > executed-binaries-v5.txt
git -C src rev-parse HEAD > executed-source-v5.txt
MOV=/home/alex/MotionCorr-standalone/relion30_tutorial/Movies
COMMON=(--use_own --gpu 0 --j 4 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
mkdir final-v5-24
build/motioncorr --i "$MOV/*.tiff" --gainref "$MOV/gain.mrc" --o "$R/final-v5-24/" "${COMMON[@]}" > final-v5-24/run.log 2>&1
EARGS=(--i "$R/src/test-data/synthetic/synthetic_movie.tiff" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 1 --bin_factor 2 --save_noDW --even_odd_split)
mkdir final-v5-early
build/motioncorr "${EARGS[@]}" --o "$R/final-v5-early/" > final-v5-early/run.log 2>&1
/home/alex/mc-env/bin/python3 compare-native.py "$R/base24" "$R/final-v5-24" --images 24 --stars 25 --report parity24-v5.json
/home/alex/mc-env/bin/python3 compare-native.py "$R/base-early" "$R/final-v5-early" --images 4 --stars 2 --report parity-early-v5.json
mkdir retry-v5
MC_RETRY_CALLER=1 build/motioncorr_retry_caller --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/retry-v5/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 50 --seed 1 --dose_weighting --dose_per_frame 1 --angpix 1 --voltage 300 > retry-v5/run.log 2>&1
grep -q 'second native alignment succeeded' retry-v5/run.log
# Target the first local host alignment, while a legacy real-frame cache is retained.
mkdir frame-cache-good
set +e
MC_FAULT_TRACE=1 MC_FAULT_ORDINAL=19 MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${EARGS[@]}" --o "$R/frame-cache-good/" > frame-cache-good/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -rqs 'cuda_alignpatch.cu' frame-cache-good
grep -q 'remaining-owned=0 stale-releases=0' frame-cache-good/run.log
[ "$(find frame-cache-good -name '*.mrc' | wc -l)" -eq 0 ]
restore() { git -C src restore src/motioncorr_runner.cpp; }
trap restore EXIT
python3 - <<'PY'
from pathlib import Path
p=Path('src/src/motioncorr_runner.cpp');s=p.read_text();needle='~MovieFrameCacheGuard() { cudaReleaseCachedFrames(); }';assert s.count(needle)==1;p.write_text(s.replace(needle,'~MovieFrameCacheGuard() {}'))
PY
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target motioncorr_faultinject > mutant-frame-cache-build.log 2>&1
mkdir frame-cache-mutant
set +e
MC_FAULT_ORDINAL=19 MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${EARGS[@]}" --o "$R/frame-cache-mutant/" > frame-cache-mutant/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -q 'remaining-owned=1 stale-releases=0' frame-cache-mutant/run.log
restore
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 > restored-v5-build.log 2>&1
build/cuda_fault_matrix > matrix-v5-restored.log 2>&1
# Existing consumed-error and scratch throwing paths re-executed on final source.
ARGS=(--i "$MOV/20170629_00021_frameImage.tiff" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
for N in 34 35; do
 D="$R/final-fault-$N"; mkdir "$D"; CODE=recoverable; [ "$N" -eq 35 ] && CODE=poison
 set +e
 MC_FAULT_TRACE=1 MC_FAULT_ORDINAL="$N" MC_FAULT_CODE="$CODE" build/motioncorr_faultinject "${ARGS[@]}" --o "$D/" > "$D/run.log" 2>&1
 RC=$?
 set -e
 [ "$RC" -ne 0 ]; grep -q 'remaining-owned=0 stale-releases=0' "$D/run.log"
 [ "$(find "$D" -name '*.mrc' | wc -l)" -eq 0 ]
 [ "$(find "$D" -name corrected_micrographs.star | wc -l)" -eq 0 ]
 if [ "$N" -eq 35 ]; then grep -rqs 'recorded at cudaPreparePatch:' "$D"; ! grep -q 'cudaMalloc #36' "$D/run.log"; fi
done
mkdir final-recoverable
MC_FAULT_ORDINAL=35 MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${ARGS[@]}" --o "$R/final-recoverable/" > final-recoverable/run.log 2>&1
[ "$(find final-recoverable -name '*.mrc' | wc -l)" -eq 1 ]
grep -q 'remaining-owned=0 stale-releases=0' final-recoverable/run.log
git -C src status --porcelain > source-status-v5.txt
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-v5.txt
printf 'PASS final movie-cache ownership source=%s\n' "$(git -C src rev-parse HEAD)"
