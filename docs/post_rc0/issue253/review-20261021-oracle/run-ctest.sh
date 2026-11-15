#!/bin/bash
# CTest for the three Release builds. CUDA suites hold the GPU3 lock (by UUID) only while they run; never delete lock files.
set -u
S=/mnt/clathrin/alex-motioncorr-254-oracle-20261021
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 CUDA_DEVICE_ORDER=PCI_BUS_ID
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
for type in ${TYPES:-cpu cuda nvcomp}; do
  if [ "$type" != cpu ]; then
    exec 9>/tmp/motioncorr-gpu3-correctness.lock
    flock -w 1800 9 || exit 3
    export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
    nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv > "$S/logs/occupancy-ctest-$type.log"
  fi
  taskset -c ${CPUS:-112-119} ctest --test-dir "$S/build-$type" -j1 --output-on-failure --output-junit "$S/logs/ctest-$type.xml" > "$S/logs/ctest-$type.log" 2>&1
  echo $? > "$S/logs/ctest-$type.exit"
  if [ "$type" != cpu ]; then flock -u 9; exec 9>&-; fi
done
echo done > "$S/ctest-done"
