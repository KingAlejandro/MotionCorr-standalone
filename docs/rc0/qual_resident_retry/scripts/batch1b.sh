#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
DB=$S/build/cuda-1db/motioncorr; PRE=$S/build/cuda-pre197/motioncorr
cd $S
while [ ! -e runs/BATCH1DONE ]; do sleep 5; done
for rep in a b; do
 ./runfam.sh $PRE e10641u b1u_e10641_pre_$rep
 ./runfam.sh $DB e10641u b1u_e10641_db_$rep
done
echo done > runs/BATCH1BDONE
