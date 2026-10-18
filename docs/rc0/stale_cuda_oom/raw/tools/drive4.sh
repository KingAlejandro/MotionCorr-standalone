#!/bin/bash
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
until grep -q BUILDS3_DONE drive3.out; do sleep 20; done
grep -q "build rc=0" build-c3-cpu.out && grep -q "build rc=0" build-c3-cuda.out && grep -q "build rc=0" build-c3-nvcomp.out || { echo BUILD_FAILED; exit 1; }
for c in cuda nvcomp cpu; do echo "=== $c"; bash ./run_ctest3.sh $c; done
echo DRIVE4_DONE
