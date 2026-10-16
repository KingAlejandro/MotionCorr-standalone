#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
export S
inner() {
 flock -n /tmp/motioncorr-bench.lock true || exit 75
 cd $S/build/cuda-branch
 taskset -c 80-87 env CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID \
  ctest -R '^(PatchRetryState|CudaFaultMatrix|CudaErrorClass|CudaPreprocessingFailurePaths|CudaPatchBatch|CudaResidentRetryFailures|CudaNvcompReconstructionFailures|CudaNvcompAcceptanceFailures)$' --output-on-failure -j1 > $S/ctest/ctest-branch.log 2>&1
 echo "ctest-rc=$?" >> $S/ctest/ctest-branch.log
}
export -f inner
while true; do
 until flock -n /tmp/motioncorr-bench.lock true; do sleep 60; done
 flock /tmp/motioncorr-gpu2-correctness.lock bash -c inner; rc=$?
 [ $rc -ne 75 ] && break
done
tail -20 $S/ctest/ctest-branch.log
