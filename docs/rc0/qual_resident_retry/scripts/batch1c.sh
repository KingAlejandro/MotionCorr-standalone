#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
REV=$S/build/cuda-rev197/motioncorr; DB=$S/build/cuda-1db/motioncorr
cd $S
for fam in e10641u e10216; do
 ./runfam.sh $REV $fam b1c_${fam}_rev_a
 ./runfam.sh $DB  $fam b1c_${fam}_db_c
done
echo done > runs/BATCH1CDONE
