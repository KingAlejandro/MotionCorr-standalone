#!/bin/bash
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
until grep -q BUILDS_DONE build-fix-nvcomp-head.out 2>/dev/null; do sleep 15; done
cat build-fix-cpu.out build-fix-cuda.out build-fix-nvcomp-head.out | grep -v HOME
grep -q "build rc=0" build-fix-cpu.out && grep -q "build rc=0" build-fix-cuda.out && grep -q "build rc=0" build-fix-nvcomp-head.out || { echo BUILD_FAILED; exit 1; }
./perf.sh
export QF_W=$W QF_CPUS=88-95 QF_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d QF_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
for c in cpu cuda nvcomp; do bash ./run_ctest.sh $c; echo "ctest $c exit=$(cat ctest-fix-$c.exit)"; tail -4 ctest-fix-$c.log | head -3; done
echo DRIVE_DONE
