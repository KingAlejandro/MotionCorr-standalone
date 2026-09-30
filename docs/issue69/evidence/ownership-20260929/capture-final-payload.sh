#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-ownership-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock -n 9
mkdir payload-healthy
build/motioncorr --i "$R/src/test-data/synthetic/synthetic_movie.tiff" --use_own --gpu 0 --j 4 --patch_x 3 --patch_y 3 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 1 --bin_factor 2 --save_noDW --even_odd_split --o "$R/payload-healthy/" > payload-healthy/run.log 2>&1 &
PID=$!
for N in $(seq 1 50); do
 [ "$(readlink /proc/$PID/exe 2>/dev/null || true)" = "$R/build/motioncorr" ] && break
 sleep 0.02
done
{
 date -Is
 printf 'actual_payload_pid=%s\n' "$PID"
 readlink /proc/$PID/exe
 ps -p "$PID" -o pid,lstart,args
 cat /proc/$PID/stat
 tr '\0' ' ' < /proc/$PID/cmdline; printf '\n'
 awk '/Cpus_allowed_list|Mems_allowed_list/' /proc/$PID/status
 numactl --show
 lscpu -e=CPU,CORE,SOCKET,NODE | awk 'NR==1 || ($1>=112 && $1<=119)'
 cat /proc/loadavg
 git -C src rev-parse HEAD
 git -C src status --porcelain
 sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject,motioncorr_retry_caller} base-build/motioncorr 2>/dev/null || sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject,motioncorr_retry_caller}
 sha256sum src/test-data/synthetic/synthetic_movie.tiff
} > payload-final.txt
wait "$PID"
/home/alex/mc-env/bin/python3 compare-native.py "$R/base-early" "$R/payload-healthy" --images 4 --stars 2 --report parity-payload-final.json
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute-payload.txt
