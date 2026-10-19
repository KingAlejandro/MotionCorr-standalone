#!/bin/bash
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
for k in cpu cuda nvcomp; do ./build2.sh $W/src-c3 $W/build-c3-$k $k > build-c3-$k.out 2>&1; grep -v HOME build-c3-$k.out; done
echo BUILDS3_DONE
