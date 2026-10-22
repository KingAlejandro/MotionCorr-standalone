#!/bin/bash
# Run a GPU3 job inside the nonblocking canonical lease with mandatory health propagation (see c1_health.sh).
# usage: c1_gpu_run.sh LABEL cmd...   Note: drivers that take the GPU lease themselves (sticky, run_case based QF/T24 tools) are NOT wrapped in this lock.
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
exec 9>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 correctness lock contended; stopping"; exit 5; }
export CUDA_VISIBLE_DEVICES=$C1_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
exec "$D/c1_health.sh" "$@"
