#!/bin/bash
# New output-oracle test and its four oracle mutants on one GPU, chosen by UUID, under its lock.
set -u
S=/mnt/clathrin/alex-motioncorr-254-oracle-20261021; B=${B:-$S/build-nvcomp}
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d OMP_NUM_THREADS=8
exec 9>/tmp/motioncorr-gpu3-correctness.lock
flock -w 900 9 || exit 3
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv > "$S/logs/occupancy-oracle.log"
t() { local label=$1; shift; taskset -c ${CPUS:-112-119} "$@" > "$S/logs/$label.log" 2>&1; echo $? > "$S/logs/$label.exit"; }
t oracle-main "$B/cuda_hermitian_inverse"
for m in oracle_session_no_projection oracle_session_zero_boundary oracle_wrapper_zero_boundary oracle_dose_zero_boundary; do
  t raw-$m "$B/cuda_hermitian_inverse_$m" --expect-oracle-failure
  t exp-$m "$B/cuda_hermitian_inverse_$m" --expect-oracle-failure
done
echo done > "$S/oracle-done"
