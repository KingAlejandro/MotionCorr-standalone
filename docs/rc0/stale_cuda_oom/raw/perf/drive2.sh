#!/bin/bash
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
until grep -q DRIVE_DONE drive.out 2>/dev/null; do sleep 30; done
./build.sh $W/src-comp $W/build-comp-cuda cuda > build-comp-cuda.out 2>&1
./build.sh $W/src-comp $W/build-comp-nvcomp nvcomp > build-comp-nvcomp.out 2>&1
cat build-comp-cuda.out build-comp-nvcomp.out | grep -v HOME
export QF_W=$W QF_CPUS=88-95 QF_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d QF_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
for c in cuda nvcomp; do bash ./run_ctest_comp.sh $c; echo "ctest comp $c exit=$(cat ctest-comp-$c.exit)"; tail -4 ctest-comp-$c.log | head -3; done
echo DRIVE2_DONE
