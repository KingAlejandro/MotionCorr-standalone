#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock
flock -n 9
# Every child inherits the taskset mask from the enclosing invocation.
{
 date -Is; hostname; git -C src rev-parse HEAD; git -C src status --porcelain
 nvcc --version; nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader
 nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader
 echo "payload_pid=$$"; readlink /proc/$$/exe; ps -p $$ -o pid,lstart,cmd
 grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/$$/status
 numactl --show; lscpu -e=CPU,CORE,SOCKET,NODE; uptime
 sha256sum build/motioncorr build/cuda_fault_matrix build/motioncorr_retry_caller build/motioncorr_faultinject
 find /home/alex/MotionCorr-standalone/relion30_tutorial/Movies -type f -name '*.tiff' -exec sha256sum {} +
 sha256sum /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/gain.mrc
} > provenance-final.txt 2>&1
COMMON=(--use_own --gpu 0 --j 4 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1
        --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885)
MOV=/home/alex/MotionCorr-standalone/relion30_tutorial/Movies
mkdir cand24
build/motioncorr --i "$MOV/*.tiff" --gainref "$MOV/gain.mrc" --o "$R/cand24/" "${COMMON[@]}" > cand24/run.log 2>&1
mkdir cand-early
build/motioncorr --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/cand-early/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 1 --bin_factor 2 --save_noDW --even_odd_split > cand-early/run.log 2>&1
# Copy final binaries before negative-control edits. Only this freshly created source
# checkout is modified; the repository/other users' checkouts are never touched.
mkdir final-binaries
cp build/{motioncorr,cuda_fault_matrix,motioncorr_retry_caller,motioncorr_faultinject} final-binaries/
FINAL=$(git -C src rev-parse HEAD)
restore() { git -C src restore src/acc/cuda/cuda_alignpatch.cu src/acc/cuda/cuda_movie_session.cu src/acc/cuda/cuda_fft_prep.cu src/motioncorr_runner.cpp; }
trap restore EXIT
rebuild() { flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target "$1" > "$2" 2>&1; }
# Old alignment source: should reproduce actual resource leaks on throwing paths.
git -C src show a9f20ba:src/acc/cuda/cuda_alignpatch.cu > src/src/acc/cuda/cuda_alignpatch.cu
rebuild cuda_fault_matrix mutant-align-build.log
set +e
build/cuda_fault_matrix > mutant-align.log 2>&1; RC=$?
set -e
[ "$RC" -ne 0 ] && grep -q 'leaked owned resources' mutant-align.log
restore
# Pre-repair resident cache replacement function, keeping all other current code.
python3 - <<'PY'
from pathlib import Path
import subprocess
p=Path('src/src/acc/cuda/cuda_movie_session.cu');s=p.read_text()
o=subprocess.check_output(['git','-C','src','show','a9f20ba:src/acc/cuda/cuda_movie_session.cu'],text=True)
a='bool CudaMovieSession::preparePatchInVram(';b='\nbool CudaMovieSession::reconstructDoseWeighted('
s=s[:s.index(a)]+o[o.index(a):o.index(b)]+s[s.index(b):];p.write_text(s)
PY
rebuild cuda_fault_matrix mutant-cache-build.log
set +e
build/cuda_fault_matrix > mutant-cache.log 2>&1; RC=$?
set -e
[ "$RC" -ne 0 ] && grep -q 'FAIL ownership re-entry' mutant-cache.log
restore
# Actual runner reset removed. The injected first estimate must contaminate retry.
python3 - <<'PY'
from pathlib import Path
p=Path('src/src/motioncorr_runner.cpp');s=p.read_text()
for axis in ['x','y']:
 line=f'local_{axis}shifts.assign(local_{axis}shifts.size(), (RFLOAT)0);'
 assert s.count(line)==1;s=s.replace(line,'')
p.write_text(s)
PY
rebuild motioncorr_retry_caller mutant-reset-build.log
mkdir mutant-reset
set +e
MC_RETRY_CALLER=1 build/motioncorr_retry_caller --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/mutant-reset/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --max_iter 50 --seed 1 --dose_weighting --dose_per_frame 1 --angpix 1 --voltage 300 > mutant-reset/run.log 2>&1
RC=$?
set -e
[ "$RC" -ne 0 ] && grep -q 'stale first-attempt shift' mutant-reset/run.log
restore
# Restore and rerun final matrix after mutants, before building current-main reference.
rebuild cuda_fault_matrix restored-build.log
build/cuda_fault_matrix > matrix-final.log 2>&1
# Native reference is current main, same toolchain/input/options/GPU; no timing claim.
git -C src checkout --detach a75a3f87f7ef17e0a29b1c91a1edecda08ebed34
rebuild motioncorr base-build.log
cp build/motioncorr final-binaries/main-motioncorr
mkdir base24
build/motioncorr --i "$MOV/*.tiff" --gainref "$MOV/gain.mrc" --o "$R/base24/" "${COMMON[@]}" > base24/run.log 2>&1
mkdir base-early
build/motioncorr --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --o "$R/base-early/" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 1 --bin_factor 2 --save_noDW --even_odd_split > base-early/run.log 2>&1
sha256sum final-binaries/main-motioncorr > base-binary-hash.txt
git -C src checkout --detach "$FINAL"
flock -n /tmp/motioncorr-vm-build.lock cmake --build build -j4 > restore-final-build.log 2>&1
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute.txt
printf 'PASS final native runs, ownership/cache/reset negative controls; source restored %s\n' "$FINAL"
