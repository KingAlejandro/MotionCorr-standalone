#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-254-review-20261021
export PATH=/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64
mkdir -p "$S/logs"
cp /mnt/clathrin/boundary_injection.cu "$S/"
taskset -c 80-87 nvcc -O3 -std=c++17 "$S/boundary_injection.cu" -o "$S/boundary_injection" -lcufft -lfftw3f > "$S/logs/injection-build.log" 2>&1
echo $? > "$S/logs/injection-build.exit"
exec 8>/tmp/mc254-task-gpu.lock
flock -w 600 8
exec 9>/tmp/motioncorr-gpu1-correctness.lock
flock -w 60 9
export CUDA_VISIBLE_DEVICES=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d
nvidia-smi -L > "$S/logs/injection-resources.log"
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv >> "$S/logs/injection-resources.log"
set +e
taskset -c 80-87 "$S/boundary_injection" > "$S/logs/injection.csv" 2> "$S/logs/injection.stderr"
echo $? > "$S/logs/injection.exit"
