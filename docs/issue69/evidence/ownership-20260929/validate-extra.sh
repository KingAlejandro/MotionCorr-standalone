#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock -n 9
M=/home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff
ARGS=(--i "$M" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
mkdir boundary-trace
set +e
MC_FAULT_TRACE=1 MC_FAULT_ORDINAL=35 MC_FAULT_CODE=poison build/motioncorr_faultinject "${ARGS[@]}" --o "$R/boundary-trace/" > boundary-trace/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]
[ "$(grep -c 'cudaMalloc #' boundary-trace/run.log)" -eq 36 ] # 35 calls + injection line
! grep -q 'cudaMalloc #36' boundary-trace/run.log
grep -q 'remaining-owned=0 stale-releases=0' boundary-trace/run.log
mkdir scratch-positive
set +e
MC_FAULT_TRACE=1 MC_FAULT_ORDINAL=34 MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${ARGS[@]}" --o "$R/scratch-positive/" > scratch-positive/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -rqs 'cuda_alignpatch.cu' scratch-positive
grep -q 'remaining-owned=0 stale-releases=0' scratch-positive/run.log
[ "$(find scratch-positive -name '*.mrc' | wc -l)" -eq 0 ]
restore() { git -C src restore src/motioncorr_runner.cpp src/acc/cuda/cuda_movie_session.cu; }
trap restore EXIT
python3 - <<'PY'
from pathlib import Path
p=Path('src/src/motioncorr_runner.cpp');s=p.read_text();a=s.index('\t\t\t~PatchFourierScratchGuard() {');b=s.index('\n\t\t} patch_fcomplex_guard',a);s=s[:a]+'\t\t\t~PatchFourierScratchGuard() {}'+s[b:];p.write_text(s)
PY
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target motioncorr_faultinject > mutant-scratch-build.log 2>&1
mkdir scratch-mutant
set +e
MC_FAULT_ORDINAL=34 MC_FAULT_CODE=recoverable build/motioncorr_faultinject "${ARGS[@]}" --o "$R/scratch-mutant/" > scratch-mutant/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ]; grep -q 'remaining-owned=1 stale-releases=0' scratch-mutant/run.log
restore
# Original F4 records only the first free's error. The production two-free sequence
# must expose masking of a later consumed fatal status.
python3 - <<'PY'
from pathlib import Path
import subprocess
p=Path('src/src/acc/cuda/cuda_movie_session.cu');s=p.read_text();o=subprocess.check_output(['git','-C','src','show','a9f20ba:src/acc/cuda/cuda_movie_session.cu'],text=True)
a='bool CudaMovieSession::releasePreprocessingBuffers()';b='\nbool CudaMovieSession::computeGlobalForwardFFT()'
p.write_text(s[:s.index(a)]+o[o.index(a):o.index(b)]+s[s.index(b):])
PY
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target cuda_fault_matrix > mutant-free-build.log 2>&1
set +e
build/cuda_fault_matrix > mutant-free.log 2>&1; RC=$?
set -e
[ "$RC" -ne 0 ]; grep -q 'FAIL ownership re-entry mode=0' mutant-free.log
restore
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 > restore-extra-build.log 2>&1
build/cuda_fault_matrix > matrix-final-last.log 2>&1
sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject,motioncorr_retry_caller} > binary-hashes-last.txt
git -C src status --porcelain > source-status-last.txt
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-last.txt
printf 'PASS no allocation redispatch, actual runner scratch unwind, later fatal free retention\n'
