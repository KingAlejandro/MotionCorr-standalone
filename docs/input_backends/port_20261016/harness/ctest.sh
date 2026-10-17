#!/bin/bash
# usage: ctest.sh <build-name> <cuda:0|1>   (waits for builds, then runs full CTest, logs kept)
set -u
wait_bench() { while ! flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held by another session; waiting 60 s ($(date -u +%FT%TZ))" >&2; sleep 60; done; }
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
n=$1; cuda=$2
export PATH=/home/alex/mc-env/bin:/usr/local/cuda-12.8/bin:$PATH
cd $D/build-$n || exit 1
GPUUUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
date -u +%FT%TZ > $D/ctest-$n.started
wait_bench
if [ "$cuda" = 1 ]; then
  taskset -c 72-79 ctest -j4 -LE hardware --output-on-failure --timeout 900 > $D/ctest-$n-nonhw.log 2>&1; echo "nonhw rc=$?" > $D/ctest-$n.rc
  wait_bench
  ( flock -w 14400 9
    echo "lock acquired $(date -u +%FT%TZ)" > $D/ctest-$n-hw.lockinfo
    nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader > $D/ctest-$n-hw.pre-smi
    CUDA_VISIBLE_DEVICES=$GPUUUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c 72-79 ctest -j1 -L hardware --output-on-failure --timeout 1800 > $D/ctest-$n-hw.log 2>&1; echo "hw rc=$?" >> $D/ctest-$n.rc
  ) 9>/tmp/motioncorr-gpu3-correctness.lock
else
  taskset -c 72-79 ctest -j4 --output-on-failure --timeout 900 > $D/ctest-$n-all.log 2>&1; echo "all rc=$?" > $D/ctest-$n.rc
fi
date -u +%FT%TZ > $D/ctest-$n.finished
