#!/bin/bash
# Item 2: full CTest, no exclusions, one configuration. Usage: run_ctest.sh cpu|cuda|nvcomp [tag]
# CPU-pinned to 104-111; CUDA configurations hold the GPU1 correctness flock for the batch and see
# only GPU1 (CUDA_VISIBLE_DEVICES=<UUID>). Writes <build>/../ctest-<cfg>[-tag].{log,junit.xml,exit}.
set -u
cfg=$1; tag=${2:-}
W=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL
B=$W/build-$cfg
O=$W/ctest-$cfg${tag:+-$tag}
GPU1=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
cd $W/src || exit 90                       # real git checkout (CiFailClosedControls)
if [ "$cfg" != cpu ]; then
  export CUDA_VISIBLE_DEVICES=$GPU1 CUDA_DEVICE_ORDER=PCI_BUS_ID
  exec 9>/tmp/motioncorr-gpu1-correctness.lock
  flock 9
  # foreign compute process on GPU1 -> wait (never touch it)
  while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$GPU1"; do sleep 10; done
fi
{
  echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l)"
  echo "mask: $(taskset -cp $$)"
  ctest --test-dir $B -N | tail -3
  taskset -c 104-111 python3 tools/validate_test_collection.py --test-dir $B; echo "validate_test_collection rc=$?"
  taskset -c 104-111 ctest --test-dir $B --output-on-failure -j1 --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"
  echo $rc > $O.exit
} > $O.log 2>&1
