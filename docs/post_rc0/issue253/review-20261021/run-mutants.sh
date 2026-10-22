#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-254-review-20261021
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
exec 8>/tmp/mc254-task-gpu.lock
flock -w 600 8
exec 9>/tmp/motioncorr-gpu3-correctness.lock
flock -w 60 9
for target in cuda_hermitian_inverse_no_projection cuda_hermitian_inverse_wrapper_no_projection cuda_hermitian_inverse_dose_no_projection cuda_patch_batch_ccf_perpatch_no_projection cuda_patch_batch_ccf_batched_no_projection; do
 set +e
 taskset -c 80-87 "$S/build-nvcomp/$target" > "$S/logs/raw-$target.log" 2>&1
 rc=$?
 set -e
 echo "$rc" > "$S/logs/raw-$target.exit"
 test "$rc" -eq 1
 grep -q 'INVARIANT FAIL' "$S/logs/raw-$target.log"
done
taskset -c 80-87 "$S/build-nvcomp/cuda_hermitian_inverse" --matrix > "$S/logs/inverse-matrix.log" 2>&1
echo $? > "$S/logs/inverse-matrix.exit"
