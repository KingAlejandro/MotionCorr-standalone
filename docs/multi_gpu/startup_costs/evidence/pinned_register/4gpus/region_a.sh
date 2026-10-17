#!/bin/bash
# Region A (bench lock held, lane 96-103): build three timing arms from scratch,
# then, under the GPU0 lock, the pinning probes and the slow-round series.
set -uo pipefail
S=/dev/shm/mcs2; E=$S/ev
export PATH=/usr/local/cuda/bin:/home/alex/.mc-venv/bin:$PATH
NV=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive; PY=/home/alex/.mc-venv/bin/python
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
echo "region A start $(date -Is) load=$(cut -d' ' -f1-3 /proc/loadavg)"
for a in main s2 c1; do
  rm -rf $S/b-t-$a
  cmake -S $S/src-$a -B $S/b-t-$a -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NV -DPython3_EXECUTABLE=$PY > $S/b-t-$a.cmake.log 2>&1; echo "$a cmake rc=$?"
  cmake --build $S/b-t-$a -j8 > $S/b-t-$a.build.log 2>&1; echo "$a build rc=$? $(date -Is) sha=$(sha256sum $S/b-t-$a/motioncorr | cut -c1-16)"
done
nvcc -O2 -arch=sm_80 -o $S/fork_probe $E/fork_probe.cu && nvcc -O2 -arch=sm_80 -o $S/pin_probe $E/pin_probe.cu; echo "probes rc=$?"
echo "builds done $(date -Is); waiting for GPU0 lock"
export CUDA_VISIBLE_DEVICES=$U CUDA_DEVICE_ORDER=PCI_BUS_ID
flock -w 28800 /tmp/motioncorr-gpu0-correctness.lock bash -c '
  S=/dev/shm/mcs2; mkdir -p $S/probes
  echo "gpu lock $(date -Is)"
  uname -r > $S/probes/fork.txt; $S/fork_probe 3 >> $S/probes/fork.txt 2>&1; echo "fork_probe rc=$?"
  : > $S/probes/pin.jsonl
  for rep in $(seq 1 15); do for m in hostalloc reg_huge reg_4k; do $S/pin_probe $m >> $S/probes/pin.jsonl 2>&1; done; done
  echo "pin_probe done $(date -Is)"
  R24=12 R96=4 bash $S/ev/stall_ab.sh $S/runs-stall \
     main=$S/b-t-main/motioncorr s2=$S/b-t-s2/motioncorr c1=$S/b-t-c1/motioncorr > $S/stall_ab.out 2>&1
  echo "stall_ab rc=$? $(date -Is)"'
echo "region A end $(date -Is)"
