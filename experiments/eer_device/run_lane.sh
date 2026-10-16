#!/bin/sh
# Run a command in the W-EER-DEV lane on 4GPUs: GPU0 by UUID, CPUs 96-103, with the lane locks.
# usage: run_lane.sh [--bench] command args...
# Locks are taken in ascending order: gpu0-correctness, then (with --bench) bench. --bench also pins memory
# and CPUs to NUMA node 1 (numactl --cpunodebind=1 --membind=1) and samples GPUs 1-3 (to $LANE_GPU_SAMPLES) while the
# command runs. A foreign compute process on GPU0 makes the run wait (up to 10 min) and then fail with 75;
# nothing is ever killed except the sampler this script started.
GPU_UUID=${LANE_GPU_UUID:-GPU-eddb42fe-4f9a-adde-76d3-b924e14add54}
CPUS=${LANE_CPUS:-96-103}
bench=0; [ "$1" = "--bench" ] && { bench=1; shift; }
inner='
i=0
while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$GPU_UUID"; do
  i=$((i+1)); [ $i -gt 120 ] && { echo "foreign process on GPU0" >&2; exit 75; }; sleep 5
done
export CUDA_VISIBLE_DEVICES=$GPU_UUID
if [ "$BENCH" = 1 ]; then
  if [ -n "$LANE_GPU_SAMPLES" ]; then
    nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv,noheader -l 1 > "$LANE_GPU_SAMPLES" 2>/dev/null &
    sp=$!
  fi
  numactl --cpunodebind=1 --membind=1 taskset -c $CPUS "$@"; rc=$?
  [ -n "$sp" ] && kill $sp 2>/dev/null
  exit $rc
fi
exec taskset -c $CPUS "$@"
'
export GPU_UUID CPUS
if [ $bench = 1 ]; then
  BENCH=1 exec flock /tmp/motioncorr-gpu0-correctness.lock flock /tmp/motioncorr-bench.lock sh -c "$inner" lane "$@"
else
  BENCH=0 exec flock /tmp/motioncorr-gpu0-correctness.lock sh -c "$inner" lane "$@"
fi
