#!/bin/bash
# Rerun composed-CUDA ProfilingKit once the shared host has had no compiler process for 60 s; record compiler samples.
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
export QF_W=$W QF_CPUS=88-95 QF_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d QF_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
for attempt in 1 2 3; do
  quiet=0
  while [ $quiet -lt 12 ]; do n=$(( $(pgrep -x cc1plus -c) + $(pgrep -x nvcc -c) + $(pgrep -x cicc -c) + $(pgrep -x ptxas -c) + $(pgrep -x cc1 -c) )); [ $n -eq 0 ] && quiet=$((quiet+1)) || quiet=0; sleep 5; done
  echo "attempt $attempt start $(date -u +%T), host compiler-free for 60 s"
  ( while sleep 2; do echo "$(date -u +%T) $(( $(pgrep -x cc1plus -c) + $(pgrep -x nvcc -c) + $(pgrep -x cicc -c) + $(pgrep -x ptxas -c) + $(pgrep -x cc1 -c) ))"; done ) > pk-compilers-$attempt.txt & S=$!
  bash ./run_ctest_comp.sh cuda pk-quiet-$attempt "^ProfilingKit$"; kill $S
  rc=$(cat ctest-comp-cuda-pk-quiet-$attempt.exit); echo "attempt $attempt exit=$rc max-compilers-during=$(awk '{print $2}' pk-compilers-$attempt.txt | sort -n | tail -1)"
  [ "$rc" = 0 ] && break
done
echo PK_DONE
