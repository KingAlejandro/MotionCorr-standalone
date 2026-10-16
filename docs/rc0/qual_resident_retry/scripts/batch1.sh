#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
DB=$S/build/cuda-1db/motioncorr; PRE=$S/build/cuda-pre197/motioncorr
cd $S
for fam in e10641 e10216; do
 for rep in a b; do
  ./runfam.sh $PRE $fam b1_${fam}_pre_$rep
  ./runfam.sh $DB $fam b1_${fam}_db_$rep
 done
done
echo BATCH1DONE > $S/runs/BATCH1DONE
