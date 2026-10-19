#!/bin/bash
# QF item 12 dataset wrapper: restores #207's asymmetric poison case without product or test changes.
# #210 removed the shim's MC_FAULT_ONLY_CVD; this wrapper selects the fault by the worker's own device
# instead and execs the unchanged frozen motioncorr_resident_retry_fault. The resident-retry fatal fault
# is enabled only when CUDA_VISIBLE_DEVICES is exactly $QF_FAULT_UUID; every other invocation (the other
# worker, and the GPU-less aggregate step) runs the shim with no fault. One attribution line to stderr.
set -u
: "${QF_FAULT_SHIM:?}" "${QF_FAULT_UUID:?}"
if [ "${CUDA_VISIBLE_DEVICES:-}" = "$QF_FAULT_UUID" ]; then
  export MC_PREPROCESS_FAULT=resident-retry-fatal
  echo "[qf-fault-wrapper] fault=on cvd=${CUDA_VISIBLE_DEVICES:-}" >&2
else
  unset MC_PREPROCESS_FAULT
  echo "[qf-fault-wrapper] fault=off cvd=${CUDA_VISIBLE_DEVICES:-}" >&2
fi
exec "$QF_FAULT_SHIM" "$@"
