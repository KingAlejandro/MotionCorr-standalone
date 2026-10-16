#!/bin/bash
# Locked region: full native ctest of the candidate head (CUDA) and the CUDA=OFF suite, with test counts of main.
set -uo pipefail
W=/home/alex/mc-small/wu
export PATH=/usr/local/cuda/bin:/home/alex/.mc-venv/bin:$PATH
NV=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
PY=/home/alex/.mc-venv/bin/python
echo "region start $(date -Is) load=$(cut -d' ' -f1-3 /proc/loadavg)"
# test inventory of main (configure only)
for cfg in cuda cpu; do
  rm -rf $W/b-inv-main-$cfg
  if [ $cfg = cuda ]; then F="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NV"; else F="-DCUDA=OFF"; fi
  cmake -S $W/src-main -B $W/b-inv-main-$cfg -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON $F -DPython3_EXECUTABLE=$PY > $W/b-inv-main-$cfg.log 2>&1
  echo "main $cfg: $(cd $W/b-inv-main-$cfg && ctest -N | tail -1)"
done
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID
for cfg in cuda cpu; do
  B=$W/b-full-$cfg
  rm -rf $B
  if [ $cfg = cuda ]; then F="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NV"; else F="-DCUDA=OFF"; fi
  cmake -S $W/src-c4 -B $B -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON $F -DPython3_EXECUTABLE=$PY > $B.cmake.log 2>&1; echo "c3 $cfg cmake rc=$?"
  cmake --build $B -j8 > $B.build.log 2>&1; echo "c3 $cfg build rc=$? $(date -Is)"
  echo "c3 $cfg: $(cd $B && ctest -N | tail -1)"
  J=1; [ $cfg = cpu ] && J=4
  (cd $B && ctest --output-on-failure -j$J > $W/ctest-c3-$cfg.log 2>&1; echo "c3 $cfg ctest rc=$?")
  tail -12 $W/ctest-c3-$cfg.log
done
echo "region end $(date -Is)"
