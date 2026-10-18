#!/bin/bash
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-D10d
cd "$W"
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
UUID=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598
st() { echo "$* $(date -u +%FT%TZ)"; }
st START
for b in head-cpu head-asan head-cuda head-nvcomp composed-cpu; do
  mask=112-119; case $b in head-asan|composed-cpu) mask=80-87;; esac
  taskset -c $mask cmake --build build-$b -j8 > logs/rebuild-$b.log 2>&1; echo "rebuild $b rc=$? $(grep -cE "Building|Linking" logs/rebuild-$b.log) compile/link lines"
done
sha256sum build-*/motioncorr build-*/runner_numerics > raw/binaries.sha256
( taskset -c 80-87 ctest --test-dir build-composed-cpu --output-on-failure > raw/ctest-composed-cpu.log 2>&1; st "composed-cpu rc=$?"
  taskset -c 80-87 ctest --test-dir build-head-asan -R "^EerMemorySafety\$" --output-on-failure > raw/ctest-head-asan-eer.log 2>&1; st "head-asan-eer rc=$?" ) &
taskset -c 112-119 ctest --test-dir build-head-cpu --output-on-failure > raw/ctest-head-cpu.log 2>&1; st "head-cpu rc=$?"
exec 9>/tmp/motioncorr-gpu2-correctness.lock; flock 9; st "gpu2 lock held"
export CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader > raw/gpu-identity.txt
for b in head-cuda head-nvcomp; do taskset -c 112-119 ctest --test-dir build-$b --output-on-failure > raw/ctest-$b.log 2>&1; st "$b rc=$?"; done
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader >> raw/gpu-identity.txt
flock -u 9
wait
st END
