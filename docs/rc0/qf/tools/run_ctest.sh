#!/bin/bash
# QF item 1: full CTest, no exclusions, one configuration. Ported from Q1 (PR #209).
# Usage: run_ctest.sh cpu|cuda|nvcomp [tag] [ctest -R regex]
# Lane from the environment (defaults = W-QF-PREP rehearsal lane): QF_W, QF_CPUS,
# QF_GPU_UUID, QF_GPU_LOCK. CUDA configurations hold the lane GPU flock for the whole batch
# and see only that GPU (CUDA_VISIBLE_DEVICES=<UUID>). Every configuration waits while the
# bench lock is held (probe only). Writes $QF_W/ctest-<cfg>[-tag].{log,junit.xml,exit}.
set -u
cfg=$1; tag=${2:-}; rx=${3:-}
W=${QF_W:-/mnt/clathrin/alex-motioncorr-rc0/W-QF-PREP}
CPUS=${QF_CPUS:-96-103}
GPU=${QF_GPU_UUID:-GPU-eddb42fe-4f9a-adde-76d3-b924e14add54}
LOCK=${QF_GPU_LOCK:-/tmp/motioncorr-gpu0-correctness.lock}
B=$W/build-$cfg
O=$W/ctest-$cfg${tag:+-$tag}
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
cd $W/src || exit 90                       # real git checkout (CiFailClosedControls needs .git)
if [ "$cfg" != cpu ]; then
  export CUDA_VISIBLE_DEVICES=$GPU CUDA_DEVICE_ORDER=PCI_BUS_ID
  exec 9>$LOCK
  flock 9
  # foreign compute process on the lane GPU -> wait (never touch it)
  while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$GPU"; do sleep 10; done
fi
until flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held, waiting $(date -u +%T)" >> $O.waits; sleep 60; done
{
  echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l)"
  echo "mask: $CPUS gpu: ${CUDA_VISIBLE_DEVICES:-none}"
  echo "binary sha256: $(sha256sum $B/motioncorr | cut -c1-64)"
  ctest --test-dir $B -N | tail -3
  taskset -c $CPUS python3 tools/validate_test_collection.py --test-dir $B; echo "validate_test_collection rc=$?"
  if [ "$cfg" = cpu ]; then
    taskset -c $CPUS python3 tools/test_ci_fail_closed.py -v; echo "test_ci_fail_closed rc=$?"
  fi
  taskset -c $CPUS ctest --test-dir $B --output-on-failure -j1 ${rx:+-R "$rx"} --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"
  echo $rc > $O.exit
} > $O.log 2>&1
