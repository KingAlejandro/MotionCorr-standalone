#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-hygiene239
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
cd "$W/src"
for cfg in cpu cuda nvcomp; do
  flock -n /tmp/motioncorr-bench.lock true
  if [ "$cfg" != cpu ]; then
    exec 9>/tmp/motioncorr-gpu3-correctness.lock
    flock -n 9
    export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID
    if nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$CUDA_VISIBLE_DEVICES"; then echo lane-occupied; exit 90; fi
  fi
  taskset -c 112-119 python3 tools/validate_test_collection.py --test-dir "$W/build-$cfg" > "$W/logs/collection-$cfg.log" 2>&1
  set +e
  taskset -c 112-119 ctest --test-dir "$W/build-$cfg" --output-on-failure -j1 --output-junit "$W/logs/ctest-$cfg.xml" > "$W/logs/ctest-$cfg.log" 2>&1
  rc=$?
  set -e
  echo "$rc" > "$W/logs/ctest-$cfg.exit"
  echo "ctest $cfg rc=$rc"
  if [ "$cfg" != cpu ]; then flock -u 9; exec 9>&-; unset CUDA_VISIBLE_DEVICES; fi
done
