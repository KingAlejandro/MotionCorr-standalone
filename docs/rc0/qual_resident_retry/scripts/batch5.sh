#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
cd $S
./runcpu.sh $S/build/cpu-pre197/motioncorr b5_cpu_pre
./runcpu.sh $S/build/cpu-1db/motioncorr b5_cpu_db
echo done > runs/BATCH5DONE
