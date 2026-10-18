#!/bin/bash
# Fresh composed-tree CTest (main 1afa03b5 + head), QF run_ctest.sh semantics without the bench lock
# (4GPUs is correctness-only now). CPU on CPUs 24-39; CUDA configs on 88-95 + GPU3 by UUID under its lock.
# At most ONE rerun, and only of a runbook load-sensitive test (ProfilingKit; MultiGpuScheduling).
set -u
cfg=$1
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11
B=$W/build-c3-$cfg; O=$W/ctest-c3-$cfg
GPU=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d; LOCK=/tmp/motioncorr-gpu3-correctness.lock
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES GLIBC_TUNABLES
cd $W/src-c3 || exit 90
load() { echo "load $(date -u +%FT%TZ): $(uptime | sed 's/.*load average/load average/'); compilers cc1plus=$(pgrep -x cc1plus -c) cc1=$(pgrep -x cc1 -c) nvcc=$(pgrep -x nvcc -c) cicc=$(pgrep -x cicc -c) ptxas=$(pgrep -x ptxas -c); users=$(who | awk '{print $1}' | sort -u | wc -l)"; }
if [ "$cfg" = cpu ]; then CPUS=24-39; else
  CPUS=88-95; export CUDA_VISIBLE_DEVICES=$GPU CUDA_DEVICE_ORDER=PCI_BUS_ID
  exec 9>$LOCK; flock 9
  while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$GPU"; do sleep 10; done
fi
{
  echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) tree=$(git rev-parse HEAD^{tree}) status=$(git status --porcelain | wc -l)"
  echo "mask: $CPUS gpu: ${CUDA_VISIBLE_DEVICES:-none}"; load
  echo "binary sha256: $(sha256sum $B/motioncorr | cut -c1-64)"
  ctest --test-dir $B -N | tail -1
  taskset -c $CPUS python3 tools/validate_test_collection.py --test-dir $B; echo "validate_test_collection rc=$?"
  [ "$cfg" = cpu ] && { taskset -c $CPUS python3 tools/test_ci_fail_closed.py -v; echo "test_ci_fail_closed rc=$?"; }
  taskset -c $CPUS ctest --test-dir $B --output-on-failure -j1 --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"; load
  echo $rc > $O.exit
} > $O.log.tmp 2>&1
mv $O.log.tmp $O.log
failed=$(sed -n 's/^[[:space:]]*[0-9]* - \([A-Za-z0-9_]*\) (\(Failed\|Timeout\)).*/\1/p' $O.log | sort -u)
if [ -n "$failed" ]; then
  n=$(echo "$failed" | wc -l)
  if [ "$n" = 1 ] && echo "$failed" | grep -qx 'ProfilingKit\|MultiGpuScheduling'; then
    { echo "single load-sensitive failure: $failed; one rerun"; load
      taskset -c $CPUS ctest --test-dir $B --output-on-failure -R "^${failed}\$"; echo "rerun rc=$?"; load; } > $O.rerun.log 2>&1
    tail -4 $O.rerun.log
  else
    echo "failures not eligible for a rerun: $failed"
  fi
fi
grep -E "tests passed|validate_test_collection rc|test_ci_fail_closed rc|^load" $O.log
