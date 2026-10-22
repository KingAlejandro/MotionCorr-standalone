#!/bin/bash
# #244 opt-in destructive CudaStickyContext on GPU3 (docs/issue213/README.md runbook). usage: c1_sticky.sh cuda|nvcomp
# Builds only motioncorr_sticky_fault in a separate build tree (MC_ENABLE_STICKY_CUDA_TEST=ON), then runs the driver under the GPU3 lock.
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
cfg=$1; B=$C1_SCR/build-sticky-$cfg
if [ ! -x $B/motioncorr_sticky_fault ]; then
  CFG=$cfg "$(dirname "$0")/c1_build.sh" $C1_SCR/src $B motioncorr_sticky_fault -DBUILD_TESTING=ON -DMC_ENABLE_STICKY_CUDA_TEST=ON || exit 2
fi
sha256sum $B/motioncorr_sticky_fault > $B.binaries.sha256
exec 9>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 lock contended; stopping"; exit 5; }
"$(dirname "$0")/c1_occupancy.sh" sticky-$cfg-pre || exit 3
CUDA_VISIBLE_DEVICES=$C1_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c $C1_CPUS $C1_PY $C1_SCR/src/tests/run_sticky_cuda_control.py \
  --binary $B/motioncorr_sticky_fault --workdir $C1_SCR/sticky-$cfg; rc=$?
"$(dirname "$0")/c1_occupancy.sh" sticky-$cfg-post
exit $rc
