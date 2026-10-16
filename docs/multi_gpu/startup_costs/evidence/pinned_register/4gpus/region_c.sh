#!/bin/bash
# Region C (bench lock held): full ctest of step 2 alone, CUDA (GPU0 lock) and CUDA=OFF.
# Any CUDA failure is rerun once on the candidate and once on a main build with tests.
set -uo pipefail
S=/dev/shm/mcs2
export PATH=/usr/local/cuda/bin:/home/alex/.mc-venv/bin:$PATH
NV=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive; PY=/home/alex/.mc-venv/bin/python
echo "region C start $(date -Is) load=$(cut -d' ' -f1-3 /proc/loadavg)"
cfgflags() { if [ $1 = cuda ]; then echo "-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NV"; else echo "-DCUDA=OFF"; fi; }
for t in s2:cuda s2:cpu main:cuda; do a=${t%%:*}; cfg=${t#*:}; B=$S/b-full-$a-$cfg; rm -rf $B
  cmake -S $S/src-$a -B $B -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON $(cfgflags $cfg) -DPython3_EXECUTABLE=$PY > $B.cmake.log 2>&1; echo "$a $cfg cmake rc=$?"
  cmake --build $B -j8 > $B.build.log 2>&1; echo "$a $cfg build rc=$? $(date -Is) $(cd $B && ctest -N | tail -1)"
done
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID
flock -w 28800 /tmp/motioncorr-gpu0-correctness.lock bash -c '
  S=/dev/shm/mcs2; B=$S/b-full-s2-cuda
  uname -r > $S/probes/fork.txt; $S/fork_probe 3 >> $S/probes/fork.txt 2>&1; echo "fork_probe rc=$?"; cat $S/probes/fork.txt
  (cd $B && ctest --output-on-failure -j1 > $S/ctest-s2-cuda.log 2>&1; echo "s2 cuda ctest rc=$?")
  tail -12 $S/ctest-s2-cuda.log
  failed=$(sed -n "s/^[[:space:]]*[0-9]* - \([A-Za-z0-9_]*\) (.*/\1/p" $S/ctest-s2-cuda.log | paste -sd"|")
  if [ -n "$failed" ]; then
    echo "rerun failed: $failed"
    (cd $B && ctest --output-on-failure -R "^($failed)\$" > $S/ctest-s2-cuda-rerun.log 2>&1; echo "s2 rerun rc=$?")
    (cd $S/b-full-main-cuda && ctest --output-on-failure -R "^($failed)\$" > $S/ctest-main-cuda-failed.log 2>&1; echo "main same tests rc=$?")
    grep -E "Test +#|tests passed" $S/ctest-s2-cuda-rerun.log $S/ctest-main-cuda-failed.log
  fi'
(cd $S/b-full-s2-cpu && ctest --output-on-failure -j4 > $S/ctest-s2-cpu.log 2>&1; echo "s2 cpu ctest rc=$?")
tail -8 $S/ctest-s2-cpu.log
echo "region C end $(date -Is)"
